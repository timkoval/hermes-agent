#!/usr/bin/env python3
"""Context and toolset-preset resolution for Hermes Agent.

Given an active context name, resolves the context config (credential pool,
model, git identity, toolset preset) and enables only the toolsets that
preset specifies.

Contexts live under ``config.contexts``:
    contexts:
        default:
            credential_pool: ""
            model: {}
            git: {name: "", email: ""}
            preset: full
            write_scope: []

Toolset presets live under ``config.toolset_presets``:
    toolset_presets:
        full: [terminal, file, web, skills, ...]
        coding: [terminal, file, web, skills, ...]
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_PRESET = "full"
_DEFAULT_CONTEXT = "default"


# ---------------------------------------------------------------------------
# Context resolution
# ---------------------------------------------------------------------------


def resolve_context_config(
    context_name: str,
    config: Dict,
) -> Optional[Dict]:
    """Look up a named context's config dict from the loaded config.

    Returns the context dict (with all defaults filled in), or ``None``
    if the context name doesn't exist in the config.

    Always returns a dict with at least these keys:
    ``credential_pool``, ``model``, ``git``, ``preset``, ``write_scope``.
    """
    contexts: Dict = config.get("contexts", {}) if isinstance(config, dict) else {}
    if not contexts or context_name not in contexts:
        return None

    ctx = dict(contexts[context_name])  # shallow copy
    # Fill in defaults for missing keys
    ctx.setdefault("credential_pool", "")
    ctx.setdefault("model", {})
    ctx.setdefault("git", {"name": "", "email": ""})
    ctx.setdefault("preset", _DEFAULT_PRESET)
    ctx.setdefault("write_scope", [])
    return ctx


def resolve_default_context_name(config: Dict) -> str:
    """Return the name of the default context.

    The first entry in ``config.contexts`` is treated as the default.
    If no contexts are configured, returns 'default'.
    """
    contexts: Dict = config.get("contexts", {}) if isinstance(config, dict) else {}
    if isinstance(contexts, dict) and contexts:
        first = next(iter(contexts))
        return first
    return _DEFAULT_CONTEXT


def list_context_names(config: Dict) -> List[str]:
    """Return sorted list of configured context names."""
    contexts: Dict = config.get("contexts", {}) if isinstance(config, dict) else {}
    if not isinstance(contexts, dict):
        return []
    return sorted(contexts.keys())


# ---------------------------------------------------------------------------
# Toolset preset resolution
# ---------------------------------------------------------------------------


def resolve_preset(
    preset_name: str,
    config: Dict,
) -> List[str]:
    """Resolve a toolset preset name to a list of toolset strings.

    Falls back to ``"full"`` if the preset doesn't exist in the config.
    Returns an empty list only if the fallback preset is also missing.
    """
    presets: Dict = (
        config.get("toolset_presets", {})
        if isinstance(config, dict)
        else {}
    )
    if not isinstance(presets, dict):
        presets = {}

    # Direct match
    if preset_name in presets:
        return _normalize_toolset_list(presets[preset_name])

    # Fallback
    if _DEFAULT_PRESET in presets:
        logger.warning(
            "Toolset preset '%s' not found — falling back to '%s'",
            preset_name, _DEFAULT_PRESET,
        )
        return _normalize_toolset_list(presets[_DEFAULT_PRESET])

    logger.warning("No toolset presets configured at all — returning empty list")
    return []


def list_preset_names(config: Dict) -> List[str]:
    """Return sorted list of configured preset names."""
    presets: Dict = (
        config.get("toolset_presets", {})
        if isinstance(config, dict)
        else {}
    )
    if not isinstance(presets, dict):
        return []
    return sorted(presets.keys())


def _normalize_toolset_list(toolsets) -> List[str]:
    """Ensure the value is a list of strings, dropping non-strings."""
    if not isinstance(toolsets, (list, tuple)):
        return []
    return [str(t) for t in toolsets if isinstance(t, str)]


# ---------------------------------------------------------------------------
# Context-aware config override
# ---------------------------------------------------------------------------


def apply_context_to_config(
    context_name: str,
    config: Dict,
) -> Dict:
    """Merge a context's config into the root config for agent initialization.

    Returns a config dict override suitable for passing to ``init_agent``.
    The returned dict has the same shape as ``_agent_cfg``, but with
    model, credential_pool, and git overridden from the context.

    ``None`` fields mean "no override — use whatever the root config says."
    """
    ctx = resolve_context_config(context_name, config)
    if ctx is None:
        return {}  # no override

    overrides: Dict = {}

    # Model override
    ctx_model = ctx.get("model", {})
    if isinstance(ctx_model, dict) and ctx_model:
        if "default" in ctx_model:
            overrides["model"] = ctx_model["default"]
        # Copy other model fields (provider, base_url, api_key, etc.)
        overrides.setdefault("model_config_override", {})
        for k, v in ctx_model.items():
            if k != "default":
                overrides.setdefault("model_config_override", {})[k] = v

    # Credential pool override
    if ctx.get("credential_pool"):
        overrides["credential_pool"] = ctx["credential_pool"]

    # Git identity override
    ctx_git = ctx.get("git", {})
    if isinstance(ctx_git, dict) and (ctx_git.get("name") or ctx_git.get("email")):
        overrides["git_identity"] = {
            "name": ctx_git.get("name", ""),
            "email": ctx_git.get("email", ""),
        }

    return overrides
