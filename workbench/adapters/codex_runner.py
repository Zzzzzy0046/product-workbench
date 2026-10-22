"""Injected local Codex subprocess runner with cancellation support."""

from workbench.core.runtime import *
from workbench.core.codex_config import codex_runtime_settings
from workbench.services.base import BoundService


DIAGNOSTIC_LIMIT = 12_000


def redact_codex_diagnostic(message, secret_env_names=()):
    """Keep useful CLI failures without persisting credentials or endpoints."""
    value = str(message or "")
    names = set(secret_env_names)
    names.update(name for name in os.environ if re.search(r"(?:TOKEN|SECRET|PASSWORD|COOKIE|AUTH|API.?KEY|CREDENTIAL|_KEY$)", name, re.I))
    for name in names:
        secret = os.environ.get(name, "")
        if len(secret) >= 4:
            value = value.replace(secret, "[认证信息已隐藏]")
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    value = re.sub(r"(?i)https?://[^\s<>\"']+", "[连接地址已隐藏]", value)
    value = re.sub(r"(?i)\bBearer\s+[^\s,;\"']+", "Bearer [认证信息已隐藏]", value)
    value = re.sub(r"\bsk[-_][A-Za-z0-9_-]{8,}", "[认证信息已隐藏]", value)
    value = re.sub(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[认证信息已隐藏]", value)
    value = re.sub(r"(?im)^([^\r\n]*?\b(?:authorization|x-api-key|api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|cookie|set-cookie|secret|password|experimental_bearer_token|http_headers)\b[\"']?\s*[:=]).*$", r"\1 [认证信息已隐藏]", value)
    return value[-DIAGNOSTIC_LIMIT:].strip()


def codex_failure_summary(diagnostic):
    lowered = diagnostic.lower()
    if any(term in lowered for term in ("unexpected argument", "unknown feature", "unrecognized option", "invalid value", "error parsing", "config.toml")):
        reason = "Codex 参数或配置错误，请检查 CLI 版本及本机连接设置。"
    elif any(term in lowered for term in ("insufficient_quota", "quota", "rate limit", "rate_limit", "usage limit", "429", "credits exhausted")):
        reason = "Codex 额度不足或请求限流，请检查额度或稍后重试。"
    elif any(term in lowered for term in ("unauthorized", "401", "not logged in", "authentication", "login required", "token expired")):
        reason = "Codex 登录或认证失败，请在本机执行 codex login status 并检查当前连接。"
    elif any(term in lowered for term in ("model not found", "model_not_found", "unsupported model", "model does not exist", "not supported when using", "unknown model", "not have access to model")):
        reason = "Codex 模型不可用，请检查模型名称和当前连接的模型权限。"
    elif any(term in lowered for term in ("connection", "connect error", "timed out", "timeout", "dns", "tls", "certificate", "502", "503", "network", "failed to send request", "stream disconnected")):
        reason = "Codex 网络或连接失败，请检查网络及本机 provider 的连接地址。"
    else:
        reason = "Codex 执行失败，请查看本次任务的本地诊断并重试。"
    detail = diagnostic[-650:].strip()
    return reason + ("\n诊断摘要：" + detail if detail else " 未收到 CLI 错误详情。")


class CodexRunner(BoundService):
    def run_codex(self, job):
        command = codex_command()
        if not command:
            raise ValueError("未找到 Codex CLI。")
        directory = self.data / "runs" / job["id"]
        attempt = uuid.uuid4().hex
        output = directory / f"model-output-{attempt}.md"
        diagnostic_path = directory / f"codex-diagnostics-{attempt}.log"
        connection = codex_runtime_settings()
        command += ["exec","--ignore-user-config","--ephemeral","--skip-git-repo-check","--sandbox","read-only","--color","never","-C",str(directory),"-o",str(output),"-c",'web_search="live"']
        for override in connection["config_overrides"]:
            command += ["-c", override]
        # This runner creates documents; it must not inherit arbitrary execution,
        # installed connectors, browser control, memory access or agent delegation.
        for feature in ('shell_tool','unified_exec','multi_agent','multi_agent_v2','apps','plugins','hooks','computer_use','browser_use','memories','skill_search'):
            command += ['--disable',feature]
        snapshot = json.loads((directory/'执行记录.json').read_text(encoding='utf-8'))
        model = snapshot.get('model', '')
        if not isinstance(model, str):
            raise ValueError("任务快照中的 Codex 模型名称无效，请重新准备任务。")
        if model:
            command += ["--model",model]
        for image_path in dict.fromkeys(source.get("image_path", "") for source in snapshot.get("sources", [])):
            if image_path and Path(image_path).is_file():
                command += ["--image", image_path]
        command += ["-"]
        # No shell interpolation. Credentials stay in the CLI's existing auth store.
        with self.lock:
            if self.job(job["id"])["status"] == "cancelled":
                raise ValueError("任务已取消。")
            try:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            except OSError:
                raise ValueError("Codex CLI 无法启动，请检查 Node.js、CLI 安装和可执行文件路径。") from None
            self.processes[job["id"]] = process
        # Drain a bounded tail while writing stdin independently, so a CLI that
        # never reads its prompt cannot block cancellation or the timeout.
        tail = [""]

        def drain_errors():
            import codecs
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            try:
                while True:
                    chunk = process.stderr.read(4096)
                    if not chunk:
                        break
                    tail[0] = (tail[0] + decoder.decode(chunk))[-DIAGNOSTIC_LIMIT:]
                tail[0] = (tail[0] + decoder.decode(b"", final=True))[-DIAGNOSTIC_LIMIT:]
            except (OSError, ValueError):
                pass

        def write_prompt():
            try:
                process.stdin.write(job["prompt"].encode("utf-8"))
                process.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                pass
            finally:
                try:
                    process.stdin.close()
                except (OSError, ValueError):
                    pass

        errors_worker = threading.Thread(target=drain_errors, daemon=True)
        input_worker = threading.Thread(target=write_prompt, daemon=True)
        errors_worker.start()
        input_worker.start()
        timed_out = False
        stopped = True
        try:
            process.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            timed_out = True
            stopped = self.stop_process(process)
        except OSError:
            self.stop_process(process)
            raise ValueError("Codex 子进程连接中断，请检查 CLI 运行环境后重试。") from None
        finally:
            errors_worker.join(timeout=3)
            input_worker.join(timeout=3)
        diagnostic = redact_codex_diagnostic(tail[0], connection["secret_env_names"])
        # This file is local diagnostics, not a deliverable or task input.
        try:
            diagnostic_path.write_text(diagnostic, encoding="utf-8")
        except OSError:
            pass
        if timed_out:
            message = "任务超过 30 分钟，已停止；请缩小任务或稍后重试。" if stopped else "任务超过 30 分钟；停止进程未完成，请检查本机 Codex 进程后重试。"
            raise ValueError(message)
        if self.job(job["id"])["status"] == "cancelled":
            raise ValueError("任务已取消。")
        if process.returncode:
            raise ValueError(codex_failure_summary(diagnostic))
        if not output.is_file():
            raise ValueError("Codex 未生成最终文档。")
        return output.read_text(encoding="utf-8")

    @staticmethod
    def stop_process(process):
        if process.poll() is not None:
            return True
        if os.name == "nt":
            try:
                subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"], capture_output=True, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0), timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                pass
        for stop in (process.terminate, process.kill):
            if process.poll() is not None:
                return True
            try:
                stop()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                continue
        return process.poll() is not None
