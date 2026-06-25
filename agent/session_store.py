"""Persistent checkpoint bookmarks stored in the workspace.

Used by /checkpoint and --resume-checkpoint.
"""

import time
from pathlib import Path
from typing import Dict, List, Optional


class CheckpointStore:
    """Persistent checkpoint bookmarks stored in CHECKPOINTS.md."""

    def __init__(self, workspace_dir: Optional[Path] = None):
        if workspace_dir is None:
            from tools.memory_tool import get_workspace_dir
            workspace_dir = get_workspace_dir()
        self._path = workspace_dir / "CHECKPOINTS.md"

    def save(self, description: str, session_id: str, cwd: str = "") -> str:
        """Append a checkpoint entry. Returns confirmation message."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
        entry = (
            f"## {timestamp}\n"
            f"session: {session_id}\n"
            f"description: {description}\n"
        )
        if cwd:
            entry += f"cwd: {cwd}\n"
        entry += "\n"

        with open(self._path, "a", encoding="utf-8") as f:
            f.write(entry)

        return f"Checkpoint saved: {description[:60]}"

    def list_recent(self, limit: int = 10) -> List[Dict]:
        """Return recent checkpoints."""
        if not self._path.exists():
            return []
        content = self._path.read_text(encoding="utf-8")
        return list(self._parse_checkpoints(content))[-limit:]

    def last(self) -> Optional[Dict]:
        """Return the most recent checkpoint, or None."""
        items = list(self._parse_all())
        return items[-1] if items else None

    def resolve(self, index: int = 0) -> Optional[str]:
        """Resolve a checkpoint index to a session ID. 0 = most recent."""
        items = list(self._parse_all())
        if not items:
            return None
        idx = min(index, len(items) - 1)
        return items[-(idx + 1)]["session_id"]

    def _parse_all(self):
        return self._parse_checkpoints(
            self._path.read_text(encoding="utf-8")
            if self._path.exists() else ""
        )

    @staticmethod
    def _parse_checkpoints(text: str):
        """Yield checkpoint dicts from CHECKPOINTS.md content."""
        current = {}
        for line in text.split("\n"):
            if line.startswith("## "):
                if current.get("session_id"):
                    yield current
                current = {"timestamp": line[3:].strip(), "description": ""}
            elif line.startswith("session: "):
                current["session_id"] = line.split("session: ", 1)[1].strip()
            elif line.startswith("description: "):
                current["description"] = line.split("description: ", 1)[1].strip()
            elif line.startswith("cwd: "):
                current["cwd"] = line.split("cwd: ", 1)[1].strip()
        if current.get("session_id"):
            yield current
