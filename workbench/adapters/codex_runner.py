"""Injected local Codex subprocess runner with cancellation support."""

from workbench.core.runtime import *
from workbench.services.base import BoundService


class CodexRunner(BoundService):
    def run_codex(self, job):
        command = codex_command()
        if not command:
            raise ValueError("未找到 Codex CLI。")
        directory = self.data / "runs" / job["id"]
        output = directory / "model-output.md"
        command += ["exec","--ignore-user-config","--ephemeral","--skip-git-repo-check","--sandbox","read-only","--color","never","-C",str(directory),"-o",str(output),"-c",'web_search="live"']
        # This runner creates documents; it must not inherit arbitrary execution,
        # installed connectors, browser control, memory access or agent delegation.
        for feature in ('shell_tool','unified_exec','multi_agent','multi_agent_v2','apps','plugins','hooks','computer_use','browser_use','memories','skill_search'):
            command += ['--disable',feature]
        snapshot = json.loads((directory/'执行记录.json').read_text(encoding='utf-8'))
        model = snapshot.get('model', '')
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
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            self.processes[job["id"]] = process
        try:
            process.communicate(job["prompt"].encode("utf-8"), timeout=1800)
        except subprocess.TimeoutExpired:
            self.stop_process(process)
            process.wait(timeout=15)
            raise ValueError("任务超过 30 分钟，已停止；请缩小任务或稍后重试。")
        if process.returncode:
            raise ValueError("Codex 执行失败。请在终端检查 codex login status、模型可用性与额度后重试；也可下载任务包运行。")
        if not output.is_file():
            raise ValueError("Codex 未生成最终文档。")
        return output.read_text(encoding="utf-8")

    @staticmethod
    def stop_process(process):
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"], capture_output=True, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0), timeout=15)
        else:
            process.terminate()
