"""Agent self-profile — introspection tool for runtime state.

Returns active context, model, preset, toolset list, workspace path,
memory usage per tier, context usage %, and git identity.
"""

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def agent_profile(agent: Any = None, **kwargs) -> str:
    """Return a JSON snapshot of the agent's current runtime state."""
    store = kwargs.get("store")
    result: Dict = {}

    result["model"] = getattr(agent, "model", "unknown") if agent else "unknown"
    result["provider"] = getattr(agent, "provider", "unknown") if agent else "unknown"
    result["profile"] = _get_active_profile()
    result["session_id"] = getattr(agent, "session_id", None) if agent else None

    if agent:
        result["tools_count"] = len(getattr(agent, "valid_tool_names", []))
        result["toolsets"] = sorted(getattr(agent, "_enabled_toolsets", []))
        result["context"] = getattr(agent, "_active_context", "default")
        result["preset"] = getattr(agent, "_active_preset", "")

    from tools.memory_tool import get_workspace_dir
    result["workspace"] = str(get_workspace_dir())

    if store:
        result["memory"] = {}
        for target in ["memory", "user", "working"]:
            entries = store._entries_for(target)
            current = len(store.ENTRY_DELIMITER.join(entries)) if entries else 0
            limit = store._char_limit(target)
            pct = min(100, int((current / limit) * 100)) if limit > 0 else 0
            result["memory"][target] = {
                "entries": len(entries),
                "used_chars": current,
                "limit_chars": limit,
                "usage_pct": pct,
            }

    try:
        import subprocess
        git_name = subprocess.check_output(
            ["git", "config", "user.name"], text=True, timeout=2
        ).strip()
        git_email = subprocess.check_output(
            ["git", "config", "user.email"], text=True, timeout=2
        ).strip()
        result["git"] = {"name": git_name or None, "email": git_email or None}
    except Exception:
        result["git"] = None

    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


def _get_active_profile() -> str:
    try:
        from agent.file_safety import _resolve_active_profile_name
        return _resolve_active_profile_name()
    except Exception:
        return "default"


def check_agent_profile_requirements() -> bool:
    return True


# --- Registry ---
from tools.registry import registry

registry.register(
    name="agent_profile",
    toolset="core",
    schema={
        "name": "agent_profile",
        "description": (
            "Return a JSON snapshot of your current runtime state: active model, "
            "provider, toolsets, workspace path, memory usage per tier (permanent, "
            "working, user), context window pressure, and git identity. Use this to "
            "orient yourself at session start."
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
