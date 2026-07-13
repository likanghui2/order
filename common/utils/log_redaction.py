import json
import re
from copy import deepcopy


_CARD_KEYS = {"cardnumber", "card_number", "pan"}
_SECRET_KEYS = {
    "cardcvv",
    "card_cvv",
    "cvv",
    "securitycode",
    "security_code",
    "authorization",
    "xdtoken",
    "x-d-token",
    "clientsecret",
    "client_secret",
    "password",
    "cookie",
    "proxy",
}
_KEY_VALUE_PATTERN = re.compile(
    r"(?P<prefix>[\"']?(?P<key>cardNumber|card_number|pan|cardCVV|card_cvv|CVV|cvv|"
    r"securityCode|security_code|authorization|x-d-token|client_secret|password|cookie|proxy)"
    r"[\"']?\s*[:=]\s*[\"'])(?P<value>[^\"']*)(?P<suffix>[\"'])",
    re.IGNORECASE,
)
_BEARER_PATTERN = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+")
_PAN_PATTERN = re.compile(r"(?<!\d)\d{12,19}(?!\d)")


def _normalized_key(value) -> str:
    return str(value or "").strip().lower().replace("-", "")


def _mask_card(value) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return f"{'*' * max(0, len(digits) - 4)}{digits[-4:]}" if digits else "[REDACTED]"


def _redact_string(value: str) -> str:
    stripped = value.strip()
    if stripped and stripped[0] in "[{":
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            pass
        else:
            return json.dumps(redact_sensitive(parsed), ensure_ascii=False)

    def replacement(match: re.Match) -> str:
        key = _normalized_key(match.group("key"))
        replacement_value = _mask_card(match.group("value")) if key in {
            _normalized_key(item) for item in _CARD_KEYS
        } else "[REDACTED]"
        return f"{match.group('prefix')}{replacement_value}{match.group('suffix')}"

    redacted = _KEY_VALUE_PATTERN.sub(replacement, value)
    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
    return _PAN_PATTERN.sub(lambda match: _mask_card(match.group(0)), redacted)


def redact_sensitive(value):
    if isinstance(value, dict):
        result = {}
        for key, item in deepcopy(value).items():
            normalized = _normalized_key(key)
            if normalized in {_normalized_key(name) for name in _CARD_KEYS}:
                result[key] = _mask_card(item)
            elif normalized in {_normalized_key(name) for name in _SECRET_KEYS}:
                result[key] = "[REDACTED]"
            else:
                result[key] = redact_sensitive(item)
        return result
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    if isinstance(value, str):
        return _redact_string(value)
    return value
