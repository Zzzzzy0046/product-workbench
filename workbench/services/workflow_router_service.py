"""Read-only workflow presets composed from enabled task capabilities."""

from workbench.core.runtime import *
from workbench.services.base import BoundService


class WorkflowRouterService(BoundService):
    def __init__(self, workbench, config_path=None):
        super().__init__(workbench)
        self.config_path = Path(config_path or HERE / "workflows" / "presets.json")

    def list_presets(self, mode="fast"):
        mode = str(mode or "fast")
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        presets = payload.get("workflows", [])
        if not isinstance(presets, list):
            raise ValueError("工作流配置必须包含 workflows 数组。")
        available = {
            task["key"]: task
            for pack in self.registry()
            if pack.get("enabled")
            for task in pack.get("tasks", [])
            if not task.get("modes") or mode in task["modes"]
        }
        result, seen = [], set()
        for raw in presets:
            workflow_id = str(raw.get("id", "")).strip()
            if not re.fullmatch(r"[a-z0-9-]+", workflow_id) or workflow_id in seen:
                raise ValueError("工作流 ID 无效或重复。")
            seen.add(workflow_id)
            if mode not in raw.get("modes", ["fast"]):
                continue
            steps = []
            for step in raw.get("steps", []):
                task_key = str(step.get("task", "")).strip()
                task = available.get(task_key)
                if task is None:
                    raise ValueError(f"工作流引用了不可用任务：{task_key}")
                steps.append({
                    "task": task_key,
                    "name": task["name"],
                    "description": task["description"],
                    "optional": bool(step.get("optional", False)),
                })
            if not steps:
                raise ValueError(f"工作流没有可执行步骤：{workflow_id}")
            result.append({
                "id": workflow_id,
                "name": str(raw.get("name", "")).strip(),
                "description": str(raw.get("description", "")).strip(),
                "prompt": str(raw.get("prompt", "")).strip(),
                "steps": steps,
            })
        return result
