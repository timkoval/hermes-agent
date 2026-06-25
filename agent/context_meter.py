"""Context usage estimation and system-prompt meter injection."""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Rough tokenization ratio — safe overestimate for UTF-8 text
_CHARS_PER_TOKEN = 4.0


def estimate_context_usage(agent: Any, config: Optional[Dict] = None) -> Optional[Dict]:
    """Estimate current context window usage and return a summary dict.

    Uses the agent's cumulative token counters when available, falling back
    to character-based estimation of the conversation history.

    Returns:
        { "used_tokens": int, "limit_tokens": int, "usage_pct": float,
          "message_count": int, "messages_until_compression": int }
    or None if estimation is not possible.
    """
    if not agent:
        return None

    # Context length limit
    from hermes_cli.config import load_config as _load_cfg
    cfg = config if config else _load_cfg()

    limit = getattr(agent, "_context_length", None)
    if not limit:
        _model_cfg = cfg.get("model", {}) if isinstance(cfg, dict) else {}
        provider_cfg = cfg.get("providers", {}) if isinstance(cfg, dict) else {}
        # Try agent's model name
        model_name = getattr(agent, "model", "")
        if isinstance(provider_cfg, dict) and model_name:
            for p_id, p_entry in provider_cfg.items():
                if isinstance(p_entry, dict):
                    p_models = p_entry.get("models", {}) if isinstance(p_entry.get("models"), dict) else {}
                    if isinstance(p_models, dict) and model_name in p_models:
                        m_cfg = p_models[model_name]
                        if isinstance(m_cfg, dict):
                            limit = m_cfg.get("context_length") or p_entry.get("context_length")
                            break
        if not limit:
            limit = cfg.get("model", {}).get("context_length", 128000) if isinstance(cfg, dict) else 128000

    limit = int(limit) if limit else 128000
    if limit <= 0:
        limit = 128000

    # Used tokens — prefer cumulative stats from the agent
    total_tokens = getattr(agent, "session_total_tokens", 0) or 0
    input_tokens = getattr(agent, "session_input_tokens", 0) or 0

    # If no token counters yet, estimate from conversation characters
    if total_tokens == 0 and input_tokens == 0:
        conv = getattr(agent, "conversation_history", None) or []
        char_count = sum(
            len(str(m.get("content", "")))
            for m in conv if isinstance(m, dict)
        )
        total_tokens = int(char_count / _CHARS_PER_TOKEN)

    used = max(total_tokens, input_tokens)
    pct = min(100.0, (used / limit) * 100.0)

    # Estimate messages until compression
    threshold = 1.0
    if isinstance(cfg, dict):
        comp_cfg = cfg.get("compression", {})
        if isinstance(comp_cfg, dict):
            threshold = comp_cfg.get("threshold", 0.50)
    trigger_at = limit * threshold
    usable_remaining = max(0, trigger_at - used)
    avg_msg_size = max(1, used / max(1, len(getattr(agent, "conversation_history", []) or [])))
    msgs_left = int(usable_remaining / avg_msg_size) if avg_msg_size > 0 else 0

    return {
        "used_tokens": used,
        "limit_tokens": limit,
        "usage_pct": round(pct, 1),
        "message_count": len(getattr(agent, "conversation_history", []) or []),
        "messages_until_compression": msgs_left,
    }


def build_context_usage_line(agent: Any, config: Optional[Dict] = None) -> str:
    """Build a compact context-usage status line for system prompt injection.

    Returns empty string when usage is below the warning threshold or
    when config ``compression.show_context_usage`` is False.
    """
    if not agent:
        return ""

    cfg = config
    if cfg is None:
        try:
            from hermes_cli.config import load_config as _load_cfg
            cfg = _load_cfg()
        except Exception:
            return ""

    comp_cfg = cfg.get("compression", {}) if isinstance(cfg, dict) else {}
    if not comp_cfg.get("show_context_usage", True):
        return ""

    warn_threshold = float(comp_cfg.get("usage_warning_threshold", 0.50))

    usage = estimate_context_usage(agent, cfg)
    if not usage:
        return ""

    if usage["usage_pct"] < warn_threshold * 100:
        return ""  # Below threshold — no meter

    pct = usage["usage_pct"]
    used_k = usage["used_tokens"] // 1000
    limit_k = usage["limit_tokens"] // 1000
    msgs = usage["message_count"]
    remaining = usage["messages_until_compression"]

    if remaining > 0:
        return (
            f"[Context: {pct:.0f}% — {used_k}K/{limit_k}K tokens"
            f" — ~{remaining} messages until compression]"
        )
    return (
        f"[Context: {pct:.0f}% — {used_k}K/{limit_k}K tokens"
        f" — past compression threshold]"
    )
