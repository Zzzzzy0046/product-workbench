"""Non-secret Lanhu MCP configuration inspection and snapshot settings."""

from workbench.core.runtime import *
from workbench.services.base import BoundService


class LanhuAdapter(BoundService):
    def lanhu_settings(self):
        """Return non-secret Lanhu MCP configuration and local readiness."""
        prefs = self.rows("SELECT value FROM preferences WHERE key=?", (LANHU_CONFIG_KEY,))
        saved = {}
        if prefs:
            try:
                saved = json.loads(prefs[0]["value"])
            except (TypeError, ValueError):
                saved = {}
        codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home()/".codex"))).expanduser()
        config_path = Path(str(saved.get("config_path") or (codex_home / "config.toml"))).expanduser()
        configured = {}
        config_exists = config_path.is_file()
        if config_exists:
            try:
                parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
                configured = parsed.get("mcp_servers", {}).get("lanhu", {}) or {}
            except (OSError, ValueError, TypeError):
                configured = {}
        command = str(saved.get("command") or configured.get("command") or "npx").strip()
        args = saved.get("args") if isinstance(saved.get("args"), list) else configured.get("args", [])
        args = [str(item)[:240] for item in args[:12]] if isinstance(args, list) else []
        package = str(saved.get("package") or next((item for item in args if item == "mcp-lanhu"), "mcp-lanhu"))
        env_keys = sorted(str(key) for key in (configured.get("env") or {}).keys()) if isinstance(configured.get("env"), dict) else []
        executable = shutil.which(command) or shutil.which(command + ".cmd")
        ready = bool(config_exists and executable and package == "mcp-lanhu" and env_keys)
        if not config_exists:
            message = "未找到 Codex 配置文件。"
        elif not executable:
            message = f"未找到 {command}，请先安装 Node.js / npx。"
        elif not env_keys:
            message = "已找到 MCP 配置，但没有检测到认证环境变量。"
        else:
            message = "已检测到 Lanhu MCP 配置；尚未执行实际连接测试。"
        return {
            "configured": bool(configured),
            "config_path": str(config_path),
            "config_exists": config_exists,
            "command": command,
            "args": args,
            "package": package,
            "env_keys": env_keys,
            "executable_found": bool(executable),
            "ready": ready,
            "message": message,
            "enabled": bool(saved.get("enabled", True)),
            "source": "saved" if saved else "codex-config",
        }

    def save_lanhu_settings(self, payload):
        command = str(payload.get("command") or "npx").strip()
        package = str(payload.get("package") or "mcp-lanhu").strip()
        config_path = str(payload.get("config_path") or "").strip()
        if command not in {"npx", "npx.cmd"}:
            raise ValueError("为安全起见，Lanhu MCP 命令目前只允许 npx。")
        if not LANHU_PACKAGE_PATTERN.fullmatch(package) or len(package) > 180:
            raise ValueError("MCP 包名格式无效。")
        if package != "mcp-lanhu":
            raise ValueError("当前 Lanhu 连接只允许 mcp-lanhu。")
        if config_path and len(config_path) > 500:
            raise ValueError("配置文件路径过长。")
        saved = {"command": command, "package": package, "config_path": config_path, "enabled": bool(payload.get("enabled", True))}
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO preferences VALUES(?,?)", (LANHU_CONFIG_KEY, json.dumps(saved, ensure_ascii=False)))
        return self.lanhu_settings()
