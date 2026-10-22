"""Assemble a clean Windows EXE/source handoff without copying local run data.

Run this with the same isolated Python environment used to build the EXE so
dependency notices describe that environment. This script does not run the EXE,
connect to services or devices, install dependencies, or create the outer ZIP.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import sys
import sysconfig


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_DOCS = (
    "WORKBENCH-HTTP-API.md",
    "WORKBENCH-EXE-HANDOFF.md",
    "数据采集能力与数据流-同事交接说明-v1.0.md",
)
GENERAL_DOCS = (
    "WORKBENCH-EXE-VERIFICATION.md",
    "WORKFLOW-USER-MANUAL.md",
    "WORKBENCH-FLOW-AND-VERIFICATION.md",
    "WORKBENCH-OVERVIEW.md",
    "WORKBENCH-ANDROID-CAPTURE.md",
    "WORKBENCH-BEHAVIOR-BASELINE.md",
    "WORKBENCH-COMPETITOR-DISCOVERY-UPDATE.md",
)
EXCLUDED_DIRECTORIES = frozenset({
    "data", "auth", ".git", ".venv", ".runtime", "backups", "__pycache__",
    "work", "tmp", "temp", "projects", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "node_modules", "site-packages", "dist", "build",
    "inbox", "cases", "decisions", ".index", ".cache", "browser-data",
})
SENSITIVE_FILENAME = re.compile(
    r"(?:^|[._-])(?:tokens?|cookies?|credentials?|secrets?|passwords?)(?:[._-]|$)",
    re.IGNORECASE,
)
LICENSE_FILENAME = re.compile(
    r"^(?:licen[cs]e|copying|copyright|notice)(?:[._-].*)?$", re.IGNORECASE
)
SOURCE_TREES = (
    ("workbench", {".py", ".js", ".css", ".html", ".json", ".md", ".ps1", ".cmd"}),
    ("packages/competitor-collector/competitor_collector", {".py", ".js", ".css", ".html", ".json", ".md", ".txt"}),
    ("packages/competitor-collector/tests", {".py"}),
    ("packages/android-capture/skill", {".py", ".md", ".json", ".js", ".css", ".html", ".txt", ".ps1"}),
    ("packages/android-walkthrough/skill", {".py", ".md", ".json", ".yaml", ".yml", ".txt"}),
    ("src/product_kb", {".py"}),
    ("knowledge/templates", {".md", ".json", ".yaml", ".yml", ".txt"}),
    ("knowledge/wiki/methods", {".md", ".json", ".yaml", ".yml", ".txt"}),
    ("knowledge/wiki/patterns", {".md", ".json", ".yaml", ".yml", ".txt"}),
    ("scripts", {".py", ".ps1", ".cmd", ".bat", ".js", ".mjs", ".sh", ".md", ".json"}),
    ("tests", {".py"}),
)
FIXED_SOURCE_FILES = (
    "README.md", "pyproject.toml", ".gitignore", ".mcp.example.json",
    "packages/competitor-collector/README.md",
    "packages/competitor-collector/VERIFICATION.md",
    "packages/competitor-collector/pyproject.toml",
    "packages/competitor-collector/start.ps1",
    "packages/competitor-collector/启动采集器.cmd",
    "scripts/packaging/requirements-build.lock",
)
MAX_LICENSE_BYTES = 2 * 1024 * 1024


def is_reparse_point(path: Path) -> bool:
    """Do not follow symlinks, Windows junctions or other reparse points."""
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def allowed_source(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part.casefold() in EXCLUDED_DIRECTORIES for part in relative.parts[:-1]):
        return False
    name = path.name.casefold()
    if name.startswith(".env") or name == ".mcp.json":
        return False
    if re.search(r"\.(?:sqlite|db)", name) or SENSITIVE_FILENAME.search(name):
        return False
    if name.endswith((".pyc", ".pyo", ".pem", ".key", ".pfx", ".p12")):
        return False
    if is_reparse_point(path) or not path.is_file():
        return False
    # A safe-looking child must not escape through a parent junction either.
    return path.resolve().is_relative_to(ROOT)


def walk_source(directory: Path, suffixes: set[str]):
    if not directory.is_dir() or is_reparse_point(directory):
        return
    for parent, dirs, files in os.walk(directory, followlinks=False):
        folder = Path(parent)
        dirs[:] = sorted(
            name for name in dirs
            if name.casefold() not in EXCLUDED_DIRECTORIES
            and not is_reparse_point(folder / name)
        )
        for name in sorted(files):
            path = folder / name
            if path.suffix.casefold() in suffixes and allowed_source(path):
                yield path


def source_files() -> list[Path]:
    selected: set[Path] = set()
    for relative, suffixes in SOURCE_TREES:
        selected.update(walk_source(ROOT / relative, suffixes))
    candidates = [ROOT / relative for relative in FIXED_SOURCE_FILES]
    candidates += [ROOT / "docs" / name for name in REQUIRED_DOCS + GENERAL_DOCS]
    candidates += sorted((ROOT / "schemas").glob("*.json"))
    candidates += sorted((ROOT / "config").glob("*.example.yaml"))
    for path in candidates:
        if path.is_file() and allowed_source(path):
            selected.add(path)
    return sorted(selected, key=lambda path: path.relative_to(ROOT).as_posix())


def write_text(path: Path, text: str, *, windows_text: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8-sig" if windows_text else "utf-8", newline="\n")


def write_json(path: Path, value):
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def copy_file(source: Path, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    # Copy file contents, without carrying source-machine permissions or metadata.
    shutil.copyfile(source, target)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")[:160] or "unnamed"


def site_package_roots() -> list[Path]:
    """Inspect this interpreter's environment, never a user-site/config folder."""
    roots = {Path(value).resolve() for key, value in sysconfig.get_paths().items()
             if key in {"purelib", "platlib"} and value}
    return sorted((path for path in roots if path.is_dir()), key=str)


def read_license(path: Path) -> str:
    if is_reparse_point(path) or path.stat().st_size > MAX_LICENSE_BYTES:
        raise ValueError("license file is a link or exceeds the 2 MiB collection limit")
    content = path.read_bytes()
    if b"\x00" in content:
        raise ValueError("license file appears to be binary")
    return content.decode("utf-8-sig", errors="replace")


def collect_notices(output: Path) -> dict:
    site_roots = site_package_roots()
    if not site_roots:
        raise ValueError("当前 Python 环境没有可读取的 site-packages；请使用构建 EXE 的虚拟环境。")
    distributions = sorted(
        metadata.distributions(path=[str(path) for path in site_roots]),
        key=lambda dist: ((dist.metadata.get("Name") or "").casefold(), dist.version),
    )
    packages = []
    notices = [
        "PRODUCT WORKBENCH RESEARCH — THIRD-PARTY NOTICES", "",
        "These notices were collected from installed distribution metadata and",
        "license files in the Python environment running package_handoff.py.",
        "This inventory describes the build environment; it is not a claim that",
        "every listed distribution or file is embedded in the EXE.",
        "The original notices below remain attributable to their respective owners.",
        "No installation, device execution or external service verification is implied.", "",
    ]
    seen = set()
    for dist in distributions:
        meta = dist.metadata
        name, version = str(meta.get("Name") or "unknown"), str(dist.version)
        if (name.casefold(), version) in seen:
            continue
        seen.add((name.casefold(), version))
        record = {
            "name": name, "version": version,
            "license_expression": str(meta.get("License-Expression") or ""),
            "license_metadata": str(meta.get("License") or ""),
            "license_classifiers": [value for value in meta.get_all("Classifier", [])
                                    if value.startswith("License ::")],
            "license_files": [], "collection_notes": [],
        }
        notices += ["=" * 78, f"{name} {version}", "=" * 78]
        for label, value in (
            ("License expression", record["license_expression"]),
            ("License metadata", record["license_metadata"]),
            ("License classifiers", "; ".join(record["license_classifiers"])),
        ):
            if value:
                notices.append(f"{label}: {value}")
        for entry in sorted(dist.files or [], key=str):
            relative = Path(str(entry))
            if relative.is_absolute() or ".." in relative.parts or not LICENSE_FILENAME.fullmatch(relative.name):
                continue
            located = Path(dist.locate_file(entry)).resolve()
            # Distribution RECORD entries can point outside site-packages. Never
            # follow those entries into scripts, configuration or home folders.
            if not any(located.is_relative_to(root) for root in site_roots):
                continue
            try:
                if not located.is_file():
                    continue
                text = read_license(located)
            except (OSError, ValueError):
                record["collection_notes"].append(f"Could not collect license: {relative.as_posix()}")
                continue
            ordinal = len(record["license_files"]) + 1
            destination = output / "dependencies/licenses" / portable_name(f"{name}-{version}") / f"{ordinal:02d}-{portable_name(relative.name)}.txt"
            write_text(destination, text)
            license_record = {
                "distribution_path": relative.as_posix(),
                "path": destination.relative_to(output).as_posix(),
                "size": destination.stat().st_size, "sha256": sha256(destination),
            }
            record["license_files"].append(license_record)
            notices += ["", f"--- {relative.as_posix()} ---", text.rstrip(), ""]
        if not record["license_files"]:
            notices.append("No separate readable license file was found in this installed distribution.")
        notices += record["collection_notes"] + [""]
        packages.append(record)

    python_record = {
        "implementation": platform.python_implementation(),
        "version": platform.python_version(), "license_file": "",
    }
    prefixes = {Path(sys.base_prefix), Path(sys.prefix)}
    python_candidates = [prefix / filename for prefix in sorted(prefixes, key=str)
                         for filename in ("LICENSE.txt", "LICENSE", "license.txt")]
    python_candidates += [Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"]
    notices += ["=" * 78, f"Python {python_record['version']}", "=" * 78]
    for candidate in python_candidates:
        if not candidate.is_file():
            continue
        try:
            text = read_license(candidate)
        except (OSError, ValueError):
            continue
        destination = output / "dependencies/licenses/python/LICENSE.txt"
        write_text(destination, text)
        python_record["license_file"] = destination.relative_to(output).as_posix()
        notices += [text.rstrip(), ""]
        break
    if not python_record["license_file"]:
        notices += ["Python's installation license file was not found in the standard fixed locations.", ""]
    inventory = {
        "schema_version": 1,
        "scope": "Installed distributions in the packaging interpreter's purelib/platlib directories.",
        "python": python_record, "distributions": packages,
    }
    write_json(output / "dependencies/installed-distributions.json", inventory)
    write_text(output / "dependencies/installed-packages.lock",
               "# Exact installed versions from the packaging environment; not a universal runtime lock.\n"
               + "\n".join(f"{item['name']}=={item['version']}" for item in packages) + "\n")
    write_text(output / "THIRD-PARTY-NOTICES.txt", "\n".join(notices).rstrip() + "\n", windows_text=True)
    return inventory


def readme() -> str:
    return """产品工作台 · Windows 技术研究交接包

1. 解压后双击 ProductWorkbench.exe。程序会打开本机浏览器，地址为
   http://127.0.0.1:8765/；若该端口被占用，会自动选择后续空闲端口。
   控制台会显示实际地址。只监听本机 localhost，不向局域网公开。
2. 运行期间保留控制台窗口。关闭控制台窗口，或在该窗口按 Ctrl+C，
   即可停止本次服务；浏览器标签页关闭不会停止服务。
3. 默认数据位置为：
   %LOCALAPPDATA%\\ProductWorkbenchResearch\\data
   首次运行从空数据开始。交接包不带原作者项目、数据库、截图、账户或登录状态。
   既有 WORKBENCH_DATA 环境变量或 --data-dir 参数可以指定其他数据位置。
4. 这是免安装的单文件 EXE，不是安装程序；不需要先安装 Python。
   首次启动可能需要解压内置资源到临时目录，请留出正常启动时间。
5. 文档生成需要本机单独安装、登录并配置 Codex CLI；实机走查还需要
   本机 ADB、已授权 USB 调试的 Android 设备或模拟器。EXE 不附带账户凭据。
   联网采集、模型调用和外部工具是否可用，取决于同事自己的环境与授权。
6. 使用说明见 docs/WORKBENCH-EXE-HANDOFF.md；接口说明见
   docs/WORKBENCH-HTTP-API.md；采集能力与数据流见 docs/ 下的中文交接说明。
   source/ 是按白名单复制的当前源码，包含本次尚未提交的代码，供研究和修改。
   源码运行或重新构建仍需要相应 Python 环境和依赖，请参考 source/ 下说明。
7. dependencies/ 记录打包环境的依赖版本和可读取许可证；完整声明见
   THIRD-PARTY-NOTICES.txt。manifest.json 列出本包文件相对路径、大小和 SHA256。

本文件只说明包结构与启动方式，不声称已在同事电脑上完成运行、设备、账号、
联网采集或商业效果验证。具体构建和验证记录以附带文档的明确记载为准。
"""


def validate_inputs(exe: Path, output: Path):
    if not exe.is_file() or exe.suffix.casefold() != ".exe" or is_reparse_point(exe):
        raise ValueError("--exe 必须指向实际存在的 Windows EXE 文件，不能使用链接。")
    with exe.open("rb") as handle:
        if handle.read(2) != b"MZ":
            raise ValueError("--exe 文件没有 Windows EXE 的 MZ 文件头。")
    if output.exists() or output.is_symlink():
        raise ValueError("--output 目录已经存在；为避免覆盖，请换一个新目录。")
    if ROOT.is_relative_to(output):
        raise ValueError("输出目录不能是源码仓库或它的上级目录。")
    for relative, _ in SOURCE_TREES:
        if output.is_relative_to(ROOT / relative):
            raise ValueError("输出目录不能位于将要复制的源码目录内；请选择 work/ 或仓库外的新目录。")
    if output.is_relative_to(ROOT / "docs"):
        raise ValueError("输出目录不能位于源码 docs/ 内。")
    for name in REQUIRED_DOCS:
        path = ROOT / "docs" / name
        if not path.is_file() or not allowed_source(path):
            raise ValueError(f"缺少交接所需文档：docs/{name}")


def package_handoff(exe: Path, output: Path) -> dict:
    exe, output = exe.expanduser().absolute(), output.expanduser().resolve()
    validate_inputs(exe, output)
    selected = source_files()
    # exist_ok=False is deliberate. Never merge with or replace an old handoff.
    output.mkdir(parents=True, exist_ok=False)
    copy_file(exe, output / "ProductWorkbench.exe")
    for source in selected:
        copy_file(source, output / "source" / source.relative_to(ROOT))
    for name in REQUIRED_DOCS + GENERAL_DOCS:
        source = ROOT / "docs" / name
        if source.is_file() and allowed_source(source):
            destination = output / "docs" / name
            copy_file(source, destination)
            # Top-level docs sit alongside source/, unlike source/docs/.
            content = destination.read_text(encoding="utf-8")
            content = re.sub(r"\]\(\.\./(workbench|packages|scripts|src|knowledge)/", r"](../source/\1/", content)
            content = content.replace("](../README.md)", "](../source/README.md)")
            write_text(destination, content)
    build_lock = ROOT / "scripts/packaging/requirements-build.lock"
    if build_lock.is_file() and allowed_source(build_lock):
        copy_file(build_lock, output / "dependencies/requirements-build.lock")
    write_text(output / "先读我.txt", readme(), windows_text=True)
    inventory = collect_notices(output)
    files = []
    for path in sorted(output.rglob("*")):
        if path.is_file():
            files.append({"path": path.relative_to(output).as_posix(),
                          "size": path.stat().st_size, "sha256": sha256(path)})
    manifest = {
        "schema_version": 1,
        "package": "ProductWorkbench-Windows-Research-Handoff",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest_scope": "All package files except manifest.json itself.",
        "source_selection": "Explicit reusable source/document allowlist; local run/account/business data excluded.",
        "source_file_count": len(selected),
        "packaging_python": inventory["python"],
        "installed_distribution_count": len(inventory["distributions"]),
        "file_count": len(files), "files": files,
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True, help="已构建的 ProductWorkbench.exe")
    parser.add_argument("--output", type=Path, required=True, help="交接输出目录，必须尚不存在")
    args = parser.parse_args()
    try:
        manifest = package_handoff(args.exe, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"交接包未完成：{exc}\n失败时已创建的目录会保留供检查；修正后请换一个新输出目录。\n")
    print(json.dumps({"package": manifest["package"], "source_file_count": manifest["source_file_count"],
                      "file_count": manifest["file_count"], "manifest": "manifest.json"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
