"""Output-directory state: aw.json config, checkpoint, per-device lock, timings."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from typing import Any, Iterator

from .errors import AwError

PACKAGE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


class Workspace:
    def __init__(self, out_dir: str | Path):
        self.root = Path(out_dir).expanduser().resolve()
        self.config_path = self.root / "aw.json"
        self.checkpoint_path = self.root / "capture-session.json"
        self.map_path = self.root / "research-map.json"
        self.observations = self.root / "observations"

    @property
    def initialized(self) -> bool:
        return self.config_path.is_file()

    def config(self) -> dict[str, Any]:
        data = read_json(self.config_path)
        if not data:
            raise AwError("NOT_INITIALIZED", f"{self.root} 尚未初始化，先运行 aw init。")
        return data

    def save_config(self, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_json(self.config_path, data)

    def checkpoint(self) -> dict[str, Any]:
        return read_json(self.checkpoint_path, {}) or {}

    def save_checkpoint(self, data: dict[str, Any]) -> None:
        atomic_json(self.checkpoint_path, {**data, "updated_at": now_iso()})

    def observation(self, observation_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"obs-[a-f0-9]{16}", observation_id or ""):
            raise AwError("BAD_ARGS", "observation id 格式应为 obs-<16位十六进制>。")
        data = read_json(self.observations / f"{observation_id}.json")
        if not data:
            raise AwError("STALE_OBSERVATION", f"找不到观察记录 {observation_id}。")
        return data

    def log_timing(self, command: str, ok: bool, seconds: float, phases: list[dict]) -> None:
        if not self.root.is_dir():
            return
        with (self.root / "timings.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": now_iso(), "command": command, "ok": ok, "seconds": round(seconds, 4),
                                     "adb_calls": len(phases), "phases": phases}, ensure_ascii=False) + "\n")


@contextmanager
def device_lock(serial: str) -> Iterator[None]:
    """Hold an OS lock for the complete operation; process exit releases it.

    Keep one stable file per device. Deleting/replacing it could let two Unix
    processes lock different inodes, or remove another process's Windows lock.
    The PID written inside is diagnostic only, never a lease or stale heuristic.
    """
    directory = Path(tempfile.gettempdir()) / "android-walkthrough-locks"
    directory.mkdir(exist_ok=True)
    path = directory / (hashlib.sha256(serial.encode()).hexdigest()[:24] + ".lock")
    handle = os.fdopen(os.open(path, os.O_CREAT | os.O_RDWR, 0o600), "r+b", buffering=0)
    locked = False
    try:
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                # Windows permits locking a byte beyond EOF, including a new file.
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            raise AwError("DEVICE_LOCKED", f"设备 {serial} 已有操作运行；请等待持有者结束，不要删除锁文件。") from None
        handle.seek(0)
        handle.write(str(os.getpid()).encode("ascii"))
        handle.truncate()
        yield
    finally:
        try:
            if locked:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
