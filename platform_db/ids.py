"""UUID v7 primary keys (SRS section 8: "All primary keys are UUID v7, time-ordered").

PostgreSQL 16 has no native ``uuidv7()`` (that arrives in PG 18), and Python's
``uuid`` module gains ``uuid7`` only in 3.14, so v1 generates keys application-side.
This is a pure, dependency-free RFC 9562 implementation: a 48-bit millisecond
timestamp in the high bits makes keys sort in creation order, which is the property
the SRS relies on for cursor pagination and partition-friendly inserts.
"""
from __future__ import annotations

import secrets
import time
import uuid

_LAST_MS = 0
_SEQ = 0


def uuid7() -> uuid.UUID:
    """Return a time-ordered UUID v7.

    Layout (128 bits): 48-bit unix_ts_ms | version(0x7) | 12-bit seq-or-rand |
    variant(0b10) | 62-bit random. Within a single millisecond a monotonic counter
    fills ``rand_a`` so keys minted back-to-back still order correctly; across
    milliseconds the timestamp orders them. Thread-safety is not promised (the API
    mints keys inside a single request/session); the random tail makes a collision
    between concurrent workers astronomically unlikely regardless.
    """
    global _LAST_MS, _SEQ
    now = int(time.time() * 1000) & ((1 << 48) - 1)
    if now > _LAST_MS:
        _LAST_MS = now
        _SEQ = 0                             # fresh ms: counter starts at 0
    else:
        # The clock did not advance (or went backwards): stay on the last ms and
        # bump the 12-bit counter. On overflow, borrow a millisecond into the future
        # rather than reuse — the effective timestamp is NEVER allowed to decrease,
        # which is what keeps keys strictly ordered under a tight mint loop.
        _SEQ += 1
        if _SEQ > 0xFFF:
            _SEQ = 0
            _LAST_MS = (_LAST_MS + 1) & ((1 << 48) - 1)
    rand_b = secrets.randbits(62)            # 62 bits of entropy per key
    value = (_LAST_MS << 80) | (0x7 << 76) | (_SEQ << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)
