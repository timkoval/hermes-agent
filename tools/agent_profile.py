"""Agent self-profile — introspection tool for runtime state.

Returns a compact JSON snapshot of the agent's current runtime state:
model, provider, active profile/context/preset, enabled toolsets, workspace
path, memory usage per tier, session id, and git identity.
"""

import json
import logging
import subprocess
from typing import Any, Dict, List, Optional

from tools.memory_tool import ENTRY_DELIMITER, get_workspace_dir
from tools.registry import registry

logger = logging.getLogger(__name__)


def _get_active_profile() -> str:
    try:
        from agent.file_safety import _resolve_active_profile_name
        return _resolve_active_profile_name()
    except Exception:
        return "default"


def _memory_usage_line(store: Any, target: str) -> str:
    """Format a memory tier as 'pct% (used/limit chars)'."""
    entries = store._entries_for(target)
    used = len(ENTRY_DELIMITER.join(entries)) if entries else 0
    limit = store._char_limit(target)
    pct = min(100, int((used / limit) * 100)) if limit > 0 else 0
    return f"{pct}% ({used:,}/{limit:,} chars)"


def _git_identity() -> Optional[Dict[str, Optional[str]]]:
    """Return git user.name/user.email from the current repo, or None."""
    try:
        name = subprocess.check_output(
            ["git", "config", "user.name"], text=True, timeout=2
        ).strip() or None
        email = subprocess.check_output(
            ["git", "config", "user.email"], text=True, timeout=2
        ).strip() or None
        if name or email:
            return {"name": name, "email": email}
    except Exception:
        pass
    return None


def agent_profile(agent: Any = None, store: Any = None, **kwargs) -> str:
    """Return a compact JSON snapshot of the agent's runtime state."""
    result: Dict[str, Any] = {}

    if agent:
        result["model"] = getattr(agent, "model", None) or "unknown"
        result["provider"] = getattr(agent, "provider", None) or "unknown"
        result["context"] = getattr(agent, "_active_context", "default") or "default"
        result["preset"] = getattr(agent, "_active_preset", "") or ""
        result["toolsets"] = sorted(getattr(agent, "_enabled_toolsets", []))
        result["session_id"] = getattr(agent, "session_id", None)
    else:
        result["model"] = "unknown"
        result["provider"] = "unknown"
        result["context"] = "default"
        result["preset"] = ""
        result["toolsets"] = []
        result["session_id"] = None

    result["profile"] = _get_active_profile()
    result["workspace"] = str(get_workspace_dir())

    if store:
        result["memory"] = {
            "memory": _memory_usage_line(store, "memory"),
            "working": _memory_usage_line(store, "working"),
            "user": _memory_usage_line(store, "user"),
        }
    else:
        result["memory"] = {}

    result["git"] = _git_identity()

    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


def check_agent_profile_requirements() -> bool:
    return True


registry.register(
    name="agent_profile",
    toolset="memory",
    schema={
        "name": "agent_profile",
        "description": (
            "Return a compact JSON snapshot of your current runtime state: model, "
            "provider, active profile/context/preset, enabled toolsets, workspace "
            "path, memory usage per tier, session id, and git identity. Use this "
            "to orient yourself at session start."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    handler=lambda args, **kw: agent_profile(agent=kw.get("agent"), store=kw.get("store")),
    check_fn=check_agent_profile_requirements,
    emoji="🔍",
)
