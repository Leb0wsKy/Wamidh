"""Message signatures (contracts/mqtt_topics.md, "Signatures").

sig = base64( HMAC-SHA256(key, canonical(payload without "sig"))[:16] )
canonical = JSON with keys sorted, no whitespace, UTF-8. Truncation to 16 bytes keeps the LoRa
packet small while leaving 128 bits against forgery.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

SIG_BYTES = 16


def canonical(payload: Mapping[str, Any]) -> bytes:
    body = {k: v for k, v in payload.items() if k != "sig"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sign(payload: Mapping[str, Any], key: bytes) -> str:
    mac = hmac.new(key, canonical(payload), hashlib.sha256).digest()[:SIG_BYTES]
    return base64.b64encode(mac).decode()


def verify(message: Mapping[str, Any], key: bytes) -> bool:
    """True only if `message` carries a valid signature for its other fields."""
    sig = message.get("sig")
    if not isinstance(sig, str):
        return False
    try:
        given = base64.b64decode(sig, validate=True)
    except (binascii.Error, ValueError):
        return False
    expected = hmac.new(key, canonical(message), hashlib.sha256).digest()[:SIG_BYTES]
    return hmac.compare_digest(given, expected)
