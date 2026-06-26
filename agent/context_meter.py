"""Context usage estimation for /status and the TUI status bar."""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Rough tokenization ratio — safe overestimate for UTF-8 text
_CHARS_PER_TOKEN = 4.0


def _resolve_context_length(agent: Any, cfg: Dict) -> int:
    """Resolve the agent's context window limit.

    Prefers the compressor's context_length, then agent._context_length,
    then provider/model config, then a safe default.
    """
    compressor = getattr(agent, "context_compressor", None)
    if compressor:
        limit = getattr(compressor, "context_length", 0) or 0
        if limit > 0:
            return limit

    limit = getattr(agent, "_context_length", None)
    if limit:
        return int(limit)

    model_name = getattr(agent, "model", "")
    provider_cfg = cfg.get("providers", {}) if isinstance(cfg, dict) else {}
    if isinstance(provider_cfg, dict) and model_name:
        for p_entry in provider_cfg.values():
            if not isinstance(p_entry, dict):
                continue
            p_models = p_entry.get("models", {}) if isinstance(p_entry.get("models"), dict) else {}
            if isinstance(p_models, dict) and model_name in p_models:
                m_cfg = p_models[model_name]
                if isinstance(m_cfg, dict):
                    limit = m_cfg.get("context_length") or p_entry.get("context_length")
                    if limit:
                        return int(limit)

    return int(cfg.get("model", {}).get("context_length", 128000)) if isinstance(cfg, dict) else 128000


def estimate_context_usage(agent: Any, config: Optional[Dict] = None) -> Optional[Dict]:
    """Estimate current context window usage for /status.

    Returns:
        { "used_tokens": int, "limit_tokens": int, "usage_pct": float,
          "message_count": int, "messages_until_compression": int }
    or None if estimation is not possible.
    """
    if not agent:
        return None

    from hermes_cli.config import load_config as _load_cfg
    cfg = config if config is not None else _load_cfg()
    if not isinstance(cfg, dict):
        cfg = {}

    limit = _resolve_context_length(agent, cfg)
    if limit <= 0:
        limit = 128000

    # Prefer the compressor's last prompt token count (same source as the
    # status bar), then cumulative session counters, then char estimation.
    compressor = getattr(agent, "context_compressor", None)
    used = 0
    if compressor:
        used = getattr(compressor, "last_prompt_tokens", 0) or 0
        if used < 0:
            used = 0

    if used == 0:
        used = getattr(agent, "session_total_tokens", 0) or 0

    if used == 0:
        conv = getattr(agent, "conversation_history", None) or []
        char_count = sum(
            len(str(m.get("content", "")))
            for m in conv if isinstance(m, dict)
        )
        used = int(char_count / _CHARS_PER_TOKEN)

    pct = min(100.0, (used / limit) * 100.0)

    conv = getattr(agent, "conversation_history", None) or []
    message_count = len(conv)

    # Estimate messages until compression threshold
    comp_cfg = cfg.get("compression", {}) if isinstance(cfg, dict) else {}
    threshold = float(comp_cfg.get("threshold", 0.50)) if isinstance(comp_cfg, dict) else 0.50
    trigger_at = limit * threshold
    usable_remaining = max(0, trigger_at - used)
    avg_msg_size = max(1, used / max(1, message_count))
    msgs_left = int(usable_remaining / avg_msg_size) if avg_msg_size > 0 else 0

    return {
        "used_tokens": used,
        "limit_tokens": limit,
        "usage_pct": round(pct, 1),
        "message_count": message_count,
        "messages_until_compression": msgs_left,
    }


def build_context_usage_line(agent: Any, config: Optional[Dict] = None) -> str:
    """Build the human-readable /status context line.

    Format: "Context: 12% — 14K/128K tokens, ~85 messages until compression"
    """
    usage = estimate_context_usage(agent, config)
    if not usage:
        return "Context: unknown"

    pct = usage["usage_pct"]
    used_k = usage["used_tokens"] // 1000
    limit_k = usage["limit_tokens"] // 1000
    remaining = usage["messages_until_compression"]

    if remaining > 0:
        return (
            f"Context: {pct:.0f}% — {used_k}K/{limit_k}K tokens, "
            f"~{remaining} messages until compression"
        )
    return (
        f"Context: {pct:.0f}% — {used_k}K/{limit_k}K tokens, "
        f"past compression threshold"
    )
