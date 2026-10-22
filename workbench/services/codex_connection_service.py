"""Explicit local Codex onboarding with no credential access or output storage."""

from __future__ import annotations

from copy import deepcopy
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import uuid

from workbench.core.codex_config import (
    codex_command, codex_discovery, codex_runtime_settings, configured_model,
    validate_codex_binary,
)


CONFIG_KEY = "codex-connection-v1"
FEATURES_DISABLED = (
    "shell_tool", "unified_exec", "multi_agent", "multi_agent_v2", "apps",
    "plugins", "hooks", "computer_use", "browser_use", "memories", "skill_search",
)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _auth():
    return {"status": "unknown", "method": "unknown", "checked_at": "", "message": "尚未检查登录状态。"}


def _test():
    return {"status": "not_tested", "checked_at": "", "message": "尚未进行实际连接测试；登录成功不代表模型可用。"}


def _failure(diagnostic):
    """Classify locally; never include raw CLI text, links or credentials."""
    value = diagnostic.lower()
    if any(word in value for word in ("quota", "rate_limit", "rate limit", "429", "usage limit", "credits exhausted")):
        return "Codex 额度不足或请求限流，请检查额度或稍后重试。"
    if any(word in value for word in ("401", "unauthorized", "not logged in", "authentication", "token expired", "login required")):
        return "Codex 登录或认证不可用，请重新检查本机登录状态。"
    if any(word in value for word in ("model_not_found", "model not found", "unsupported model", "not have access", "unknown model")):
        return "当前模型不可用，请检查本机模型配置及账号权限。"
    if any(word in value for word in ("unexpected argument", "unknown feature", "unrecognized option", "config.toml", "error parsing", "invalid value")):
        return "Codex CLI 版本或本机配置不兼容，请检查并更新 CLI。"
    if any(word in value for word in ("connection", "network", "timeout", "timed out", "dns", "tls", "502", "503", "stream disconnected")):
        return "Codex 网络连接失败，请检查本机网络与连接配置。"
    return "Codex 操作未完成，请检查 CLI 安装、登录及本机连接配置后重试。"


class _ConnectionFailure(Exception):
    """A fixed, safe message created only by this service."""


class CodexConnectionService:
    """Own only this screen's processes/state, separate from generation jobs."""

    def __init__(self, app):
        self.app = app
        self._lock = threading.RLock()
        self._processes = {}
        self._workers = {}
        self._closed = False
        self._operation = None
        self._active_id = None
        self._cancelled = set()
        self._fingerprint = None
        self._version = ""
        self._auth = _auth()
        self._test = _test()

    def _saved(self):
        rows = self.app.rows("SELECT value FROM preferences WHERE key=?", (CONFIG_KEY,))
        if not rows:
            return ""
        try:
            saved = json.loads(rows[0]["value"])
            return saved.get("binary_path", "") if isinstance(saved, dict) and isinstance(saved.get("binary_path", ""), str) else ""
        except (ValueError, TypeError):
            return ""

    def command(self):
        with self._lock:
            return codex_command(self._saved())

    def _context(self):
        saved = self._saved()
        config_path = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser() / "config.toml"
        error = ""
        try:
            discovery = codex_discovery(saved)
        except ValueError:
            discovery = {"command": None, "source": "environment" if any(os.environ.get(key, "").strip() for key in ("WORKBENCH_CODEX_BIN", "WORKBENCH_CODEX_JS")) else "saved", "candidates": [], "env_managed": any(os.environ.get(key, "").strip() for key in ("WORKBENCH_CODEX_BIN", "WORKBENCH_CODEX_JS"))}
            error = "Codex 路径配置无效，请选择原生 CLI 或检查环境变量。"
        model = configured_model()
        if not isinstance(model, str):
            model = ""
            error = "本机 Codex 模型配置格式无效，请检查 config.toml。"
        try:
            connection = codex_runtime_settings()
            config_signature = connection["config_overrides"]
        except ValueError:
            config_signature = ["invalid"]
            error = "本机 Codex 连接配置无法用于安全执行，请检查 config.toml。"
        # Metadata is sufficient to invalidate caches when the local provider changes.
        try:
            stamp = config_path.stat().st_mtime_ns
        except OSError:
            stamp = 0
        fingerprint = hashlib.sha256(json.dumps([discovery["command"], model, str(config_path), config_signature, stamp], ensure_ascii=False).encode("utf-8")).hexdigest()
        return discovery, saved, model, config_path, fingerprint, error

    def snapshot(self):
        """Only inspect non-secret paths/config; never spawn a process on GET."""
        with self._lock:
            discovery, saved, model, config, fingerprint, error = self._context()
            if self._fingerprint != fingerprint:
                self._fingerprint = fingerprint
                self._version = ""
                self._auth = _auth()
                self._test = _test()
            command = discovery["command"] or []
            result = {
                "available": bool(command), "command": command, "binary_path": saved,
                "source": discovery["source"], "candidates": discovery["candidates"],
                "version": self._version, "model": model, "config_path": str(config),
                "env_managed": bool(discovery["env_managed"]),
                "message": error or ("已找到本机 Codex CLI；请检查登录状态，实际模型可用性需单独测试。" if command else "未找到 Codex CLI，请先安装或选择本机原生可执行文件。"),
                "auth": self._auth, "test": self._test, "operation": self._operation,
            }
            return deepcopy(result)

    def configure(self, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("binary_path", ""), str):
            raise ValueError("CLI 路径格式无效。")
        with getattr(self.app, "lock", None) or nullcontext(), self._lock:
            self._ensure_idle()
            self._ensure_no_work()
            if self._context()[0]["env_managed"]:
                raise ValueError("当前 CLI 由环境变量管理，请先由本机管理员调整环境变量。")
            value = payload.get("binary_path", "").strip()
            path = validate_codex_binary(value) if value else ""
            with self.app.db() as db:
                db.execute("INSERT OR REPLACE INTO preferences(key,value) VALUES(?,?)", (CONFIG_KEY, json.dumps({"binary_path": path}, ensure_ascii=False)))
            self._fingerprint = None
            return self.snapshot()

    def _ensure_idle(self):
        if self._closed:
            raise ValueError("Codex 连接服务已关闭。")
        if self._active_id or any(process.poll() is None for process in self._processes.values()):
            raise ValueError("已有 Codex 操作正在执行，请等待或先取消。")

    def _ensure_no_work(self):
        jobs = self.app.rows("SELECT id FROM jobs WHERE status IN (?,?) LIMIT 1", ("queued", "running"))
        capture = getattr(self.app, "android_capture", None)
        captures = bool(getattr(capture, "_capture_processes", {})) or any(worker.is_alive() for worker in list(getattr(capture, "_capture_threads", {}).values()))
        if jobs or captures:
            raise ValueError("工作台正在生成文档或进行实机走查，请等待完成后再修改 CLI、登录或测试连接。")

    def start(self, kind, payload=None):
        if kind not in {"check", "login", "test"}:
            raise ValueError("不支持的 Codex 操作。")
        if kind in {"login", "test"} and (not isinstance(payload, dict) or payload.get("confirmed") is not True):
            raise ValueError("请先确认本次登录授权或最小模型测试。")
        with getattr(self.app, "lock", None) or nullcontext(), self._lock:
            self._ensure_idle()
            if kind in {"login", "test"}:
                self._ensure_no_work()
            state = self.snapshot()
            command = self.command()
            if not command:
                raise ValueError("未找到 Codex CLI，请先配置本机原生可执行文件。")
            identifier = uuid.uuid4().hex
            now = _now()
            self._operation = {"id": identifier, "kind": kind, "status": "running", "started_at": now, "updated_at": now, "message": {"check": "正在检查 CLI 版本和本机登录状态，不会调用模型。", "login": "已启动官方登录流程，请在系统默认浏览器中自行完成授权。", "test": "正在使用空目录做最小模型测试，不会使用任何项目资料。"}[kind]}
            self._active_id = identifier
            if kind in {"check", "login"}:
                self._auth = _auth()
            if kind in {"login", "test"}:
                self._test = _test()
            thread = threading.Thread(target=self._run, args=(identifier, kind, command, self._fingerprint, state["model"]), daemon=True)
            self._workers[identifier] = thread
            thread.start()
            return self.snapshot()

    @staticmethod
    def _stop(process):
        if process.poll() is not None:
            return True
        if os.name == "nt":
            try:
                taskkill = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe")
                subprocess.run([taskkill, "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (OSError, subprocess.TimeoutExpired):
                pass
        for method in (process.terminate, process.kill):
            if process.poll() is not None:
                break
            try:
                method()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        return process.poll() is not None

    def _execute(self, identifier, command, timeout, cwd=None, prompt=None, discard=False):
        """Bounded in-memory diagnostics; no shell and no stdout/stderr files."""
        with self._lock:
            if self._closed or identifier in self._cancelled:
                raise InterruptedError()
            process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE if prompt else subprocess.DEVNULL, stdout=subprocess.DEVNULL if discard else subprocess.PIPE, stderr=subprocess.DEVNULL if discard else subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self._processes[identifier] = process
        tails = [b"", b""]
        workers = []

        def drain(stream, index):
            try:
                while chunk := stream.read(4096):
                    tails[index] = (tails[index] + chunk)[-8192:]
            except (OSError, ValueError):
                pass

        for index, stream in enumerate((process.stdout, process.stderr)):
            if stream is not None:
                worker = threading.Thread(target=drain, args=(stream, index), daemon=True)
                worker.start()
                workers.append(worker)
        if prompt:
            def send():
                try:
                    process.stdin.write(prompt.encode("utf-8"))
                    process.stdin.flush()
                except (OSError, ValueError):
                    pass
                finally:
                    try:
                        process.stdin.close()
                    except (OSError, ValueError):
                        pass
            worker = threading.Thread(target=send, daemon=True)
            worker.start()
            workers.append(worker)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._stop(process)
            raise TimeoutError() from None
        except OSError:
            self._stop(process)
            raise
        finally:
            for worker in workers:
                worker.join(timeout=1)
            with self._lock:
                if process.poll() is not None:
                    self._processes.pop(identifier, None)
        with self._lock:
            if self._closed or identifier in self._cancelled:
                raise InterruptedError()
        return process.returncode, b"\n".join(tails).decode("utf-8", "replace")

    def _login_status(self, identifier, command):
        code, output = self._execute(identifier, command + ["login", "status"], 20)
        value = output.lower()
        status, method = "error", "unknown"
        if "not logged in" in value or "login required" in value:
            status = "not_logged_in"
        elif code == 0 and re.search(r"\blogged in\b", value):
            status = "logged_in"
            if "chatgpt" in value:
                method = "chatgpt"
            elif "api key" in value or "api_key" in value:
                method = "api_key"
            elif "access token" in value or "access_token" in value:
                method = "access_token"
        return {"status": status, "method": method, "checked_at": _now(), "message": {"logged_in": "本机 CLI 已登录；模型权限和网络尚需单独测试。", "not_logged_in": "本机 CLI 尚未登录，请使用官方浏览器登录。", "error": "无法确认本机登录状态，请检查 CLI 安装和连接配置。"}[status]}

    def _run(self, identifier, kind, command, fingerprint, model):
        status, message = "succeeded", "操作已完成。"
        auth = None
        test = None
        version = None
        try:
            if kind == "check":
                code, output = self._execute(identifier, command + ["--version"], 15)
                match = re.search(r"\bcodex(?:-cli)?\s+(\d+\.\d+(?:\.\d+)?(?:[-+][A-Za-z0-9.]+)?)\b", output, re.I)
                if code or not match:
                    raise _ConnectionFailure(_failure(output))
                version = match.group(1)
                auth = self._login_status(identifier, command)
                if auth["status"] == "error":
                    status = "failed"
                message = auth["message"]
            elif kind == "login":
                code, _ = self._execute(identifier, command + ["login"], 300, discard=True)
                if code:
                    raise _ConnectionFailure("官方登录流程未完成或已被关闭，请重新尝试。")
                auth = self._login_status(identifier, command)
                if auth["status"] != "logged_in":
                    status = "failed"
                message = auth["message"]
            else:
                settings = codex_runtime_settings()
                with tempfile.TemporaryDirectory(prefix="workbench-codex-test-") as directory:
                    output_file = Path(directory) / "reply.txt"
                    argv = command + ["exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never", "-C", directory, "-o", str(output_file), "-c", 'approval_policy="never"', "-c", 'web_search="disabled"']
                    for override in settings["config_overrides"]:
                        argv += ["-c", override]
                    for feature in FEATURES_DISABLED:
                        argv += ["--disable", feature]
                    if model:
                        argv += ["--model", model]
                    argv += ["-"]
                    code, diagnostic = self._execute(identifier, argv, 90, cwd=directory, prompt="仅回复连接成功")
                    if code:
                        raise _ConnectionFailure(_failure(diagnostic))
                    # Read only a tiny final response; no model output is returned or stored.
                    try:
                        with output_file.open("rb") as stream:
                            reply = stream.read(256).decode("utf-8", "replace").strip().strip('。.!！\"“”` \r\n')
                    except OSError:
                        reply = ""
                    if reply != "连接成功":
                        raise _ConnectionFailure("CLI 已退出，但没有返回预期的最小测试结果；暂不能确认模型可用。")
                message = "最小模型测试通过；未使用项目资料，不代表所有正式生成任务都已验证。"
                test = {"status": "passed", "checked_at": _now(), "message": message}
        except InterruptedError:
            status, message = "cancelled", "操作已取消。"
        except TimeoutError:
            status = "failed"
            message = "官方登录等待超过 5 分钟，已停止本次操作。" if kind == "login" else "Codex 操作超时，已停止本次操作；请检查网络或稍后重试。"
        except _ConnectionFailure as error:
            status, message = "failed", str(error)
        except ValueError:
            status, message = "failed", "本机 Codex 连接配置无法用于安全执行，请检查 config.toml。"
        except (OSError, subprocess.SubprocessError):
            status, message = "failed", "Codex CLI 无法启动或连接中断，请检查本机 CLI 路径和安装。"
        except Exception:
            status, message = "failed", "Codex 操作未完成，请检查本机配置后重试。"
        finally:
            with self._lock:
                self._workers.pop(identifier, None)
                process = self._processes.get(identifier)
                still_running = bool(process and process.poll() is None)
                if self._active_id == identifier and not still_running:
                    self._active_id = None
                if not self._operation or self._operation["id"] != identifier:
                    return
                if identifier in self._cancelled or self._closed:
                    status, message = "cancelled", "操作已取消。"
                if self._context()[4] != fingerprint:
                    status, message = "failed", "CLI 路径、模型或连接配置已变化，请重新检查连接。"
                    self._fingerprint = None
                elif status != "cancelled":
                    if version is not None:
                        self._version = version
                    if auth is not None:
                        self._auth = auth
                    elif kind in {"check", "login"} and status == "failed":
                        self._auth = {"status": "error", "method": "unknown", "checked_at": _now(), "message": message}
                    if test is not None:
                        self._test = test
                    elif kind == "test" and status == "failed":
                        self._test = {"status": "failed", "checked_at": _now(), "message": message}
                if still_running:
                    status, message = "running", "未能停止本次 CLI 进程，请再次取消；停止前不能开始其他连接操作。"
                self._operation.update(status=status, message=message, updated_at=_now())
                self._cancelled.discard(identifier)

    def cancel(self, operation_id):
        with self._lock:
            if not self._operation or self._operation["id"] != operation_id:
                raise ValueError("Codex 操作不存在或已更新。")
            if self._operation["status"] != "running":
                return self.snapshot()
            self._cancelled.add(operation_id)
            process = self._processes.get(operation_id)
            self._operation.update(updated_at=_now(), message="正在停止本次操作，请稍候。")
        if process:
            self._stop(process)
            with self._lock:
                if process.poll() is not None:
                    self._processes.pop(operation_id, None)
                    if self._active_id == operation_id and operation_id not in self._workers:
                        self._active_id = None
                    if self._operation and self._operation["id"] == operation_id and operation_id not in self._workers:
                        self._operation.update(status="cancelled", updated_at=_now(), message="操作已取消。")
        return self.snapshot()

    def close(self):
        with self._lock:
            self._closed = True
            processes = list(self._processes.items())
            for identifier, _ in processes:
                self._cancelled.add(identifier)
            if self._operation and self._operation["status"] == "running":
                self._operation.update(status="cancelled", updated_at=_now(), message="工作台已关闭，本次连接操作已取消。")
        for _, process in processes:
            self._stop(process)
