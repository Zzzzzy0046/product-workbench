"""Desktop competitor-review scraper bridge and isolated worker lifecycle."""

from workbench.core.runtime import *
from workbench.services.base import BoundService


class ReviewScraperAdapter(BoundService):
    def review_scraper_settings(self):
        """Return safe local configuration for the desktop review scraper."""
        rows = self.rows("SELECT value FROM preferences WHERE key=?", (REVIEW_SCRAPER_CONFIG_KEY,))
        saved = {}
        if rows:
            try:
                saved = json.loads(rows[0]["value"])
            except (TypeError, ValueError):
                saved = {}
        default_root = Path.home() / "Desktop" / "competitor-analysis-platform"
        root_value = str(
            saved.get("root")
            or os.environ.get("WORKBENCH_REVIEW_SCRAPER_ROOT", "")
            or default_root
        ).strip()
        try:
            root = Path(root_value).expanduser().resolve()
        except (OSError, RuntimeError):
            root = Path(root_value).expanduser()
        source_file = root / "app" / "scrapers.py"
        python_value = str(saved.get("python") or "").strip()
        candidates = []
        if python_value:
            candidates.append(Path(python_value).expanduser())
        candidates.extend([
            root / ".venv" / "Scripts" / "python.exe",
            root / ".venv" / "bin" / "python",
            Path(sys.executable),
        ])
        python = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
        if python is None and python_value:
            located = shutil.which(python_value)
            if located:
                python = Path(located).resolve()
        ready = bool(root.is_dir() and source_file.is_file() and python and python.is_file())
        if not root.is_dir():
            message = "未找到竞品评论工具目录。"
        elif not source_file.is_file():
            message = "工具目录存在，但未找到 app/scrapers.py。"
        elif not python:
            message = "未找到可用 Python；请检查工具目录的 .venv。"
        elif ready:
            message = "已检测到桌面竞品评论采集工具。"
        else:
            message = "竞品评论采集器暂不可用。"
        return {
            "root": str(root),
            "python": str(python) if python else "",
            "source": "saved" if saved else "默认桌面路径",
            "ready": ready,
            "enabled": bool(saved.get("enabled", True)),
            "message": message,
        }

    def save_review_scraper_settings(self, payload):
        root_value = str(
            payload.get("root")
            or os.environ.get("WORKBENCH_REVIEW_SCRAPER_ROOT", "")
            or (Path.home() / "Desktop" / "competitor-analysis-platform")
        ).strip()
        if not root_value or len(root_value) > 500:
            raise ValueError("竞品评论工具目录路径无效或过长。")
        root = Path(root_value).expanduser().resolve()
        if not (root / "app" / "scrapers.py").is_file():
            raise ValueError("工具目录无效，未找到 app/scrapers.py。")
        python_value = str(payload.get("python") or "").strip()
        if len(python_value) > 500:
            raise ValueError("Python 路径过长。")
        saved = {"root": str(root), "enabled": bool(payload.get("enabled", True))}
        if python_value:
            candidate = Path(python_value).expanduser()
            if candidate.is_file():
                saved["python"] = str(candidate.resolve())
            elif shutil.which(python_value):
                saved["python"] = python_value
            else:
                raise ValueError("指定的 Python 不存在。")
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO preferences VALUES(?,?)",
                (REVIEW_SCRAPER_CONFIG_KEY, json.dumps(saved, ensure_ascii=False)),
            )
        return self.review_scraper_settings()

    def scrapes(self, project_id):
        self.project(project_id)
        rows = self.rows(
            """SELECT s.*,v.name AS version_name FROM scrapes s
               LEFT JOIN product_versions v ON v.id=s.version_id
               WHERE s.project_id=? ORDER BY s.created DESC""",
            (project_id,),
        )
        return [self._with_collection_preview(item) for item in rows]

    def _collection_directory(self, scrape):
        return self.data / "scrapes" / scrape["project_id"] / scrape["id"]

    def _collection_manifest(self, scrape):
        path = self._collection_directory(scrape) / "manifest.json"
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _with_collection_preview(self, scrape, include_listing=False):
        item = dict(scrape)
        try:
            request = json.loads(item.get("request") or "{}")
        except (TypeError, ValueError):
            request = {}
        manifest = self._collection_manifest(item)
        listing = manifest.get("listing") if isinstance(manifest.get("listing"), dict) else {}
        item.update({
            "collection_type": "competitor" if request.get("collect_listing") else "reviews",
            "listing_title": str(listing.get("title") or ""),
            "listing_market": str(listing.get("market") or ""),
            "has_short_description": bool(str(listing.get("short_description") or "").strip()),
            "has_long_description": bool(str(listing.get("long_description") or "").strip()),
            "screenshot_count": len(listing.get("screenshot_files") or []),
            "document_ids": manifest.get("document_ids") or [],
            "translation_requested": bool(request.get("translate")),
            "translated_count": int(manifest.get("translated_count") or 0),
        })
        if include_listing:
            item["listing"] = listing
            item["warnings"] = manifest.get("warnings") or []
        return item

    @staticmethod
    def _parse_competitor_entry(value):
        raw = str(value or "").strip()
        if not raw or len(raw) > 500:
            raise ValueError("竞品链接或应用 ID 无效。")
        parsed = urlparse(raw if "://" in raw else "")
        if parsed.scheme:
            host = (parsed.hostname or "").lower()
            if host == "play.google.com" or host.endswith(".play.google.com"):
                app_id = str((parse_qs(parsed.query).get("id") or [""])[0]).strip()
                platform = "google_play"
            elif host == "apps.apple.com" or host.endswith(".apps.apple.com"):
                match = re.search(r"/id(\d+)(?:[/?#]|$)", parsed.path + "/")
                app_id = match.group(1) if match else ""
                platform = "app_store"
            else:
                raise ValueError(f"不支持的商店链接：{raw[:120]}")
        elif raw.isdigit():
            platform, app_id = "app_store", raw
        else:
            platform, app_id = "google_play", raw
        if not app_id or len(app_id) > 200 or not re.fullmatch(r"[A-Za-z0-9_.-]+", app_id):
            raise ValueError(f"无法识别应用 ID：{raw[:120]}")
        source_url = (
            f"https://play.google.com/store/apps/details?id={app_id}"
            if platform == "google_play"
            else f"https://apps.apple.com/app/id{app_id}"
        )
        return {"platform": platform, "app_id": app_id, "source_url": source_url}

    def start_competitor_collection(self, project_id, payload):
        """Queue a user-supplied competitor list; discovery is intentionally excluded."""
        self.project(project_id)
        if not isinstance(payload, dict):
            raise ValueError("采集参数无效。")
        product_version = self.version_service.resolve(project_id, payload.get("version_id", ""))
        raw_entries = payload.get("entries") or []
        if isinstance(raw_entries, str):
            raw_entries = raw_entries.splitlines()
        if not isinstance(raw_entries, list):
            raise ValueError("竞品列表格式无效。")
        entries, seen = [], set()
        for raw in raw_entries:
            if not str(raw or "").strip():
                continue
            entry = self._parse_competitor_entry(raw)
            key = (entry["platform"], entry["app_id"])
            if key not in seen:
                seen.add(key)
                entries.append(entry)
        if not entries or len(entries) > 8:
            raise ValueError("请提供 1–8 个由你确认的竞品链接或应用 ID。")
        raw_countries = payload.get("countries", [])
        if isinstance(raw_countries, str):
            raw_countries = re.split(r"[,，\s]+", raw_countries)
        countries = []
        for value in raw_countries if isinstance(raw_countries, list) else []:
            country = str(value).strip().lower()
            if country and country not in countries:
                countries.append(country)
        if not countries or len(countries) > 20 or any(not re.fullmatch(r"[a-z]{2}", item) for item in countries):
            raise ValueError("至少提供一个两位国家代码，最多 20 个。")
        try:
            count = int(payload.get("count_per_country", 100))
        except (TypeError, ValueError) as exc:
            raise ValueError("每个国家的评论数量必须是数字。") from exc
        if count < 1 or count > 500:
            raise ValueError("每个国家最多采集 500 条评论。")
        sort = str(payload.get("sort", "newest")).strip()
        if sort not in {"newest", "relevant"}:
            raise ValueError("评论排序只支持最新或相关。")
        date_from = self._scrape_date(payload.get("date_from"), "开始日期")
        date_to = self._scrape_date(payload.get("date_to"), "结束日期")
        if date_from and date_to and date_from > date_to:
            raise ValueError("开始日期不能晚于结束日期。")
        if self.rows("SELECT id FROM scrapes WHERE project_id=? AND status IN ('queued','running') LIMIT 1", (project_id,)):
            raise ValueError("当前项目已有竞品采集任务执行中，请等待完成。")
        stamp = now()
        scrape_ids = []
        with self.db() as db:
            for entry in entries:
                scrape_id = uid()
                request = {
                    **entry,
                    "countries": countries,
                    "count_per_country": min(100, count) if entry["platform"] == "app_store" else count,
                    "sort": sort,
                    "date_from": date_from,
                    "date_to": date_to,
                    "version_id": product_version["id"] if product_version else "",
                    "collect_listing": True,
                    "translate": bool(payload.get("translate", True)),
                    "translation_batch_size": 20,
                    "requires_confirmation": True,
                }
                db.execute(
                    "INSERT INTO scrapes(id,project_id,platform,app_id,request,status,result_doc_id,created,updated,error,version_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (scrape_id, project_id, entry["platform"], entry["app_id"], json.dumps(request, ensure_ascii=False), "queued", "", stamp, stamp, "", product_version["id"] if product_version else ""),
                )
                scrape_ids.append(scrape_id)
        worker = threading.Thread(target=self._run_collection_batch, args=(scrape_ids,), daemon=True)
        for scrape_id in scrape_ids:
            self.scrape_threads[scrape_id] = worker
        worker.start()
        return {"count": len(scrape_ids), "items": [self.scrape(item) for item in scrape_ids]}

    def _run_collection_batch(self, scrape_ids):
        for scrape_id in scrape_ids:
            try:
                if self.scrape(scrape_id)["status"] != "cancelled":
                    self._run_review_scrape(scrape_id)
            except ValueError:
                continue

    @staticmethod
    def _listing_markdown(listing):
        platform = "Google Play" if listing.get("platform") == "google_play" else "App Store"
        yes_no = lambda value: "是" if value is True else "否" if value is False else "未提供"
        return "\n".join([
            f"# {listing.get('title') or listing.get('app_id') or '竞品'}商店信息",
            "",
            f"- 平台：{platform}",
            f"- 应用 ID：{listing.get('app_id') or '未提供'}",
            f"- 市场：{listing.get('market') or '未提供'}",
            f"- 语言：{listing.get('language') or '未提供'}",
            f"- 开发者：{listing.get('developer') or '未提供'}",
            f"- 分类：{listing.get('category') or '未提供'}",
            f"- 评分：{listing.get('rating') if listing.get('rating') not in (None, '') else '未提供'}",
            f"- 评分数量：{listing.get('rating_count') if listing.get('rating_count') not in (None, '') else '未提供'}",
            f"- 安装量：{listing.get('installs') or '未提供'}",
            f"- 当前版本：{listing.get('version') or '未提供'}",
            f"- 商店更新时间：{listing.get('updated') or '未提供'}",
            f"- 包含广告：{yes_no(listing.get('contains_ads'))}",
            f"- 提供应用内购买：{yes_no(listing.get('offers_iap'))}",
            f"- 来源：{listing.get('source_url') or '未提供'}",
            f"- 采集时间：{listing.get('collected_at') or now()}",
            "",
            "## 短描述",
            "",
            str(listing.get("short_description") or "当前商店接口未提供短描述。"),
            "",
            "## Promotional Text",
            "",
            str(listing.get("promotional_text") or "当前商店接口未提供 Promotional Text。"),
            "",
            "## 长描述",
            "",
            str(listing.get("long_description") or "当前商店接口未提供长描述。"),
            "",
            "## 证据说明",
            "",
            "以上字段是指定市场商店页面的采集快照；未提供字段保持为空，不使用模型补写或翻译。",
        ])

    def _stage_collection_result(self, scrape, request, result, directory):
        listing = result.get("listing") if isinstance(result.get("listing"), dict) else None
        reviews = result.get("reviews") if isinstance(result.get("reviews"), list) else []
        warnings = [str(item)[:300] for item in (result.get("warnings") or []) if str(item).strip()]
        if listing:
            (directory / "store-listing.json").write_text(json.dumps(listing, ensure_ascii=False, indent=2), encoding="utf-8")
            (directory / "store-listing.md").write_text(self._listing_markdown(listing), encoding="utf-8")
        if reviews:
            csv_content = self._review_csv(reviews)
            if len(csv_content) > MAX_FILE:
                raise ValueError("评论 CSV 超过 12 MB，请减少国家数量或每国条数后重试。")
            (directory / "reviews.csv").write_bytes(csv_content)
        if not listing and not reviews:
            return None
        manifest = {
            "schema": 1,
            "project_id": scrape["project_id"],
            "scrape_id": scrape["id"],
            "platform": scrape["platform"],
            "app_id": scrape["app_id"],
            "version_id": scrape.get("version_id", ""),
            "listing": listing or {},
            "review_count": len(reviews),
            "translated_count": sum(
                bool(str(item.get("translated_content") or "").strip())
                for item in reviews
                if isinstance(item, dict)
            ),
            "warnings": warnings,
            "created_at": now(),
        }
        (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def confirm_competitor_collection(self, scrape_id):
        """Import a staged competitor evidence pack only after user confirmation."""
        with self.lock:
            scrape = self.scrape(scrape_id)
            if scrape["status"] != "ready":
                raise ValueError("只有待确认的竞品资料可以入库。")
            directory = self._collection_directory(scrape).resolve()
            manifest = self._collection_manifest(scrape)
            listing = manifest.get("listing") if isinstance(manifest.get("listing"), dict) else {}
            if not directory.is_dir() or not manifest:
                raise ValueError("竞品采集暂存资料不存在，请重新采集。")
            files = []
            for filename, relation in (("store-listing.md", "competitor-listing"), ("reviews.csv", "review-evidence")):
                path = (directory / filename).resolve()
                if path.is_relative_to(directory) and path.is_file():
                    files.append((path, relation))
            screenshots = directory / "screenshots"
            if screenshots.is_dir():
                for path in sorted(screenshots.iterdir()):
                    resolved = path.resolve()
                    if resolved.is_relative_to(screenshots.resolve()) and resolved.suffix.lower() in IMAGE_SUFFIXES and resolved.is_file():
                        files.append((resolved, "competitor-screenshot"))
            if not files:
                raise ValueError("竞品采集没有可入库的资料。")
            prepared = []
            for path, relation in files:
                content = path.read_bytes()
                if not content or len(content) > MAX_FILE:
                    raise ValueError(f"暂存文件无效或超过 12 MB：{path.name}")
                extract(path.name, content)
                prepared.append((path, relation, content))
            safe_title = self._safe_export_name(str(listing.get("title") or scrape["app_id"]))[:60]
            market = self._safe_export_name(str(listing.get("market") or "GLOBAL"))[:12]
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            document_ids, listing_doc_id, review_doc_id, image_index = [], "", "", 0
            for path, relation, content in prepared:
                if path.name == "store-listing.md":
                    name = f"竞品商店信息-{safe_title}-{market}-{stamp}.md"
                elif path.name == "reviews.csv":
                    name = f"竞品评论-{safe_title}-{market}-{stamp}.csv"
                else:
                    image_index += 1
                    name = f"竞品截图-{safe_title}-{market}-{image_index:02d}{path.suffix.lower()}"
                document = self.add_document(scrape["project_id"], name, content, scrape.get("version_id", ""), relation)
                document_ids.append(document["id"])
                if path.name == "store-listing.md":
                    listing_doc_id = document["id"]
                elif path.name == "reviews.csv":
                    review_doc_id = document["id"]
            manifest["document_ids"] = document_ids
            manifest["listing_document_id"] = listing_doc_id
            manifest["review_document_id"] = review_doc_id
            (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            self._update_scrape(
                scrape_id,
                status="completed",
                result_doc_id=review_doc_id or listing_doc_id or document_ids[0],
                updated=now(),
            )
        return self.scrape(scrape_id)

    def retry_scrape(self, scrape_id):
        old = self.scrape(scrape_id)
        if old["status"] not in {"failed", "empty", "cancelled"}:
            raise ValueError("只有失败、空结果或已取消的采集可以重试。")
        if self.rows("SELECT id FROM scrapes WHERE project_id=? AND status IN ('queued','running') LIMIT 1", (old["project_id"],)):
            raise ValueError("当前项目已有竞品采集任务执行中，请等待完成。")
        request = json.loads(old.get("request") or "{}")
        new_id, stamp = uid(), now()
        with self.db() as db:
            db.execute(
                "INSERT INTO scrapes(id,project_id,platform,app_id,request,status,result_doc_id,created,updated,error,version_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (new_id, old["project_id"], old["platform"], old["app_id"], json.dumps(request, ensure_ascii=False), "queued", "", stamp, stamp, "", old.get("version_id", "")),
            )
        worker = threading.Thread(target=self._run_review_scrape, args=(new_id,), daemon=True)
        self.scrape_threads[new_id] = worker
        worker.start()
        return self.scrape(new_id)

    @staticmethod
    def _review_csv(reviews):
        fields = (
            "review_id", "content", "score", "published_at", "market", "language",
            "version", "source", "platform", "app_id", "thumbs_up_count", "user_name",
            "title", "original_content", "translated_content", "reply_content", "reply_at",
        )
        result = io.StringIO(newline="")
        writer = csv.DictWriter(result, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in reviews:
            values = {}
            for field in fields:
                value = row.get(field, "") if isinstance(row, dict) else ""
                if value is None:
                    value = ""
                elif isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                value = str(value)
                # Prevent spreadsheet formula execution when a review starts with
                # a formula marker. The source text remains visibly intact.
                if value[:1] in {"=", "+", "-", "@"}:
                    value = "'" + value
                values[field] = value
            writer.writerow(values)
        return b"\xef\xbb\xbf" + result.getvalue().encode("utf-8")

    def _translate_items(self, items):
        """Run translation inside the configured desktop tool environment."""
        settings = self.review_scraper_settings()
        if not settings["ready"] or not settings["enabled"]:
            raise ValueError(settings["message"])
        command = [settings["python"], str(HERE / "review_scraper_worker.py")]
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        payload = {
            "mode": "translate",
            "root": settings["root"],
            "batch_size": 20,
            "items": items,
        }
        try:
            completed = subprocess.run(
                command,
                input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=settings["root"],
                env=env,
                timeout=900,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("评论翻译超过 15 分钟，已停止；原始 CSV 未改动。") from exc
        try:
            result = json.loads(completed.stdout.decode("utf-8", errors="replace").strip().splitlines()[-1])
        except (IndexError, TypeError, ValueError) as exc:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()[:500]
            raise ValueError(detail or "翻译工具没有返回有效结果。") from exc
        if completed.returncode:
            raise ValueError(str(result.get("error") or "评论翻译失败。")[:1000])
        translations = result.get("translations")
        if not isinstance(translations, list) or len(translations) != len(items):
            raise ValueError("翻译结果与原评论数量不一致，原始 CSV 未改动。")
        return result

    def translate_review_document(self, document_id):
        """Fill missing Simplified Chinese translations in an uploaded review CSV."""
        rows = self.rows(
            "SELECT id,project_id,name,sha,kind FROM documents WHERE id=?",
            (str(document_id).strip(),),
        )
        if not rows:
            raise ValueError("评论资料不存在。")
        document = rows[0]
        if document["kind"] != "upload" or Path(document["name"]).suffix.lower() != ".csv":
            raise ValueError("只有已上传的评论 CSV 可以补充翻译。")
        path = self.upload_path(document["project_id"], document["id"], document["name"]).resolve()
        root = (self.data / "uploads" / document["project_id"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("评论 CSV 原文件不存在。")
        original = path.read_bytes()
        try:
            source = original.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                source = original.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise ValueError("CSV 编码无法识别。") from exc
        reader = csv.DictReader(io.StringIO(source))
        fieldnames = list(reader.fieldnames or [])
        normalized = {str(field).strip(): field for field in fieldnames if field is not None}
        if "content" not in normalized and "original_content" not in normalized:
            raise ValueError("CSV 缺少 content 或 original_content 字段。")
        if "translated_content" not in normalized:
            fieldnames.append("translated_content")
            normalized["translated_content"] = "translated_content"
        clean_rows = [
            {field: str(row.get(field) or "") for field in fieldnames}
            for row in reader
        ]
        content_field = normalized.get("original_content") or normalized.get("content")
        language_field = normalized.get("language")
        translated_field = normalized["translated_content"]
        pending = []
        for index, row in enumerate(clean_rows):
            text = str(row.get(content_field) or row.get(normalized.get("content", "")) or "").strip()
            language = str(row.get(language_field) or "").strip() if language_field else ""
            translated = str(row.get(translated_field) or "").strip()
            if translated and translated != "[翻译失败]":
                continue
            if self.material_service._review_needs_translation(text, language):
                pending.append((index, text, language))
        before = sum(
            bool(str(row.get(translated_field) or "").strip())
            and str(row.get(translated_field) or "").strip() != "[翻译失败]"
            for row in clean_rows
        )
        batch = pending[:500]
        if not batch:
            return {
                "document_id": document["id"],
                "total_rows": len(clean_rows),
                "translated_count": before,
                "newly_translated": 0,
                "remaining_count": 0,
                "failed_count": 0,
                "provider": "none",
            }
        result = self._translate_items(
            [{"text": text, "language": language} for _, text, language in batch]
        )
        newly_translated = 0
        for (row_index, _, _), translated in zip(batch, result["translations"]):
            value = str(translated or "").strip()
            if not value:
                continue
            if value[:1] in {"=", "+", "-", "@"}:
                value = "'" + value
            clean_rows[row_index][translated_field] = value
            newly_translated += 1
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(clean_rows)
        content = b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")
        if len(content) > MAX_FILE:
            raise ValueError("翻译后的评论 CSV 超过 12 MB，原文件未改动。")
        extracted = extract(document["name"], content)
        digest = hashlib.sha256(content).hexdigest()
        temporary = path.with_name(f".{path.name}.{uid()}.tmp")
        with self.lock:
            if hashlib.sha256(path.read_bytes()).hexdigest() != hashlib.sha256(original).hexdigest():
                raise ValueError("评论 CSV 已在翻译期间发生变化，请重新打开后再试。")
            try:
                temporary.write_bytes(content)
                os.replace(temporary, path)
                with self.db() as db:
                    db.execute(
                        "UPDATE documents SET text=?,sha=? WHERE id=? AND project_id=?",
                        (extracted, digest, document["id"], document["project_id"]),
                    )
            except Exception:
                path.write_bytes(original)
                raise
            finally:
                temporary.unlink(missing_ok=True)
        remaining = max(0, len(pending) - newly_translated)
        return {
            "document_id": document["id"],
            "total_rows": len(clean_rows),
            "translated_count": before + newly_translated,
            "newly_translated": newly_translated,
            "remaining_count": remaining,
            "failed_count": int(result.get("failed_count") or 0),
            "provider": str(result.get("provider") or ""),
            "warnings": result.get("warnings") or [],
        }

    @staticmethod
    def _scrape_date(value, label):
        value = str(value or "").strip()
        if not value:
            return ""
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{label}格式无效，请使用 YYYY-MM-DD。") from exc
        return value

    def start_review_scrape(self, project_id, payload):
        self.project(project_id)
        if not isinstance(payload, dict):
            raise ValueError("采集参数无效。")
        product_version = self.version_service.resolve(project_id, payload.get("version_id", ""))
        platform = str(payload.get("platform", "google_play")).strip()
        if platform not in {"google_play", "app_store"}:
            raise ValueError("只支持 Google Play 或 App Store。")
        app_id = str(payload.get("app_id", "")).strip()
        if not app_id or len(app_id) > 200 or not re.fullmatch(r"[A-Za-z0-9_.-]+", app_id):
            raise ValueError("应用 ID 无效；Google Play 使用 package name，App Store 使用 app ID。")
        raw_countries = payload.get("countries", payload.get("markets", []))
        if isinstance(raw_countries, str):
            raw_countries = re.split(r"[,，\s]+", raw_countries)
        if not isinstance(raw_countries, list):
            raise ValueError("国家或地区格式无效。")
        countries = []
        for item in raw_countries:
            country = str(item).strip().lower()
            if country and country not in countries:
                countries.append(country)
        if not countries or len(countries) > 20 or any(not re.fullmatch(r"[a-z]{2}", item) for item in countries):
            raise ValueError("至少提供一个两位国家代码，最多 20 个。")
        try:
            count = int(payload.get("count_per_country", 100))
        except (TypeError, ValueError) as exc:
            raise ValueError("每个国家的评论数量必须是数字。") from exc
        if count < 1 or count > 500:
            raise ValueError("每个国家最多采集 500 条评论。")
        sort = str(payload.get("sort", "newest")).strip()
        if sort not in {"newest", "relevant"}:
            raise ValueError("评论排序只支持最新或相关。")
        date_from = self._scrape_date(payload.get("date_from"), "开始日期")
        date_to = self._scrape_date(payload.get("date_to"), "结束日期")
        if date_from and date_to and date_from > date_to:
            raise ValueError("开始日期不能晚于结束日期。")
        active = self.rows(
            "SELECT id FROM scrapes WHERE project_id=? AND status IN ('queued','running') LIMIT 1",
            (project_id,),
        )
        if active:
            raise ValueError("当前项目已有评论采集任务执行中，请等待完成。")
        request = {
            "platform": platform,
            "app_id": app_id,
            "countries": countries,
            "count_per_country": count,
            "sort": sort,
            "date_from": date_from,
            "date_to": date_to,
            "version_id": product_version["id"] if product_version else "",
            "translate": bool(payload.get("translate", False)),
            "translation_batch_size": 20,
        }
        scrape_id = uid()
        stamp = now()
        with self.db() as db:
            db.execute(
                "INSERT INTO scrapes(id,project_id,platform,app_id,request,status,result_doc_id,created,updated,error,version_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (scrape_id, project_id, platform, app_id, json.dumps(request, ensure_ascii=False), "queued", "", stamp, stamp, "", product_version["id"] if product_version else ""),
            )
        worker = threading.Thread(target=self._run_review_scrape, args=(scrape_id,), daemon=True)
        self.scrape_threads[scrape_id] = worker
        worker.start()
        return self.scrape(scrape_id)

    def _update_scrape(self, scrape_id, **values):
        if not values:
            return
        assignments = ",".join(f"{key}=?" for key in values)
        with self.db() as db:
            db.execute(f"UPDATE scrapes SET {assignments} WHERE id=?", (*values.values(), scrape_id))

    def _run_review_scrape(self, scrape_id):
        process = None
        try:
            scrape = self.scrape(scrape_id)
            if scrape["status"] == "cancelled":
                return
            settings = self.review_scraper_settings()
            if not settings["ready"] or not settings["enabled"]:
                raise ValueError(settings["message"])
            request = json.loads(scrape["request"] or "{}")
            request["root"] = settings["root"]
            directory = self.data / "scrapes" / scrape["project_id"] / scrape_id
            directory.mkdir(parents=True, exist_ok=True)
            if request.get("collect_listing"):
                request["output_dir"] = str((directory / "screenshots").resolve())
            (directory / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
            self._update_scrape(scrape_id, status="running", updated=now(), error="")
            command = [settings["python"], str(HERE / "review_scraper_worker.py")]
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            # The desktop scraper may inherit Windows GBK streams.  Force the
            # child process protocol to UTF-8 so emoji/CJK review text cannot
            # make the bridge fail before it returns JSON.
            env["PYTHONIOENCODING"] = "utf-8"
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=settings["root"],
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            with self.lock:
                self.scrape_processes[scrape_id] = process
                if self.scrape(scrape_id)["status"] == "cancelled":
                    self.stop_process(process)
                    return
            stdout, stderr = process.communicate(json.dumps(request, ensure_ascii=False).encode("utf-8"), timeout=1800)
            current = self.scrape(scrape_id)
            if current["status"] == "cancelled":
                return
            try:
                result = json.loads(stdout.decode("utf-8", errors="replace").strip().splitlines()[-1])
            except (IndexError, ValueError, TypeError) as exc:
                detail = stderr.decode("utf-8", errors="replace").strip()[:500]
                raise ValueError(detail or "评论采集器没有返回有效结果。") from exc
            if process.returncode:
                raise ValueError(str(result.get("error") or stderr.decode("utf-8", errors="replace").strip() or "评论采集失败")[:1000])
            reviews = result.get("reviews") if isinstance(result, dict) else None
            if request.get("requires_confirmation"):
                manifest = self._stage_collection_result(scrape, request, result, directory)
                warnings = (result.get("warnings") or []) if isinstance(result, dict) else []
                warning = "；".join(str(item) for item in warnings if str(item).strip())
                if not manifest:
                    self._update_scrape(
                        scrape_id,
                        status="empty",
                        updated=now(),
                        error=warning or "没有采集到商店资料或评论，未生成待确认资料。",
                        review_count=0,
                        warning_count=len(warnings),
                    )
                    return
                if not reviews:
                    warning = "；".join(filter(None, [warning, "没有采集到评论；商店资料仍可确认入库"]))
                self._update_scrape(
                    scrape_id,
                    status="ready",
                    updated=now(),
                    error=warning,
                    review_count=len(reviews or []),
                    warning_count=len(warnings),
                )
                return
            if not isinstance(reviews, list) or not reviews:
                warning = "；".join(str(item) for item in (result.get("warnings") or []) if str(item).strip()) if isinstance(result, dict) else ""
                self._update_scrape(scrape_id, status="empty", updated=now(), error=warning or "没有采集到评论，未写入资料。", review_count=0, warning_count=len(result.get("warnings") or []) if isinstance(result, dict) else 0)
                return
            csv_content = self._review_csv(reviews)
            if len(csv_content) > MAX_FILE:
                raise ValueError("评论 CSV 超过 12 MB，请减少国家数量或每国条数后重试。")
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            safe_app_id = self._safe_export_name(scrape["app_id"])[:60]
            document = self.add_document(
                scrape["project_id"],
                f"竞品评论-{safe_app_id}-{stamp}.csv",
                csv_content,
                scrape.get("version_id", ""),
                "review-evidence",
            )
            warning = "；".join(str(item) for item in (result.get("warnings") or []) if str(item).strip()) if isinstance(result, dict) else ""
            self._update_scrape(
                scrape_id,
                status="completed",
                result_doc_id=document["id"],
                updated=now(),
                error=warning,
                review_count=len(reviews),
                warning_count=len(result.get("warnings") or []) if isinstance(result, dict) else 0,
            )
        except subprocess.TimeoutExpired:
            if process is not None:
                self.stop_process(process)
            if self.scrape(scrape_id)["status"] != "cancelled":
                self._update_scrape(scrape_id, status="failed", updated=now(), error="评论采集超过 30 分钟，已停止。")
        except Exception as exc:  # noqa: BLE001 - persisted for UI visibility
            try:
                if self.scrape(scrape_id)["status"] != "cancelled":
                    self._update_scrape(scrape_id, status="failed", updated=now(), error=str(exc)[:1000])
            except ValueError:
                pass
        finally:
            with self.lock:
                self.scrape_processes.pop(scrape_id, None)
                self.scrape_threads.pop(scrape_id, None)

    def scrape(self, scrape_id):
        rows = self.rows("SELECT * FROM scrapes WHERE id=?", (scrape_id,))
        if not rows:
            raise ValueError("评论采集任务不存在。")
        return self._with_collection_preview(rows[0], include_listing=True)

    def cancel_scrape(self, scrape_id):
        with self.lock:
            scrape = self.scrape(scrape_id)
            if scrape["status"] not in {"queued", "running"}:
                raise ValueError("当前评论采集任务不能取消。")
            self._update_scrape(scrape_id, status="cancelled", updated=now(), error="已由用户取消。")
            process = self.scrape_processes.get(scrape_id)
            if process is not None:
                self.stop_process(process)
        return self.scrape(scrape_id)
