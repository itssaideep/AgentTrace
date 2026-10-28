"""Unit tests for RedactionEngine and canary secret leak prevention."""

from __future__ import annotations

from agenttrace.instrumentation.redaction import RedactionEngine


def test_canary_secret_leak_prevention() -> None:
    """Plant canary secrets in attributes and assert zero leakage."""
    engine = RedactionEngine()

    canary_token = "sk-live-canary-secret-token-xyz987"
    raw_attrs = {
        "user_id": 42,
        "api_key": canary_token,
        "nested": {
            "OPENAI_SECRET": canary_token,
            "normal_field": "safe_value",
            "db_password": "supersecretpassword",
        },
        "items_list": [
            {"bearer_token": "bearer 12345"},
            "harmless_string",
        ],
    }

    sanitized = engine.sanitize(raw_attrs)

    # Convert entire sanitized dict to string and assert canary never appears
    sanitized_str = str(sanitized)
    assert canary_token not in sanitized_str
    assert "supersecretpassword" not in sanitized_str
    assert "bearer 12345" not in sanitized_str

    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["OPENAI_SECRET"] == "[REDACTED]"
    assert sanitized["nested"]["normal_field"] == "safe_value"
    assert sanitized["nested"]["db_password"] == "[REDACTED]"
    assert sanitized["items_list"][0]["bearer_token"] == "[REDACTED]"
    assert sanitized["items_list"][1] == "harmless_string"


def test_privacy_by_default_payload_omission() -> None:
    """Verify large payloads and prompt contents are omitted by default."""
    engine = RedactionEngine(record_payloads=False)

    large_prompt = "You are a helpful research agent. " * 50
    attrs = {
        "operation": "chat_completion",
        "prompt": large_prompt,
        "messages": [{"role": "user", "content": "hello"}],
    }

    sanitized = engine.sanitize(attrs)
    assert sanitized["operation"] == "chat_completion"
    assert "[PAYLOAD_OMITTED:" in sanitized["prompt"]
    assert "[PAYLOAD_OMITTED:" in sanitized["messages"]


def test_opt_in_payload_retention() -> None:
    """Verify payloads are retained when explicitly enabled."""
    engine = RedactionEngine(record_payloads=True)

    attrs = {
        "prompt": "Summarize this document.",
        "api_key": "secret_key_123",
    }

    sanitized = engine.sanitize(attrs)
    assert sanitized["prompt"] == "Summarize this document."
    assert sanitized["api_key"] == "[REDACTED]"  # Secrets are still redacted even with payloads on


def test_string_truncation() -> None:
    """Verify excessive string attributes are capped at max_string_length."""
    engine = RedactionEngine(max_string_length=20)
    attrs = {"long_string": "abcdefghijklmnopqrstuvwxyz1234567890"}

    sanitized = engine.sanitize(attrs)
    assert sanitized["long_string"] == "abcdefghijklmnopqrst...[TRUNCATED]"
