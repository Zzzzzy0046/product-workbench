"""Loopback-only collector UI with server-enforced account and file permissions."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import subprocess
import sys
import threading
from urllib.parse import parse_qs, unquote, urlparse
import uuid
import webbrowser
import zipfile

from competitor_collector import __version__
from competitor_collector.auth import AuthError, AuthStore
from competitor_collector.android_capture import AndroidCaptureService, CaptureError
from competitor_collector.exports import write_evidence
from competitor_collector.request_spec import normalize_request

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
COOKIE = "competitor_collector_session"
IDENTIFIER = re.compile(r"^[a-f0-9]{32}$")
MARKETS = [("us", "美国"), ("gb", "英国"), ("de", "德国"), ("jp", "日本"),
           ("in", "印度"), ("id", "印度尼西亚"), ("br", "巴西"), ("sa", "沙特阿拉伯"),
           ("fr", "法国"), ("ca", "加拿大"), ("au", "澳大利亚"), ("kr", "韩国"),
           ("mx", "墨西哥"), ("th", "泰国"), ("vn", "越南"), ("ae", "阿联酋")]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class HTTPError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def atomic_json(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def linked_path(path):
    """Directory junctions on Windows are links too, not trusted run roots."""
    if path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    # pathlib.Path.is_junction was added in Python 3.12; support the declared
    # Python 3.11 minimum by refusing Windows reparse points as well.
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


class CollectorApp:
    def __init__(self, data_dir, runner=None):
        self.data = Path(data_dir).resolve()
        self.runs = self.data / "runs"
        self.runs.mkdir(parents=True, exist_ok=True)
        self._runs_root()
        self.auth = AuthStore(self.data / "auth.sqlite3")
        self.captures = AndroidCaptureService(self.data)
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="collector")
        self.runner = runner or self._run_engine
        self.processes = set()
        self.jobs = {}
        self.closed = False
        for path in self.runs.glob("*/job.json"):
            if not IDENTIFIER.fullmatch(path.parent.name) or linked_path(path):
                continue
            try:
                root = self._job_root(path.parent.name)
                if path.resolve().parent != root:
                    continue
                job = json.loads(path.read_text(encoding="utf-8"))
                if job.get("id") != path.parent.name or not isinstance(job.get("items"), list) or not job.get("owner_id"):
                    continue
                if any(not isinstance(item, dict) or not IDENTIFIER.fullmatch(str(item.get("id") or "")) for item in job["items"]):
                    continue
                for item in job["items"]:
                    candidate = root / item["id"]
                    if candidate.exists() or linked_path(candidate):
                        self._item_root(job["id"], item["id"])
                if job.get("status") in {"running", "queued"}:
                    job["status"] = "failed"
                    for item in job["items"]:
                        if item.get("status") in {"running", "queued"}:
                            item.update(status="failed", error="服务已重启，本项未完成。请重新发起采集。")
                    job["updated_at"] = now()
                    atomic_json(path, job)
                self.jobs[job["id"]] = job
            except (OSError, ValueError, TypeError):
                continue

    @staticmethod
    def _checked_directory(path, parent):
        if linked_path(path) or not path.is_dir():
            raise HTTPError("采集目录不存在或含不安全链接。", 404)
        resolved = path.resolve(strict=True)
        if resolved.parent != parent.resolve(strict=True):
            raise HTTPError("采集目录不属于当前任务。", 404)
        return resolved

    def _runs_root(self):
        if linked_path(self.data) or self.data.resolve() != self.data:
            raise HTTPError("资料根目录已改变，请检查本机目录。", 404)
        return self._checked_directory(self.runs, self.data)

    def _job_root(self, identifier):
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
            raise HTTPError("记录不存在。", 404)
        return self._checked_directory(self._runs_root() / identifier, self.runs)

    def _item_root(self, identifier, item_id, create=False):
        if not isinstance(item_id, str) or not IDENTIFIER.fullmatch(item_id):
            raise HTTPError("文件不存在。", 404)
        parent = self._job_root(identifier)
        directory = parent / item_id
        if linked_path(directory):
            raise HTTPError("采集目录含不安全链接。", 404)
        if create:
            directory.mkdir(exist_ok=True)
        return self._checked_directory(directory, parent)

    def close(self):
        with self.lock:
            self.closed = True
            for process in list(self.processes):
                if process.poll() is None:
                    process.terminate()
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.captures.close()

    def meta(self):
        return {"version": __version__, "markets": [{"code": code, "label": label} for code, label in MARKETS],
                "defaults": {"count_per_country": 100, "sort": "newest"},
                "capabilities": {"google_play": importlib.util.find_spec("google_play_scraper") is not None,
                                 "app_store": importlib.util.find_spec("requests") is not None,
                                 "translation_google": importlib.util.find_spec("deep_translator") is not None},
                "output_dir": str(self.runs), "isolation": "owner", "local_only": True}

    def _persist(self, job):
        atomic_json(self._job_root(job["id"]) / "job.json", job)

    @staticmethod
    def _may_read(user, job):
        return user["role"] == "admin" or user["id"] == job["owner_id"]

    def jobs_for(self, user):
        with self.lock:
            return deepcopy(sorted((job for job in self.jobs.values() if self._may_read(user, job)),
                                   key=lambda item: item["created_at"], reverse=True)[:100])

    def get_job(self, user, identifier):
        with self.lock:
            job = self.jobs.get(identifier)
            if job is None or not self._may_read(user, job):
                raise HTTPError("记录不存在或无权访问。", 404)
            return deepcopy(job)

    def new_job(self, user, payload):
        try:
            request = normalize_request(payload)
        except ValueError as error:
            # These are deliberately authored request-validation messages, not
            # arbitrary network/provider exceptions.
            raise HTTPError(str(error)) from None
        except TypeError:
            raise HTTPError("请求参数类型无效，请检查筛选项。") from None
        if request.get("translate") and request.get("translation_provider") != "google":
            raise HTTPError("网页翻译目前仅支持显式选择 Google，不在网页配置付费模型。")
        with self.lock:
            if self.closed:
                raise HTTPError("服务正在停止，请稍后重试。", 503)
            active = [job for job in self.jobs.values() if job["status"] in {"queued", "running"}]
            if len(active) >= 8 or sum(job["owner_id"] == user["id"] for job in active) >= 2:
                raise HTTPError("正在采集的任务较多，请等待当前任务结束。", 429)
            identifier = uuid.uuid4().hex
            job = {"id": identifier, "owner_id": user["id"], "owner_name": user["username"], "status": "queued",
                   "total": len(request["entries"]), "completed": 0, "created_at": now(), "updated_at": now(),
                   "request": request, "download_url": f"/api/jobs/{identifier}/archive", "items": []}
            for entry in request["entries"]:
                job["items"].append({"id": uuid.uuid4().hex, **entry, "title": entry["app_id"], "status": "queued",
                                     "review_count": 0, "screenshot_count": 0, "warnings": [], "error": "", "files": {},
                                     "listing": {}, "review_samples": [], "screenshots": []})
            (self._runs_root() / identifier).mkdir()
            self.jobs[identifier] = job
            try:
                self._persist(job)
                self.executor.submit(self._run_job, identifier)
            except Exception:
                job.update(status="failed", completed=job["total"], updated_at=now(), error="无法保存或启动任务，请检查磁盘与目录。")
                for item in job["items"]:
                    item.update(status="failed", error="任务未能启动，未进行采集。")
                try:
                    self._persist(job)
                except Exception:
                    pass
                raise HTTPError("无法保存或启动任务，请检查磁盘与目录。", 503) from None
            return deepcopy(job)

    def _run_engine(self, payload):
        # Isolated process gives each app a hard deadline and avoids desktop
        # module/import state bleeding between tasks. No shell or legacy root.
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PACKAGE_ROOT)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        process = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "competitor_collector.engine"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   cwd=str(PACKAGE_ROOT), env=env,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with self.lock:
            self.processes.add(process)
            if self.closed:
                process.terminate()
        try:
            try:
                stdout, _ = process.communicate(json.dumps(payload, ensure_ascii=True).encode(), timeout=600)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise HTTPError("本应用采集超过 10 分钟，已停止。请减少市场或条数后重新发起。") from None
            try:
                result = json.loads(stdout.decode("utf-8"))
            except (ValueError, UnicodeError):
                raise HTTPError("采集进程未返回有效结果，请检查依赖与网络。") from None
            if not isinstance(result, dict) or process.returncode or result.get("error") or result.get("error_code"):
                # engine only emits deliberate safe errors; arbitrary stderr and
                # proxy/provider diagnostics never enter a page or job record.
                from competitor_collector.engine import _safe_exception_message
                safe = _safe_exception_message(ValueError(str(result.get("error") or ""))) if isinstance(result, dict) else ""
                raise HTTPError(safe or "采集失败，请检查应用 ID、所选市场与网络。")
            return result
        finally:
            with self.lock:
                self.processes.discard(process)

    def _run_job(self, identifier):
        try:
            self._run_job_impl(identifier)
        except Exception:
            # Disk full, directory failures and metadata writes can also fail
            # outside a provider call. Finish in memory even if disk is broken.
            with self.lock:
                job = self.jobs.get(identifier)
                if job is None:
                    return
                for item in job["items"]:
                    if item["status"] in {"queued", "running"}:
                        item.update(status="failed", error="任务保存或目录访问失败，本项已停止。")
                job["completed"] = sum(item["status"] not in {"queued", "running"} for item in job["items"])
                job["status"] = "partial" if any(item["status"] in {"completed", "partial"} for item in job["items"]) else "failed"
                job["error"] = "任务保存或目录访问失败；已保留可用结果，请检查磁盘与目录后重新发起。"
                job["updated_at"] = now()
                try:
                    self._persist(job)
                except Exception:
                    pass

    def _run_job_impl(self, identifier):
        with self.lock:
            job = self.jobs[identifier]
            job["status"] = "running"
            self._persist(job)
        for index in range(job["total"]):
            with self.lock:
                if self.closed:
                    break
                item = job["items"][index]
                item["status"] = "running"
                job["updated_at"] = now()
                self._persist(job)
            try:
                directory = self._item_root(identifier, item["id"], create=True)
                request = {key: value for key, value in job["request"].items() if key != "entries"}
                request.update(platform=item["platform"], app_id=item["app_id"], output_dir=str(directory / "screenshots"))
                result = self.runner(request)
                summary = write_evidence(directory, result, {key: value for key, value in request.items() if key != "output_dir"})
                summary["files"] = {key: f"/files/{identifier}/{item['id']}/{value}" for key, value in summary["files"].items()}
                summary["screenshots"] = [{"name": image["name"], "url": f"/files/{identifier}/{item['id']}/{image['relative_path']}"}
                                          for image in summary["screenshots"]]
                with self.lock:
                    item.update(summary)
            except Exception as error:
                message = str(error) if isinstance(error, HTTPError) else "采集或保存失败，请检查依赖、网络和输出目录。"
                with self.lock:
                    item.update(status="failed", error=message)
            with self.lock:
                job["completed"] += 1
                job["updated_at"] = now()
                self._persist(job)
        with self.lock:
            for item in job["items"]:
                if item["status"] in {"queued", "running"}:
                    item.update(status="failed", error="服务已停止，本项未完成。")
            statuses = [item["status"] for item in job["items"]]
            job["status"] = "completed" if all(status == "completed" for status in statuses) else "failed" if all(status == "failed" for status in statuses) else "partial"
            job["updated_at"] = now()
            self._persist(job)

    def evidence_file(self, user, job_id, item_id, relative):
        if not IDENTIFIER.fullmatch(job_id) or not IDENTIFIER.fullmatch(item_id):
            raise HTTPError("文件不存在。", 404)
        job = self.get_job(user, job_id)
        if item_id not in {item["id"] for item in job["items"]}:
            raise HTTPError("文件不存在。", 404)
        if "\\" in relative or ":" in relative or "\x00" in relative:
            raise HTTPError("文件路径无效。", 404)
        ref = PurePosixPath(relative)
        if ref.is_absolute() or ".." in ref.parts:
            raise HTTPError("文件路径无效。", 404)
        root = self._item_root(job_id, item_id)
        cursor = root
        for part in ref.parts:
            cursor = cursor / part
            if linked_path(cursor):
                raise HTTPError("文件路径含不安全链接。", 404)
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise HTTPError("文件路径无效。", 404) from None
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".csv", ".json", ".md"}:
            raise HTTPError("文件不存在。", 404)
        return path

    def archive(self, user, identifier):
        job = self.get_job(user, identifier)
        if job["status"] in {"queued", "running"}:
            raise HTTPError("任务尚未结束，请完成后下载整包。", 409)
        root = self._job_root(identifier)
        item_directories = []
        for item in job["items"]:
            candidate = root / item["id"]
            if not candidate.exists() and not linked_path(candidate):
                continue
            item_directories.append(self._item_root(identifier, item["id"]))
        # Never ZIP the data root: accounts, session hashes, config and other
        # users' runs cannot accidentally enter a downloaded evidence pack.
        output = root / ("download-" + uuid.uuid4().hex + ".zip")
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for directory in item_directories:
                for current, child_directories, names in os.walk(directory, topdown=True, followlinks=False):
                    current = Path(current)
                    child_directories[:] = [name for name in child_directories if not linked_path(current / name)]
                    for name in names:
                        path = current / name
                        if not path.is_file() or linked_path(path):
                            continue
                        try:
                            path.resolve().relative_to(directory)
                        except ValueError:
                            continue
                        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".csv", ".json", ".md"}:
                            archive.write(path, path.relative_to(root).as_posix())
        return output


class CollectorHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, app):
        if address[0] not in {"127.0.0.1", "localhost"}:
            raise ValueError("当前版本仅允许本机访问；团队部署需另配 HTTPS 与反向代理。")
        self.app = app
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "CompetitorCollector/0.1"

    def log_message(self, format, *args):
        # No request bodies, credentials, query strings or user content in logs.
        pass

    def _headers(self, code, content_type, length, extra=None):
        self.send_response(code)
        for name, value in {"Content-Type": content_type, "Content-Length": str(length),
                            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                            "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                            "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                            **(extra or {})}.items():
            self.send_header(name, value)
        self.end_headers()

    def _json(self, value, code=200, extra=None):
        content = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self._headers(code, "application/json; charset=utf-8", len(content), extra)
        self.wfile.write(content)

    def _file(self, path, attachment=False):
        extra = {"Content-Disposition": 'attachment; filename="' + ("materials.zip" if path.suffix == ".zip" else path.name.encode("ascii", "ignore").decode() or "download") + '"'} if attachment else None
        self._headers(200, mimetypes.guess_type(str(path))[0] or "application/octet-stream", path.stat().st_size, extra)
        with path.open("rb") as stream:
            while block := stream.read(64 * 1024):
                self.wfile.write(block)

    def _host(self):
        port = self.server.server_address[1]
        host = self.headers.get("Host", "")
        if host not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            raise HTTPError("请求来源无效。", 403)
        return host

    def _body(self):
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise HTTPError("需要 JSON 请求。", 415)
        if self.headers.get("Origin") != "http://" + self._host():
            raise HTTPError("跨站请求已拒绝。", 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 64 * 1024:
                raise ValueError()
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeError):
            raise HTTPError("请求内容无效或超过 64 KB。") from None

    def _token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            return cookie[COOKIE].value if COOKIE in cookie else ""
        except Exception:
            return ""

    def _session(self, required=True):
        value = self.server.app.auth.resolve_session(self._token())
        if required and value is None:
            raise HTTPError("请先登录。", 401)
        return value

    def _csrf(self, session):
        if not secrets.compare_digest(str(self.headers.get("X-CSRF-Token", "")), str(session["csrf_token"])):
            raise HTTPError("页面凭证失效，请刷新后重试。", 403)

    def _dispatch(self, method):
        self._host()
        route = urlparse(self.path).path
        app = self.server.app
        if method == "GET" and route == "/health":
            return self._json({"ok": True, "service": "competitor-collector"})
        if method == "GET" and route in {"/", "/app.js", "/screens.js", "/style.css"}:
            return self._file(STATIC / ({"/": "index.html"}.get(route, route[1:])))
        if method == "GET" and route == "/api/session":
            session = self._session(False)
            return self._json({"user": session["user"] if session else None,
                               "csrf_token": session["csrf_token"] if session else None,
                               "setup_required": not app.auth.has_users()})
        if method == "POST" and route == "/api/login":
            payload = self._body()
            session = app.auth.authenticate(payload.get("username", ""), payload.get("password", ""), self.client_address[0])
            cookie = f"{COOKIE}={session['token']}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800"
            return self._json({"user": session["user"], "csrf_token": session["csrf_token"]}, extra={"Set-Cookie": cookie})
        session = self._session()
        user = session["user"]
        if method in {"POST", "PATCH"}:
            payload = self._body()
            self._csrf(session)
        if method == "POST" and route == "/api/logout":
            app.auth.logout(self._token())
            return self._json({"ok": True}, extra={"Set-Cookie": f"{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
        if method == "POST" and route == "/api/password":
            app.auth.change_password(user, payload.get("current_password", ""), payload.get("new_password", ""))
            return self._json({"ok": True}, extra={"Set-Cookie": f"{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
        if route == "/api/users":
            if method == "GET":
                return self._json({"users": app.auth.list_users(user)})
            if method == "POST":
                return self._json({"user": app.auth.create_user(user, payload.get("username", ""), payload.get("password", ""), payload.get("role", "member"))}, 201)
        if method == "PATCH" and route.startswith("/api/users/"):
            changes = {key: payload[key] for key in ("disabled", "role", "password") if key in payload}
            return self._json({"user": app.auth.update_user(user, route.split("/")[-1], **changes)})
        if method == "GET" and route == "/api/meta":
            return self._json(app.meta())
        if method == "GET" and route == "/api/capture/meta":
            return self._json(app.captures.meta())
        if method == "GET" and route == "/api/capture/devices":
            return self._json(app.captures.devices(user))
        if method == "GET" and route == "/api/capture/apps":
            query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
            serials = query.get("serial", [])
            if len(serials) != 1:
                raise HTTPError("请选择一台已连接的 Android 设备。")
            return self._json(app.captures.apps(user, serials[0]))
        if route == "/api/captures":
            if method == "GET":
                return self._json({"captures": app.captures.list_for(user)})
            if method == "POST":
                return self._json({"capture": app.captures.create(user, payload)}, 201)
        match = re.fullmatch(r"/api/captures/([a-f0-9]{32})(?:/(launch|observe|action|label|export|release|resume|archive))?", route)
        if match:
            identifier, operation = match.groups()
            if method == "GET" and operation is None:
                return self._json({"capture": app.captures.get(user, identifier)})
            if method == "GET" and operation == "archive":
                archive = app.captures.archive(user, identifier)
                try:
                    return self._file(archive, True)
                finally:
                    archive.unlink(missing_ok=True)
            if method == "POST" and operation not in {None, "archive"}:
                return self._json({"capture": app.captures.command(user, identifier, operation, payload)})
        match = re.fullmatch(r"/api/captures/([a-f0-9]{32})/files/(.+)", route)
        if method == "GET" and match:
            path = app.captures.file(user, match[1], unquote(match[2]))
            return self._file(path, path.suffix.lower() != ".png")
        if route == "/api/jobs":
            if method == "GET":
                return self._json({"jobs": app.jobs_for(user)})
            if method == "POST":
                return self._json({"job": app.new_job(user, payload)}, 202)
        match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})(/archive)?", route)
        if method == "GET" and match:
            if match[2]:
                archive = app.archive(user, match[1])
                try:
                    return self._file(archive, True)
                finally:
                    archive.unlink(missing_ok=True)
            return self._json({"job": app.get_job(user, match[1])})
        match = re.fullmatch(r"/files/([a-f0-9]{32})/([a-f0-9]{32})/(.+)", route)
        if method == "GET" and match:
            path = app.evidence_file(user, match[1], match[2], unquote(match[3]))
            return self._file(path, path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"})
        raise HTTPError("页面或接口不存在。", 404)

    def _handle(self, method):
        try:
            self._dispatch(method)
        except (HTTPError, AuthError, CaptureError) as error:
            body = {"error": str(error)}
            if isinstance(error, CaptureError):
                if error.record is not None:
                    body["capture"] = error.record
                if error.action_may_have_run:
                    body["action_may_have_run"] = True
            self._json(body, error.status)
        except ValueError as error:
            from competitor_collector.engine import _safe_exception_message
            message = _safe_exception_message(error)
            self._json({"error": message or "请求参数无效，请检查后重试。"}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self._json({"error": "服务处理失败，请检查本机依赖或稍后重试。"}, 500)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PATCH(self):
        self._handle("PATCH")


def serve(data_dir=None, host="127.0.0.1", port=8766, open_browser=False):
    app = CollectorApp(data_dir or PACKAGE_ROOT / "data")
    server = CollectorHTTPServer((host, port), app)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"竞品资料采集器：{url}", flush=True)
    if not app.auth.has_users():
        print("尚未设置管理员。请先运行 python -m competitor_collector init-admin。", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()
