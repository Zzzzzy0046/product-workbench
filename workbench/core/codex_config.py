"""Local Codex executable and model configuration discovery."""

import os
import shutil
import tomllib
from pathlib import Path

from workbench.core.constants import HERE

def codex_command():
    override = os.environ.get("WORKBENCH_CODEX_JS")
    script = Path(override) if override else Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@openai/codex/bin/codex.js"
    node = shutil.which("node")
    if script.is_file() and node:
        return [node, str(script)]
    executable = shutil.which("codex.exe") or (shutil.which("codex") if os.name != "nt" else None)
    return [executable] if executable else None


def configured_model():
    if os.environ.get("WORKBENCH_MODEL"):
        return os.environ["WORKBENCH_MODEL"]
    config = Path(os.environ.get("CODEX_HOME", str(Path.home()/".codex"))) / "config.toml"
    try:
        return tomllib.loads(config.read_text(encoding="utf-8")).get("model", "")
    except (OSError, ValueError):
        return ""
