"""Authenticated, explicitly controlled Android screen collection.

Only installed applications can be opened. There is no autonomous exploration,
arbitrary shell, installation, coordinate API, login, payment or permission flow.
SQLite leases protect each physical device across threads and server instances.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import subprocess
import tempfile
from types import SimpleNamespace
from urllib.parse import quote
import uuid
import zipfile

from .capture_runtime import capture_session as runtime
from .capture_runtime import research_map as maps
from .capture_runtime.build_flow_montages import build_montages


MAX_OBSERVATIONS = 200
MAX_MODULES = 50
MAX_ACTIVE = 4
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
_SERIAL = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_PACKAGE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+\Z")
_ID = re.compile(r"[a-f0-9]{32}\Z")
_FILES = {".png", ".xml", ".json", ".md", ".jsonl"}


class CaptureError(Exception):
    def __init__(self, message, status=400, *, record=None, action_may_have_run=False):
        super().__init__(message)
        self.status = status
        self.record = record
        self.action_may_have_run = action_may_have_run


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _process_stamp(pid):
    """Identify a living process without sending a signal on Windows."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *[ctypes.POINTER(wintypes.FILETIME)] * 4]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return None
            try:
                code = wintypes.DWORD()
                if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
                    return None
                values = [wintypes.FILETIME() for _ in range(4)]
                if not kernel.GetProcessTimes(handle, *[ctypes.byref(item) for item in values]):
                    return "alive"
                return str((values[0].dwHighDateTime << 32) | values[0].dwLowDateTime)
            finally:
                kernel.CloseHandle(handle)
        probe = Path(f"/proc/{pid}/stat")
        if probe.is_file():
            return probe.read_text().rsplit(")", 1)[1].split()[19]
        os.kill(pid, 0)
        return "alive"
    except (OSError, ValueError, IndexError):
        return None


def _linked(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _trusted_adb(explicit=None):
    candidates = [explicit, os.environ.get("COLLECTOR_ADB_PATH"), shutil.which("adb"), shutil.which("adb.exe")]
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(variable):
            candidates.append(str(Path(os.environ[variable]) / "platform-tools" / "adb.exe"))
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(str(Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk" / "platform-tools" / "adb.exe"))
    # Common portable scrcpy layout used by this local tool. Discovery is narrow
    # and never recursively searches arbitrary disks or accepts an API path.
    portable = Path.home() / "Desktop" / "Tools"
    if portable.is_dir():
        candidates.extend(str(path) for pattern in ("scrcpy*/adb.exe", "scrcpy*/scrcpy*/adb.exe") for path in sorted(portable.glob(pattern))[:20])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    return None


class AndroidCaptureService:
    def __init__(self, data_dir, adb_path=None):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.root = self.data_dir / "captures"
        if _linked(self.root):
            raise CaptureError("截图资料目录不能是符号链接或目录联接。")
        self.root.mkdir(exist_ok=True)
        self.db_path = self.data_dir / "captures.sqlite3"
        if _linked(self.db_path):
            raise CaptureError("截图任务数据库不能是符号链接。")
        self.adb_path = _trusted_adb(adb_path)
        self.instance_id = uuid.uuid4().hex
        self._closed = False
        self.pid = os.getpid()
        self.process_stamp = _process_stamp(self.pid) or "alive"
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS captures (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, serial TEXT NOT NULL,
                    status TEXT NOT NULL, metadata TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS capture_leases (
                    serial TEXT PRIMARY KEY, capture_id TEXT NOT NULL,
                    instance_id TEXT NOT NULL, pid INTEGER NOT NULL, process_stamp TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS capture_operations (
                    key TEXT PRIMARY KEY, token TEXT NOT NULL, instance_id TEXT NOT NULL,
                    pid INTEGER NOT NULL, process_stamp TEXT NOT NULL);
            """)
        with self._transaction() as db:
            self._recover(db)

    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=3, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def close(self):
        """Release only this service instance's leases during clean shutdown."""
        if self._closed:
            return
        self._closed = True
        with self._transaction() as db:
            for row in db.execute("SELECT capture_id FROM capture_leases WHERE instance_id=?", (self.instance_id,)).fetchall():
                stored = db.execute("SELECT metadata FROM captures WHERE id=?", (row["capture_id"],)).fetchone()
                if stored:
                    record = json.loads(stored["metadata"])
                    record.update(status="paused", warning="服务已关闭，设备已释放；请恢复后重新观察。", updated_at=_now())
                    self._store(db, record)
            db.execute("DELETE FROM capture_leases WHERE instance_id=?", (self.instance_id,))

    @contextmanager
    def _transaction(self):
        with closing(self._connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except sqlite3.OperationalError as exc:
                db.rollback()
                raise CaptureError("采集状态正在更新，请稍后重试。", 409) from exc
            except BaseException:
                db.rollback()
                raise

    def _recover(self, db):
        for row in db.execute("SELECT * FROM capture_leases").fetchall():
            if _process_stamp(row["pid"]) != row["process_stamp"]:
                stored = db.execute("SELECT metadata FROM captures WHERE id=?", (row["capture_id"],)).fetchone()
                if stored:
                    record = json.loads(stored["metadata"])
                    record.update(status="paused", warning="服务已重启，设备控制已暂停；请显式恢复后重新观察。", updated_at=_now())
                    self._store(db, record)
                db.execute("DELETE FROM capture_leases WHERE serial=?", (row["serial"],))
        for row in db.execute("SELECT * FROM capture_operations").fetchall():
            if _process_stamp(row["pid"]) != row["process_stamp"]:
                db.execute("DELETE FROM capture_operations WHERE key=?", (row["key"],))
        # An active row without a lease can only result from an interrupted old
        # version/write; never silently reclaim a device on a GET request.
        for row in db.execute("SELECT metadata FROM captures WHERE status='active' AND id NOT IN (SELECT capture_id FROM capture_leases)").fetchall():
            record = json.loads(row["metadata"])
            record.update(status="paused", warning="设备租约已失效；请恢复并重新观察。", updated_at=_now())
            self._store(db, record)

    @staticmethod
    def _user(user):
        if not isinstance(user, Mapping) or not isinstance(user.get("id"), str) or not user["id"] or user.get("disabled"):
            raise CaptureError("请先登录。", 401)
        if user.get("role") not in {"admin", "member"}:
            raise CaptureError("账号角色无效。", 403)
        return user

    @staticmethod
    def _serial(serial):
        if not isinstance(serial, str) or not _SERIAL.fullmatch(serial):
            raise CaptureError("请选择有效的已连接 Android 设备。")
        return serial

    def _root(self, identifier):
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
            raise CaptureError("找不到截图任务。", 404)
        target = self.root / identifier
        if _linked(self.root) or _linked(target):
            raise CaptureError("截图目录不能是符号链接或目录联接。", 403)
        if any(_linked(target / name) for name in ("observations", "research-map.json", "capture-session.json", "timings.jsonl", "app-map.md", "flow_export")):
            raise CaptureError("截图资料不能使用链接文件或目录联接。", 403)
        return target

    def _load(self, user, identifier, *, control=False):
        self._user(user)
        self._root(identifier)
        with closing(self._connect()) as db:
            row = db.execute("SELECT metadata FROM captures WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise CaptureError("找不到截图任务。", 404)
        record = json.loads(row["metadata"])
        owner = record["owner_id"] == user["id"]
        if not owner and (control or user["role"] != "admin"):
            raise CaptureError("你无权操作此截图任务。" if control else "找不到截图任务。", 403 if control else 404)
        return record

    @staticmethod
    def _store(db, record):
        db.execute("INSERT INTO captures(id,owner_id,serial,status,metadata) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,metadata=excluded.metadata",
                   (record["id"], record["owner_id"], record["serial"], record["status"], json.dumps(record, ensure_ascii=False)))

    def _save(self, record):
        record["updated_at"] = _now()
        with self._transaction() as db:
            self._store(db, record)

    @contextmanager
    def _operation(self, identifier=None, serial=None):
        if self._closed:
            raise CaptureError("截图服务已关闭。", 409)
        keys = (["capture:" + identifier] if identifier else []) + (["device:" + serial] if serial else [])
        token = uuid.uuid4().hex
        with self._transaction() as db:
            self._recover(db)
            if any(db.execute("SELECT 1 FROM capture_operations WHERE key=?", (key,)).fetchone() for key in keys):
                raise CaptureError("该设备或任务正在执行操作，请等待完成，不要重复点击。", 409)
            for key in keys:
                db.execute("INSERT INTO capture_operations VALUES(?,?,?,?,?)", (key, token, self.instance_id, self.pid, self.process_stamp))
        try:
            if serial:
                # Shared with the standalone screenshot skill CLI, so another
                # copied collector/data directory cannot issue simultaneous UI
                # actions on the same physical device either.
                with runtime.device_lock(serial):
                    yield
            else:
                yield
        except runtime.CaptureError as exc:
            raise CaptureError(str(exc), 409) from None
        finally:
            with self._transaction() as db:
                db.execute("DELETE FROM capture_operations WHERE token=?", (token,))

    def _run(self, args):
        if not self.adb_path:
            raise CaptureError("未找到 ADB。请安装 Android platform-tools，并将 adb 加入 PATH 或在本机配置 COLLECTOR_ADB_PATH。", 503)
        try:
            result = subprocess.run([self.adb_path, *args], capture_output=True, timeout=15,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            raise CaptureError("ADB 响应超时，请检查 USB 连接后重试。", 409) from None
        except OSError:
            raise CaptureError("无法启动 ADB，请检查本机安装和路径。", 503) from None
        if result.returncode:
            raise CaptureError("ADB 命令失败，请检查设备连接和 USB 调试授权。", 409)
        if len(result.stdout) > 8 * 1024 * 1024:
            raise CaptureError("设备返回内容过大，已中止本次读取。", 409)
        return result.stdout.decode("utf-8", "replace")

    def meta(self):
        return {"available": bool(self.adb_path), "platform": "Android", "adb_path": self.adb_path,
                "instructions": "连接已开启 USB 调试的 Android 真机或模拟器，在设备上授权本机；竞品 App 需提前安装。iOS 真机自动采集暂不支持。",
                "limits": {"observations": MAX_OBSERVATIONS, "modules": MAX_MODULES, "active_sessions": MAX_ACTIVE},
                "mode": "explicit_snapshot_control", "automatic_exploration": False}

    def devices(self, user):
        self._user(user)
        raw = self._run(["devices", "-l"])
        devices = []
        with closing(self._connect()) as db:
            occupied = {row["serial"] for row in db.execute("SELECT serial FROM capture_leases")}
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) < 2 or not _SERIAL.fullmatch(parts[0]) or parts[1] not in {"device", "offline", "unauthorized", "recovery", "sideload", "bootloader"}:
                continue
            model = next((item[6:].replace("_", " ") for item in parts[2:] if item.startswith("model:")), "")
            devices.append({"serial": parts[0], "state": parts[1], "model": model, "busy": parts[0] in occupied})
        return {"devices": devices, "warning": "设备未授权时，请在设备上手动同意 USB 调试。"}

    def _ready(self, user, serial, *, details=False):
        serial = self._serial(serial)
        device = next((item for item in self.devices(user)["devices"] if item["serial"] == serial and item["state"] == "device"), None)
        if not device:
            raise CaptureError("设备未连接或尚未授权 USB 调试。", 409)
        return device if details else serial

    def apps(self, user, serial):
        serial = self._ready(user, serial)
        with self._operation(serial=serial):
            raw = self._run(["-s", serial, "shell", "pm", "list", "packages", "-3"])
        packages = sorted({line[8:].strip() for line in raw.splitlines() if line.startswith("package:") and _PACKAGE.fullmatch(line[8:].strip())})
        return {"apps": [{"package": package} for package in packages], "serial": serial}

    def _url(self, identifier, relative):
        return f"/api/captures/{identifier}/files/" + quote(relative, safe="/-._~")

    def _view(self, record, user):
        result = {key: record.get(key) for key in ("id", "title", "serial", "package", "model", "app_version", "version_code", "owner_id", "owner_name", "status", "created_at", "updated_at", "warning", "error")}
        result["can_control"] = record["owner_id"] == user["id"]
        root = self._root(record["id"])
        mapping = maps.load_map(self._safe_file(root, "research-map.json"))
        result.update(modules=mapping["modules"], pages=mapping["pages"])
        result["states"] = [{**state, "screenshot_url": self._url(record["id"], state["screenshot"])} for state in mapping["states"]]
        result["transitions"] = mapping["transitions"]
        result["flows"] = [{"title": flow["title"], "url": self._url(record["id"], flow["file"])} for flow in record.get("flows", [])]
        result["download_url"] = f"/api/captures/{record['id']}/archive"
        result["map_url"] = self._url(record["id"], "app-map.md") if (root / "app-map.md").is_file() else None
        result["observation"] = None
        identifier = record.get("observation_id")
        if identifier and re.fullmatch(r"obs-[a-f0-9]{16}", identifier):
            path = root / "observations" / (identifier + ".json")
            if path.is_file():
                path = self._safe_file(root, "observations/" + identifier + ".json")
                observation = json.loads(path.read_text(encoding="utf-8"))
                result["observation"] = {key: observation.get(key) for key in ("id", "status", "activity", "actionable", "captured_at", "ui_error", "previous_observation_id")}
                result["observation"]["clickables"] = []
                for node in observation.get("clickables", []):
                    context = runtime.clickable_context(observation.get("nodes", []), node)
                    labels = list(dict.fromkeys(value.strip() for item in context for value in (item.get("text", ""), item.get("content-desc", "")) if value.strip()))
                    blocked = runtime.tap_block_reason(observation.get("nodes", []), node)
                    result["observation"]["clickables"].append({"index": node["index"], "text": " · ".join(labels)[:240], "content_desc": node.get("content-desc", ""), "resource_id": node.get("resource-id", ""), "bounds": node.get("bounds", ""), "safe": not bool(blocked), "blocked": bool(blocked), "blocked_reason": blocked})
                result["observation"]["screenshot_url"] = self._url(record["id"], observation["files"]["screenshot"])
                result["observation"]["actionable"] = bool(observation.get("actionable")) and not record.get("error") and record["status"] == "active"
                result["observation"]["labelled"] = any(item["observation_id"] == identifier for item in mapping["states"])
        result["observation_count"] = len(list((root / "observations").glob("obs-*.json")))
        return result

    def list_for(self, user):
        self._user(user)
        with closing(self._connect()) as db:
            rows = db.execute("SELECT metadata FROM captures" if user["role"] == "admin" else "SELECT metadata FROM captures WHERE owner_id=?", () if user["role"] == "admin" else (user["id"],)).fetchall()
        return [self._view(record, user) for record in sorted((json.loads(row["metadata"]) for row in rows), key=lambda item: item["updated_at"], reverse=True)]

    def get(self, user, identifier):
        return self._view(self._load(user, identifier), user)

    def create(self, user, payload):
        self._user(user)
        if not isinstance(payload, Mapping):
            raise CaptureError("截图任务参数必须是对象。")
        device = self._ready(user, payload.get("serial"), details=True)
        serial = device["serial"]
        package = payload.get("package")
        if not isinstance(package, str) or len(package) > 200 or not _PACKAGE.fullmatch(package):
            raise CaptureError("请选择已安装的应用包名。")
        title = self._title(payload.get("title") or package, "任务名称")
        identifier = uuid.uuid4().hex
        record = {"id": identifier, "serial": serial, "package": package, "title": title,
                  "model": device["model"] or "未知", "app_version": "未知（设备未返回）", "version_code": None,
                  "owner_id": user["id"], "owner_name": user.get("username", ""), "status": "active", "created_at": _now(), "updated_at": _now(), "flows": []}
        with self._operation(serial=serial):
            installed = self._run(["-s", serial, "shell", "pm", "list", "packages", "-3"])
            if "package:" + package not in {line.strip() for line in installed.splitlines()}:
                raise CaptureError("目标应用未安装；请先手动安装后再创建任务。")
            try:
                version = self._run(["-s", serial, "shell", "dumpsys", "package", package])
                name_match = re.search(r"\bversionName=([^\s]+)", version)
                code_match = re.search(r"\bversionCode=(\d+)", version)
                if name_match:
                    record["app_version"] = name_match[1][:120]
                if code_match:
                    record["version_code"] = code_match[1][:30]
                if not name_match:
                    record["warning"] = "已确认安装；设备未返回应用版本名称，版本记为未知。"
            except CaptureError:
                record["warning"] = "已确认安装，但版本信息读取失败；版本记为未知，不补猜版本。"
            with self._transaction() as db:
                if db.execute("SELECT 1 FROM capture_leases WHERE serial=?", (serial,)).fetchone():
                    raise CaptureError("该设备已被另一个截图任务占用，请先释放原任务。", 409)
                if db.execute("SELECT COUNT(*) FROM capture_leases").fetchone()[0] >= MAX_ACTIVE:
                    raise CaptureError("同时最多开启 4 个截图会话，请先释放不用的会话。", 409)
                if db.execute("SELECT COUNT(*) FROM captures WHERE owner_id=?", (user["id"],)).fetchone()[0] >= 100:
                    raise CaptureError("单账号最多保留 100 个截图任务。", 409)
                root = self._root(identifier)
                root.mkdir()
                (root / "observations").mkdir()
                maps.save_map(root / "research-map.json", maps.create_map(package, serial))
                db.execute("INSERT INTO capture_leases VALUES(?,?,?,?,?)", (serial, identifier, self.instance_id, self.pid, self.process_stamp))
                self._store(db, record)
        # Creation leases the device only; opening/screenshotting requires the
        # user's separate launch/observe command and is never a GET side effect.
        return self._view(record, user)

    @staticmethod
    def _title(value, label):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80 or any(ord(ch) < 32 for ch in value):
            raise CaptureError(label + "须为 1–80 个字符，不能包含换行或控制字符。")
        return value.strip()

    def _active(self, record):
        with closing(self._connect()) as db:
            row = db.execute("SELECT capture_id,instance_id FROM capture_leases WHERE serial=?", (record["serial"],)).fetchone()
        if record["status"] != "active" or not row or row["capture_id"] != record["id"]:
            raise CaptureError("截图会话已暂停，请先恢复，再重新观察。", 409)
        if row["instance_id"] != self.instance_id:
            raise CaptureError("此会话由另一个采集器实例持有，请显式恢复后再操作。", 409)

    def _session(self, record):
        if not self.adb_path:
            raise CaptureError("未找到本机 ADB，请先安装 Android platform-tools。", 503)
        return runtime.CaptureSession(runtime.AdbClient(self.adb_path, record["serial"], timeout=10), self._root(record["id"]), record["package"])

    def _observation_limit(self, root):
        if len(list((root / "observations").glob("obs-*.png"))) >= MAX_OBSERVATIONS:
            raise CaptureError("本任务已达到 200 次观察上限，请导出并新建任务。", 409)

    def command(self, user, identifier, operation, payload=None):
        self._user(user)
        admin_release = operation == "release" and user.get("role") == "admin"
        record = self._load(user, identifier, control=not admin_release)
        payload = {} if payload is None else payload
        if not isinstance(payload, Mapping):
            raise CaptureError("截图操作参数必须是对象。")
        if operation not in {"launch", "observe", "action", "label", "export", "release", "resume"}:
            raise CaptureError("不支持此截图操作。")
        is_device = operation in {"launch", "observe", "action", "release", "resume"}
        with self._operation(identifier, record["serial"] if is_device else None):
            record = self._load(user, identifier, control=not admin_release)
            root = self._root(identifier)
            if operation == "release":
                with self._transaction() as db:
                    db.execute("DELETE FROM capture_leases WHERE capture_id=?", (identifier,))
                    record.update(status="paused", warning="设备已释放；恢复后需重新观察。", error=None, updated_at=_now())
                    self._store(db, record)
            elif operation == "resume":
                self._ready(user, record["serial"])
                with self._transaction() as db:
                    lease = db.execute("SELECT capture_id FROM capture_leases WHERE serial=?", (record["serial"],)).fetchone()
                    if lease and lease["capture_id"] != identifier:
                        raise CaptureError("该设备正被其他任务占用。", 409)
                    if not lease and db.execute("SELECT COUNT(*) FROM capture_leases").fetchone()[0] >= MAX_ACTIVE:
                        raise CaptureError("同时最多开启 4 个截图会话。", 409)
                    db.execute("INSERT OR REPLACE INTO capture_leases VALUES(?,?,?,?,?)", (record["serial"], identifier, self.instance_id, self.pid, self.process_stamp))
                    record.update(status="active", observation_id=None, warning="已恢复，请重新观察当前页面。", error=None, updated_at=_now())
                    self._store(db, record)
            elif operation == "label":
                self._label(record, payload)
                self._save(record)
            elif operation == "export":
                self._export(record)
                self._save(record)
            else:
                self._active(record)
                self._observation_limit(root)
                session = self._session(record)
                try:
                    if operation == "launch":
                        resolved = session.client.run(["shell", "cmd", "package", "resolve-activity", "--brief", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", record["package"]], "resolve_activity").decode("utf-8", "replace")
                        components = [line.strip() for line in resolved.splitlines() if re.fullmatch(re.escape(record["package"]) + r"/[A-Za-z0-9_.$]+", line.strip())]
                        if len(components) != 1:
                            raise runtime.CaptureError("未找到唯一启动入口；请在设备上手动打开 App，再点击观察。")
                        session.client.run(["shell", "am", "start", "-n", components[0]], "launch")
                        observation = session.observe()
                    elif operation == "observe":
                        observation = session.observe()
                    else:
                        action = payload.get("action")
                        observation_id = payload.get("observation_id")
                        if record.get("error"):
                            raise CaptureError("上次操作未确认成功，请先重新观察，不要重复操作。", 409)
                        if not isinstance(observation_id, str) or observation_id != record.get("observation_id"):
                            raise CaptureError("此观察已过期，请重新观察当前页面。", 409)
                        if action == "tap" and type(payload.get("index")) is not int:
                            raise CaptureError("点击需要当前观察里的控件编号。")
                        swipe = None
                        if action == "swipe":
                            direction = payload.get("direction")
                            if direction not in {"up", "down", "left", "right"}:
                                raise CaptureError("滑动方向只能为 up、down、left、right。")
                            saved = json.loads((root / "observations" / (observation_id + ".json")).read_text(encoding="utf-8"))
                            from PIL import Image
                            with Image.open(self.file(user, identifier, saved["files"]["screenshot"])) as image:
                                width, height = image.size
                            points = {"up": (.5, .75, .5, .3), "down": (.5, .3, .5, .75), "left": (.75, .5, .25, .5), "right": (.25, .5, .75, .5)}[direction]
                            swipe = [int(value * (width if index % 2 == 0 else height)) for index, value in enumerate(points)]
                        if action not in {"tap", "back", "swipe"}:
                            raise CaptureError("只允许点击、返回和方向滑动。")
                        observation = session.act_observe(observation_id, action, payload.get("index"), swipe)
                    record.update(observation_id=observation["id"], warning=observation.get("ui_error") or None, error=None)
                    self._save(record)
                except (runtime.CaptureError, OSError, ValueError) as exc:
                    may_run = any(item["phase"] in {"tap", "back", "swipe", "launch"} for item in session.client.timings)
                    message = str(exc) if isinstance(exc, runtime.CaptureError) else "采集文件或设备结果处理失败。"
                    record.update(error=message, warning="已保留现有截图。请先重新观察当前位置，不要直接重复上一动作。")
                    self._save(record)
                    raise CaptureError(message, 409, record=self._view(record, user), action_may_have_run=may_run) from None
                finally:
                    with (root / "timings.jsonl").open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps({"at": _now(), "operation": operation, "phases": session.client.timings}, ensure_ascii=False) + "\n")
        return self._view(record, user)

    def _label(self, record, payload):
        root = self._root(record["id"])
        identifier = record.get("observation_id")
        if not identifier:
            raise CaptureError("请先观察并获取一张真实截图。", 409)
        if payload.get("observation_id") != identifier:
            raise CaptureError("标注的截图已过期，请确认当前截图后重新保存。", 409)
        if record.get("error"):
            raise CaptureError("上次操作未成功，请重新观察后再标注。", 409)
        names = [self._title(payload.get(key) or ("默认状态" if key == "state_title" else None), label) for key, label in (("module_title", "模块名称"), ("page_title", "页面名称"), ("state_title", "状态名称"))]
        mapping = maps.load_map(self._safe_file(root, "research-map.json"))
        attached = next((state for state in mapping["states"] if state["observation_id"] == identifier), None)
        if attached:
            page = next(page for page in mapping["pages"] if page["id"] == attached["page_id"])
            module = next(module for module in mapping["modules"] if module["id"] == page["module_id"])
            if [module["title"], page["title"], attached["title"]] == names:
                return
            raise CaptureError("这张截图已归档。请重新观察后另存状态，不覆盖原始证据。", 409)
        observation = json.loads(self._safe_file(root, "observations/" + identifier + ".json").read_text(encoding="utf-8"))
        module = next((item for item in mapping["modules"] if item["title"] == names[0]), None)
        if module is None:
            if len(mapping["modules"]) >= MAX_MODULES:
                raise CaptureError("每个任务最多 50 个模块。", 409)
            module = {"id": f"m{len(mapping['modules']) + 1:03d}", "title": names[0]}
            maps.add_module(mapping, module["id"], module["title"])
        page = next((item for item in mapping["pages"] if item["module_id"] == module["id"] and item["title"] == names[1]), None)
        if page is None:
            page = {"id": f"p{len(mapping['pages']) + 1:03d}", "title": names[1]}
            maps.add_page(mapping, page["id"], module["id"], page["title"])
        state_id = f"s{len(mapping['states']) + 1:03d}"
        maps.attach_observation(mapping, observation, module["id"], page["id"], state_id, names[2], root)
        previous = next((state for state in mapping["states"] if state["observation_id"] == observation.get("previous_observation_id")), None)
        if previous and observation.get("action"):
            maps.add_transition(mapping, f"t{len(mapping['transitions']) + 1:03d}", previous["id"], state_id, observation["action"], [previous["observation_id"], identifier])
        maps.set_module_status(mapping, module["id"], "partial", "已登记实际截图；未自动声明覆盖完整。")
        maps.save_map(root / "research-map.json", mapping)
        (root / "app-map.md").write_text(maps.render_markdown(mapping), encoding="utf-8")
        record["flows"] = []
        record.update(error=None, warning=None)

    def _export(self, record):
        root = self._root(record["id"])
        mapping = maps.load_map(self._safe_file(root, "research-map.json"))
        if not mapping["states"]:
            raise CaptureError("请先给至少一张截图标注模块、页面和状态。", 409)
        for state in mapping["states"]:
            self._safe_file(root, state["screenshot"])
        # Use a new generated subdirectory each time; no caller-supplied path and
        # no recursive delete of older evidence or external targets.
        relative = "flow_export/" + uuid.uuid4().hex[:12]
        output = root / relative
        outputs = build_montages(SimpleNamespace(input_dir=str(root), research_map=str(root / "research-map.json"), out_dir=str(output), title=record["title"], rows_per_image=3))
        if len(outputs) > 200:
            raise CaptureError("生成图片数量超出上限。", 409)
        (root / "app-map.md").write_text(maps.render_markdown(mapping), encoding="utf-8")
        modules = {module["id"]: module["title"] for module in mapping["modules"]}
        record["flows"] = [{"title": modules[item["module_id"]] + f" · {item['part']}", "file": item["path"].relative_to(root).as_posix()} for item in outputs]
        record["warning"] = "仅拼接已观察并标注的截图，不代表全 App 覆盖。"

    def _safe_file(self, root, relative):
        if not isinstance(relative, str) or not relative or len(relative) > 500 or any(ch in relative for ch in ("\\", ":", "\x00", "\r", "\n")):
            raise CaptureError("无效文件路径。", 404)
        parts = relative.split("/")
        if any(part in {"", ".", ".."} for part in parts) or PurePosixPath(relative).is_absolute():
            raise CaptureError("无效文件路径。", 404)
        if Path(relative).suffix.lower() not in _FILES:
            raise CaptureError("此文件类型不允许下载。", 404)
        if _linked(self.root) or _linked(root):
            raise CaptureError("链接目录不可访问。", 403)
        candidate = root
        for part in parts:
            candidate = candidate / part
            if _linked(candidate):
                raise CaptureError("链接文件或目录不可访问。", 403)
        try:
            candidate.resolve().relative_to(root.resolve())
        except (ValueError, OSError):
            raise CaptureError("无效文件路径。", 404) from None
        if not candidate.is_file():
            raise CaptureError("文件不存在。", 404)
        if candidate.stat().st_size > 24 * 1024 * 1024:
            raise CaptureError("单个附件超过 24 MiB。", 413)
        return candidate

    def file(self, user, identifier, relative):
        record = self._load(user, identifier)
        return self._safe_file(self._root(record["id"]), relative)

    def archive(self, user, identifier):
        record = self._load(user, identifier)
        root = self._root(record["id"])
        # Explicitly enumerate evidence; never archive the account database,
        # arbitrary sibling files or unreferenced older montage generations.
        mapping = maps.load_map(self._safe_file(root, "research-map.json"))
        files = {"research-map.json"}
        for folder, dirs, names in os.walk(root / "observations", followlinks=False):
            if any(_linked(Path(folder) / name) for name in dirs):
                raise CaptureError("截图资料含链接目录，不能打包。", 403)
            for name in names:
                if Path(name).suffix.lower() in _FILES:
                    files.add((Path(folder) / name).relative_to(root).as_posix())
        for name in ("app-map.md", "capture-session.json", "timings.jsonl"):
            if (root / name).is_file():
                files.add(name)
        for flow in record.get("flows", []):
            files.add(flow["file"])
            notes = str(PurePosixPath(flow["file"]).parent / "flow_notes.md")
            files.add(notes)
        if len(files) > 1000:
            raise CaptureError("附件过多，不能一次打包。", 413)
        paths = [(name, self._safe_file(root, name)) for name in sorted(files)]
        if sum(path.stat().st_size for _, path in paths) > MAX_ARCHIVE_BYTES:
            raise CaptureError("本次附件超过 256 MiB，请分任务采集。", 413)
        destination = self.data_dir / "capture-exports"
        if _linked(destination):
            raise CaptureError("导出目录不能是目录联接。", 403)
        destination.mkdir(exist_ok=True)
        handle, name = tempfile.mkstemp(prefix="capture-" + identifier + "-", suffix=".zip", dir=destination)
        os.close(handle)
        archive = Path(name)
        try:
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                manifest = []
                for relative, path in paths:
                    self._safe_file(root, relative)
                    with path.open("rb") as stream:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    manifest.append({"file": relative, "bytes": path.stat().st_size, "sha256": digest})
                    bundle.write(path, relative)
                bundle.writestr("capture-info.json", json.dumps({key: record.get(key) for key in ("id", "title", "package", "serial", "model", "app_version", "version_code", "created_at")}, ensure_ascii=False, indent=2))
                bundle.writestr("evidence-manifest.json", json.dumps({"schema_version": 1, "captured_app": record["package"], "files": manifest,
                    "scope": "Actual Android screenshots and explicitly observed transitions; not complete app coverage."}, ensure_ascii=False, indent=2))
        except BaseException:
            archive.unlink(missing_ok=True)
            raise
        return archive
