"""Capability registry and task-definition lookup."""

import copy

from workbench.core.runtime import *
from workbench.services.base import BoundService


class CapabilityService(BoundService):
    def __init__(self, workbench):
        super().__init__(workbench)
        object.__setattr__(self, "_registry_cache", None)

    def registry(self):
        """Return capability packs; parsed packs are cached by file mtime/size."""
        prefs = {r["key"]:json.loads(r["value"]) for r in self.rows("SELECT * FROM preferences")}
        paths = sorted((HERE / "capabilities").glob("*.json"))
        signature = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths)
        cached = self._registry_cache
        if cached and cached[0] == signature and all(template.is_file() for template in cached[2]):
            packs = copy.deepcopy(cached[1])
        else:
            packs, templates = self._parse_registry(paths)
            object.__setattr__(self, "_registry_cache", (signature, copy.deepcopy(packs), templates))
        for pack in packs:
            pack["enabled"] = prefs.get("pack:"+pack["id"], pack.get("enabled", False))
        return packs

    def _parse_registry(self, paths):
        packs, seen, templates = [], set(), []
        for path in paths:
            pack = json.loads(path.read_text(encoding="utf-8"))
            if not re.fullmatch(r"[a-z0-9-]+", pack["id"]) or pack["id"] in seen:
                raise ValueError("能力包 ID 无效或重复。")
            seen.add(pack["id"])
            local_ids = set()
            for task in pack["tasks"]:
                if not re.fullmatch(r"[a-z0-9-]+", task["id"]) or task["id"] in local_ids:
                    raise ValueError("任务 ID 无效或重复。")
                local_ids.add(task["id"])
                template = (ROOT / task["template"]).resolve()
                if not template.is_relative_to(ROOT) or template.suffix != ".md" or not template.is_file():
                    raise ValueError("模板必须指向仓库内已有 Markdown。")
                templates.append(template)
                if not set(task["tools"]).issubset({t["id"] for t in TOOLS if t["status"] == "ready"}):
                    raise ValueError("任务包含未接入工具。")
                task["key"] = f'{pack["id"]}/{task["id"]}'
            packs.append(pack)
        return packs, templates

    def task(self, key):
        for pack in self.registry():
            for task in pack["tasks"]:
                if task["key"] == key and pack["enabled"]:
                    return task
        raise ValueError("任务不存在或所属能力未启用。")

    def task_definition(self, key):
        for pack in self.registry():
            for task in pack["tasks"]:
                if task["key"] == key:
                    return task
        raise ValueError("任务定义不存在。")
