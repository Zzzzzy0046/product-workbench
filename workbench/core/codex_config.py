"""Local Codex executable and model configuration discovery."""

import os
import json
import re
import shutil
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

from workbench.core.constants import HERE

def validate_codex_binary(value):
    """Validate a user-selected native CLI, never a shell command or wrapper."""
    if not isinstance(value, str) or not value.strip() or len(value) > 1024 or any(char in value for char in ('\x00', '\r', '\n', '"')):
        raise ValueError("请填写 Codex 原生可执行文件的完整路径，不要填写命令参数或脚本。")
    if value.strip().startswith(("\\\\", "//")):
        raise ValueError("请选择本机磁盘中的 Codex 文件，不支持网络共享路径。")
    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute() or not candidate.is_file():
        raise ValueError("指定的 Codex 文件不存在，请选择本机完整路径。")
    candidate = candidate.resolve()
    if str(candidate).startswith(("\\\\", "//")):
        raise ValueError("请选择本机磁盘中的 Codex 文件，不支持网络共享路径。")
    if os.name == "nt":
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(candidate.anchor) == 4:
            raise ValueError("请选择本机磁盘中的 Codex 文件，不支持网络映射盘。")
        if candidate.name.lower() != "codex.exe":
            raise ValueError("请选择原生 codex.exe，不支持其他程序或 .cmd/.ps1 脚本。")
        try:
            with candidate.open("rb") as stream:
                valid = stream.read(2) == b"MZ"
        except OSError:
            valid = False
        if not valid:
            raise ValueError("指定文件不是可读取的 Windows Codex 原生可执行文件。")
    elif candidate.name != "codex" or not os.access(candidate, os.X_OK):
        raise ValueError("请选择具有执行权限的原生 codex 文件。")
    return str(candidate)


def _desktop_codex_candidates():
    """Bounded lookup in the official desktop CLI directory, not a disk scan."""
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if os.name != "nt" or not local:
        return []
    root = Path(local) / "OpenAI" / "Codex" / "bin"
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name, reverse=True)[:64]
    except OSError:
        return []
    candidates = [root / "codex.exe"] + [item / "codex.exe" for item in entries if item.is_dir()]
    result = []
    for path in candidates:
        if path.is_file():
            try:
                result.append(validate_codex_binary(str(path)))
            except ValueError:
                pass
    return result


def codex_discovery(saved_path=None):
    """Discover without launching a CLI; env overrides remain authoritative."""
    candidates = []

    def add(path, source):
        if path and not any(item["path"] == path for item in candidates):
            candidates.append({"path": path, "label": "Codex 桌面客户端" if source == "desktop" else "Codex CLI", "source": source})

    binary_override = os.environ.get("WORKBENCH_CODEX_BIN", "").strip()
    script_override = os.environ.get("WORKBENCH_CODEX_JS", "").strip()
    native = shutil.which("codex.exe" if os.name == "nt" else "codex")
    if native:
        add(native, "path")
    desktop = _desktop_codex_candidates()
    for path in desktop:
        add(path, "desktop")
    result = {"command": None, "source": "missing", "candidates": candidates, "env_managed": bool(binary_override or script_override)}
    if binary_override:
        candidate = Path(binary_override).expanduser()
        executable = str(candidate.resolve()) if candidate.is_file() else shutil.which(binary_override)
        if not executable or (os.name == "nt" and Path(executable).suffix.lower() != ".exe"):
            raise ValueError("WORKBENCH_CODEX_BIN 无效：请指定存在的 Codex 原生可执行文件，不要填写命令参数或 .cmd/.ps1 脚本。")
        if os.name != "nt" and not os.access(executable, os.X_OK):
            raise ValueError("WORKBENCH_CODEX_BIN 指定的文件没有执行权限。")
        add(executable, "environment")
        return dict(result, command=[executable], source="environment")
    if script_override:
        script = Path(script_override).expanduser()
        if not script.is_file():
            raise ValueError("WORKBENCH_CODEX_JS 无效：指定的 Codex JavaScript 入口不存在。")
        node = shutil.which("node")
        if not node:
            raise ValueError("WORKBENCH_CODEX_JS 需要 Node.js，但当前环境未找到 node。")
        return dict(result, command=[node, str(script.resolve())], source="environment")
    if saved_path:
        executable = validate_codex_binary(saved_path)
        add(executable, "saved")
        return dict(result, command=[executable], source="saved")
    if native:
        return dict(result, command=[native], source="path")
    script = Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@openai/codex/bin/codex.js"
    node = shutil.which("node")
    if script.is_file() and node:
        return dict(result, command=[node, str(script)], source="npm")
    if desktop:
        return dict(result, command=[desktop[0]], source="desktop")
    return result


def codex_command(saved_path=None):
    """Return a no-shell argv, optionally using this workbench's saved path."""
    return codex_discovery(saved_path)["command"]


def configured_model():
    if os.environ.get("WORKBENCH_MODEL"):
        return os.environ["WORKBENCH_MODEL"]
    config = Path(os.environ.get("CODEX_HOME", str(Path.home()/".codex"))) / "config.toml"
    try:
        return tomllib.loads(config.read_text(encoding="utf-8")).get("model", "")
    except (OSError, ValueError):
        return ""


def _connection_config():
    path = Path(os.environ.get("CODEX_HOME", str(Path.home()/".codex"))) / "config.toml"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        raise ValueError("本机 Codex config.toml 无法读取或格式无效，请检查本机连接配置。") from None


def _toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_toml_value(key)} = {_toml_value(item)}" for key, item in value.items()) + "}"
    raise ValueError("本机 Codex 连接配置字段类型无效。")


def codex_runtime_settings():
    """Return an invocation-only connection whitelist, never auth-store contents.

    ``config_overrides`` contains TOML CLI overrides; ``secret_env_names`` is
    only used to redact inherited environment values from subprocess errors.
    Neither result should be persisted in a job snapshot or exported package.
    """
    config = _connection_config()
    overrides = []
    environment_names = []
    for field in ("model_reasoning_effort", "service_tier"):
        value = config.get(field)
        if value is not None:
            if not isinstance(value, str):
                raise ValueError(f"本机 Codex {field} 配置类型无效。")
            overrides.append(f"{field}={_toml_value(value)}")
    provider_name = config.get("model_provider")
    if not provider_name:
        return {"config_overrides": overrides, "secret_env_names": environment_names}
    if not isinstance(provider_name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", provider_name):
        raise ValueError("本机 Codex model_provider 名称无效。")
    overrides.append(f"model_provider={_toml_value(provider_name)}")
    providers = config.get("model_providers", {})
    if not isinstance(providers, dict):
        raise ValueError("本机 Codex model_providers 配置类型无效。")
    provider = providers.get(provider_name, {})
    if not isinstance(provider, dict):
        raise ValueError("本机 Codex 当前 provider 配置类型无效。")
    # Static credentials must stay out of process arguments and project data.
    for field in ("http_headers", "headers", "experimental_bearer_token", "api_key", "token", "bearer_token", "authorization"):
        if provider.get(field):
            raise ValueError("当前 Codex provider 包含静态认证字段；请改用本机登录、env_key 或 env_http_headers 后再在工作台执行。")
    allowed = {
        "name": str, "base_url": str, "wire_api": str,
        "requires_openai_auth": bool, "supports_websockets": bool,
        "env_key": str, "env_http_headers": dict,
    }
    for field, expected in allowed.items():
        if field not in provider:
            continue
        value = provider[field]
        if not isinstance(value, expected):
            raise ValueError(f"本机 Codex provider 的 {field} 类型无效。")
        if field == "base_url":
            try:
                url = urlsplit(value)
                safe = url.scheme in {"http", "https"} and url.hostname and not (url.username or url.password or url.query or url.fragment)
                safe = safe and not re.search(r"\b(?:sk[-_][A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)", value)
            except ValueError:
                safe = False
            if not safe:
                raise ValueError("Codex provider 的连接地址不可包含认证信息、查询参数或片段；请在本机配置中改用环境变量认证。")
        if field == "env_key":
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
                raise ValueError("Codex provider 的 env_key 必须是环境变量名。")
            environment_names.append(value)
        if field == "env_http_headers":
            if not all(isinstance(key, str) and isinstance(item, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item) for key, item in value.items()):
                raise ValueError("Codex provider 的 env_http_headers 必须将请求头映射到环境变量名。")
            environment_names.extend(value.values())
        overrides.append(f"model_providers.{_toml_value(provider_name)}.{field}={_toml_value(value)}")
    return {"config_overrides": overrides, "secret_env_names": environment_names}
