"""Allowlist-based attribute sanitization and canary secret protection."""

from __future__ import annotations

from typing import Any

DEFAULT_REDACT_KEYS = {
    "api_key",
    "apikey",
    "secret",
    "password",
    "token",
    "authorization",
    "auth",
    "bearer",
    "credential",
    "private_key",
}

PAYLOAD_KEYS = {
    "payload",
    "content",
    "prompt",
    "completion",
    "messages",
    "input_data",
    "output_data",
}


class RedactionEngine:
    """Sanitizes span and event attributes to enforce privacy-by-default."""

    def __init__(
        self,
        redact_keys: list[str] | set[str] | None = None,
        record_payloads: bool = False,
        allowlist_keys: set[str] | None = None,
        max_string_length: int = 512,
    ) -> None:
        self.redact_keys: set[str] = (
            {k.lower() for k in redact_keys} if redact_keys is not None else DEFAULT_REDACT_KEYS
        )
        self.record_payloads: bool = record_payloads
        self.allowlist_keys: set[str] | None = (
            {k.lower() for k in allowlist_keys} if allowlist_keys is not None else None
        )
        self.max_string_length: int = max_string_length

    def is_sensitive_key(self, key: str) -> bool:
        """Check if attribute key matches sensitive token patterns."""
        key_lower = key.lower()
        return any(sensitive in key_lower for sensitive in self.redact_keys)

    def sanitize_value(self, key: str, value: Any) -> Any:
        """Recursively sanitize attribute values."""
        key_lower = key.lower()

        if self.is_sensitive_key(key_lower):
            return "[REDACTED]"

        if not self.record_payloads and key_lower in PAYLOAD_KEYS:
            if isinstance(value, (str, bytes)):
                return f"[PAYLOAD_OMITTED: {len(value)} bytes]"
            elif isinstance(value, (list, dict)):
                return f"[PAYLOAD_OMITTED: {len(value)} items]"
            return "[PAYLOAD_OMITTED]"

        if isinstance(value, dict):
            return {str(k): self.sanitize_value(str(k), v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.sanitize_value(key, item) for item in value]
        elif isinstance(value, str):
            if len(value) > self.max_string_length:
                return value[: self.max_string_length] + "...[TRUNCATED]"
            return value
        elif isinstance(value, (int, float, bool)) or value is None:
            return value
        else:
            return str(value)

    def sanitize(self, attributes: dict[str, Any] | None) -> dict[str, Any]:
        """Sanitize an attribute dictionary in-place and return the cleaned dictionary."""
        if not attributes:
            return {}

        sanitized: dict[str, Any] = {}
        for k, v in attributes.items():
            k_str = str(k)
            if self.allowlist_keys is not None and k_str.lower() not in self.allowlist_keys:
                continue
            sanitized[k_str] = self.sanitize_value(k_str, v)

        return sanitized
