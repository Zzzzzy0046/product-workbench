"""Read-only store discovery: bounded subprocesses and an in-memory TTL cache."""

from collections import OrderedDict
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile

from workbench.core.runtime import *
from workbench.services.base import BoundService
from workbench.core.competitor_markets import GLOBAL_MARKETS


class CompetitorDiscoveryAdapter(BoundService):
    TTL = 24 * 60 * 60
    CACHE_LIMIT = 64
    MAX_RESULT_BYTES = 3 * 1024 * 1024
    TIMEOUT = 35
    GLOBAL_TIMEOUT = 55
    GLOBAL_MARKET_TIMEOUT = 12

    def __init__(self, workbench):
        super().__init__(workbench)
        object.__setattr__(self, "_cache", OrderedDict())
        object.__setattr__(self, "_cache_lock", threading.RLock())
        object.__setattr__(self, "_slots", threading.BoundedSemaphore(2))
        object.__setattr__(self, "_global_slots", threading.BoundedSemaphore(1))
        object.__setattr__(self, "_closed", threading.Event())

    def close(self):
        """Do not start queued global markets after workbench shutdown."""
        self._closed.set()
        with self.lock:
            for key, process in list(self.processes.items()):
                if key.startswith("discovery:"):
                    self._stop_discovery_process(process)

    @staticmethod
    def _stop_discovery_process(process):
        # These read-only workers never spawn child processes. Keep cleanup
        # bounded instead of invoking the slower generic taskkill tree path.
        for name in ("kill", "terminate"):
            try:
                getattr(process, name)()
                process.wait(timeout=1)
                return True
            except (AttributeError, OSError, subprocess.TimeoutExpired):
                continue
        return False

    def _validated(self, project_id, payload, detail=False):
        self.project(project_id)
        if not isinstance(payload, dict):
            raise ValueError("竞品搜索参数无效。")
        self.version_service.resolve(project_id, payload.get("version_id", ""))
        platform = str(payload.get("platform") or "google_play").strip()
        if platform not in {"google_play", "app_store"}:
            raise ValueError("只支持 Android / Google Play 或 iOS / App Store。")
        country = str(payload.get("country") or "us").strip().lower()
        language = str(payload.get("lang") or "en").strip().lower()
        if country == "global" and detail:
            country = str(payload.get("lookup_country") or "").strip().lower()
            if not re.fullmatch(r"[a-z]{2}", country):
                raise ValueError("多市场候选的详情需要具体 lookup_country；请选择该候选的发现市场，不会自动回退美国。")
        if country != "global" and not re.fullmatch(r"[a-z]{2}", country):
            raise ValueError("请选择两位代码国家或“全球（8个预设市场合并）”。")
        if not re.fullmatch(r"[a-z]{2,3}(?:[-_][a-z0-9]{2,8})?", language):
            raise ValueError("搜索语言格式无效，例如 en、zh-cn。")
        request = {"mode": "discovery_detail" if detail else "discovery_search", "platform": platform, "country": country, "lang": language}
        if detail:
            app_id = str(payload.get("app_id") or "").strip()
            if not app_id or len(app_id) > 200 or not re.fullmatch(r"[A-Za-z0-9_.-]+", app_id):
                raise ValueError("应用 ID 无效。")
            if platform == "app_store" and not app_id.isdigit():
                raise ValueError("App Store 应用 ID 必须为数字。")
            request["app_id"] = app_id
        else:
            query = str(payload.get("query") or "").strip()
            if not query or len(query) > 160 or any(ord(character) < 32 for character in query):
                raise ValueError("请输入 1–160 字的品类或功能关键词，不支持控制字符。")
            try:
                if isinstance(payload.get("limit"), bool) or (isinstance(payload.get("limit"), float) and not payload["limit"].is_integer()):
                    raise ValueError()
                limit = int(payload.get("limit", 12))
            except (TypeError, ValueError) as exc:
                raise ValueError("候选数量必须为 1–30 的整数。") from exc
            if limit < 1 or limit > 30:
                raise ValueError("每次搜索最多返回 30 个候选。")
            request.update(query=query, limit=limit)
        if "refresh" in payload and not isinstance(payload["refresh"], bool):
            raise ValueError("刷新参数必须为布尔值。")
        return request

    def _cached(self, key):
        with self._cache_lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            expires, value = entry
            if expires <= time.monotonic():
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            return {**deepcopy(value), "cached": True}

    def _remember(self, key, value):
        with self._cache_lock:
            self._cache[key] = (time.monotonic() + self.TTL, deepcopy(value))
            self._cache.move_to_end(key)
            while len(self._cache) > self.CACHE_LIMIT:
                self._cache.popitem(last=False)

    def _worker_request(self, request):
        settings = self.review_scraper_settings()
        # Apple discovery uses only the standard library; Android reuses the
        # explicitly configured local scraper environment, without importing AI.
        if request["platform"] == "google_play" and (not settings["ready"] or not settings["enabled"]):
            raise ValueError("Android 搜索需要可用的本机评论采集工具，请到设置检查工具目录、Python 和启用状态；也可直接粘贴已知竞品链接。")
        python = settings.get("python") if settings.get("ready") else sys.executable
        runtime_request = {**request, "root": settings.get("worker_root", settings.get("root", ""))}
        command = [python, "-X", "utf8", str(HERE / "review_scraper_worker.py")]
        environment = os.environ.copy()
        environment.update(PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        timeout = min(self.TIMEOUT, max(1, float(request.get("_timeout_seconds") or self.TIMEOUT)))
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            with self.lock:
                if self._closed.is_set():
                    raise ValueError("工作台已关闭，尚未开始的商店查询已停止。")
                process = subprocess.Popen(
                    command, stdin=subprocess.PIPE, stdout=output, stderr=errors,
                    cwd=settings["root"] if settings.get("ready") else HERE,
                    env=environment, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                process_key = "discovery:" + uid()
                self.processes[process_key] = process
            try:
                process.communicate(json.dumps(runtime_request, ensure_ascii=True).encode("utf-8"), timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                self._stop_discovery_process(process)
                raise ValueError(f"商店查询超过 {timeout:g} 秒已停止，请稍后重试或换关键词；也可直接粘贴竞品链接。") from exc
            finally:
                with self.lock:
                    self.processes.pop(process_key, None)
            output.seek(0, 2)
            if output.tell() > self.MAX_RESULT_BYTES:
                raise ValueError("商店返回内容过大，已停止读取；请减少候选数量。")
            output.seek(0)
            try:
                result = json.loads(output.read().decode("utf-8"))
            except (UnicodeDecodeError, TypeError, ValueError) as exc:
                raise ValueError("商店采集器返回格式不正确，请检查本机工具依赖或稍后重试。") from exc
            if not isinstance(result, dict):
                raise ValueError("商店采集器返回格式不正确。")
            if process.returncode:
                # Never expose arbitrary imported exception text, URLs, cookies
                # or local config; the worker supplies a small safe error code.
                code = str(result.get("error_code") or "store_error")
                messages = {
                    "missing_dependency": "本机采集 Python 缺少 Google Play 搜索依赖，请检查采集工具的 Python 环境；也可直接粘贴竞品链接。",
                    "unsupported_capability": "当前本机采集库不支持搜索，请升级采集工具依赖，或直接粘贴竞品链接。",
                    "not_found": "指定国家未找到该应用，请更换国家或检查应用 ID。",
                    "network_error": "商店暂时无法连接或请求被限制，请稍后重试、检查网络或更换国家。",
                }
                raise ValueError(messages.get(code, "商店搜索或详情读取失败，请稍后重试或直接粘贴竞品链接。"))
            return result

    def _discover(self, request, refresh=False, timeout_seconds=None):
        if self._closed.is_set():
            raise ValueError("工作台已关闭，商店查询已停止。")
        settings = self.review_scraper_settings()
        # Configuration identity is part of the key, so changing/disabling a
        # local integration cannot silently reuse another environment's result.
        key = (settings.get("root"), settings.get("python"), settings.get("enabled"), *sorted(request.items()))
        if not refresh:
            cached = self._cached(key)
            if cached is not None:
                return cached
        if not self._slots.acquire(blocking=False):
            raise ValueError("已有两个商店查询正在进行，请等候完成后重试。")
        try:
            runtime_request = {**request, "_timeout_seconds": timeout_seconds} if timeout_seconds is not None else request
            result = self._worker_request(runtime_request)
            detail = request["mode"] == "discovery_detail"
            if detail and not isinstance(result.get("listing"), dict):
                raise ValueError("商店没有返回有效应用详情。")
            if not detail and (not isinstance(result.get("items"), list) or len(result["items"]) > request["limit"]):
                raise ValueError("商店没有返回有效候选列表。")
            value = {"listing" if detail else "items": result["listing" if detail else "items"], "warnings": list(result.get("warnings") or [])[:8], "cached": False, "collected_at": now()}
            self._remember(key, value)
            return deepcopy(value)
        finally:
            self._slots.release()

    def search_competitors(self, project_id, payload):
        request = self._validated(project_id, payload)
        if request["country"] == "global":
            return self._global_search(request, payload.get("refresh", False))
        result = self._discover(request, payload.get("refresh", False))
        country = request["country"]
        for item in result["items"]:
            item.update(lookup_country=country, observed_countries=[country])
        return {**result, "scope": "single_market", "countries": [country], "attempted_countries": [country], "successful_countries": [country], "failed_countries": []}

    def _global_search(self, request, refresh=False):
        if self._closed.is_set():
            raise ValueError("工作台已关闭，商店查询已停止。")
        if not self._global_slots.acquire(blocking=False):
            raise ValueError("已有一个多市场搜索执行中，请等待完成后再试。")
        deadline = time.monotonic() + self.GLOBAL_TIMEOUT
        results, failures, attempted = {}, {}, set()
        attempted_lock = threading.Lock()
        def market_query(country):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or self._closed.is_set():
                raise ValueError("总等待预算已用尽或工作台已关闭，未启动该市场。")
            with attempted_lock:
                attempted.add(country)
            return self._discover({**request, "country": country}, refresh, min(self.GLOBAL_MARKET_TIMEOUT, remaining))
        try:
            # Only two markets may run concurrently, and _slots also caps all
            # live store subprocesses (including single-market/detail queries).
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="store-discovery") as executor:
                futures = {executor.submit(market_query, country): country for country in GLOBAL_MARKETS}
                for future in as_completed(futures):
                    country = futures[future]
                    try:
                        results[country] = future.result()
                    except Exception:  # imported failures must not expose secrets
                        failures[country] = "查询失败、超时或总预算已用尽"
            if not results:
                raise ValueError("全球（8个预设市场合并）搜索全部失败，未回退美国；请检查本机采集依赖和网络，或选择具体国家重试。")
            # Round-robin source order gives each successful market a chance;
            # append observed markets even if the final candidate limit is full.
            queues = {country: list(results[country]["items"]) for country in GLOBAL_MARKETS if country in results}
            all_items, ordered_keys = {}, []
            depth = max((len(items) for items in queues.values()), default=0)
            for offset in range(depth):
                for country in GLOBAL_MARKETS:
                    items = queues.get(country, [])
                    if offset >= len(items):
                        continue
                    item = items[offset]
                    key = (item.get("platform") or request["platform"], str(item.get("app_id") or ""))
                    if not key[1]:
                        continue
                    if key not in all_items:
                        all_items[key] = {**item, "lookup_country": country, "observed_countries": [country]}
                        ordered_keys.append(key)
                    elif country not in all_items[key]["observed_countries"]:
                        all_items[key]["observed_countries"].append(country)
            items = [all_items[key] for key in ordered_keys[:request["limit"]]]
            successful = [country for country in GLOBAL_MARKETS if country in results]
            failed = [country for country in GLOBAL_MARKETS if country not in results]
            warnings = [
                "“全球”仅为 US、GB、DE、JP、IN、ID、BR、SA 八个预设市场的候选合并，不代表所有国家、全球榜单或市场排名。",
                "评分、评价量、价格、安装区间等字段来自每个候选的 lookup_country 市场，不是全球汇总；重复应用仅合并发现市场。",
            ]
            if failed:
                warnings.append("部分市场未完成：" + "、".join(country.upper() for country in failed) + "；已展示其余成功市场，未用美国结果替代。")
            for country in successful:
                for warning in results[country].get("warnings", []):
                    if warning not in warnings and len(warnings) < 8:
                        warnings.append(str(warning)[:500])
            return {"items": items, "cached": all(result["cached"] for result in results.values()) and not failed, "collected_at": max(result["collected_at"] for result in results.values()), "warnings": warnings, "scope": "global_multi_market", "countries": list(GLOBAL_MARKETS), "attempted_countries": [country for country in GLOBAL_MARKETS if country in attempted], "successful_countries": successful, "failed_countries": failed}
        finally:
            self._global_slots.release()

    def competitor_detail(self, project_id, payload):
        request = self._validated(project_id, payload, detail=True)
        result = self._discover(request, payload.get("refresh", False))
        return {**result, "lookup_country": request["country"]}
