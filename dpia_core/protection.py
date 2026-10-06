"""Protection-state heuristics for a column (SRS section 4.5).

For each column flagged Medium or above, the sampler records whether the values
look plain, hashed, encrypted or tokenised. A plain Critical identifier is the
highest-priority finding the platform produces.
"""
from __future__ import annotations

import math
import re

from .models import ProtectionState

_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_B64_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
_HASH_LENGTHS = {32, 40, 64, 128}  # md5, sha1, sha256, sha512 hex lengths


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts: dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def infer_protection_state(
    sample_values,
    pattern=None,
    validator=None,
) -> ProtectionState:
    vals = [str(v).strip() for v in sample_values if v is not None and str(v).strip()]
    if not vals:
        return ProtectionState.UNKNOWN

    # Hashed: every value is hex of the same, hash-like fixed length.
    lengths = {len(v) for v in vals}
    if len(lengths) == 1 and (lengths & _HASH_LENGTHS) and all(_HEX_RE.match(v) for v in vals):
        return ProtectionState.HASHED

    # Encrypted: base64-ish, high entropy, length not matching the identifier.
    b64_like = [v for v in vals if _B64_RE.match(v) and len(v) >= 16]
    if len(b64_like) >= max(1, int(0.8 * len(vals))):
        avg_entropy = sum(_shannon_entropy(v) for v in b64_like) / len(b64_like)
        if avg_entropy > 3.5:
            return ProtectionState.ENCRYPTED

    # Tokenised: consistent format that matches the pattern but fails the
    # validator across the column (a format-preserving token).
    if pattern is not None and validator is not None:
        matched = [v for v in vals if pattern.search(v)]
        if matched:
            invalid = [v for v in matched if not validator(v)]
            if len(invalid) >= max(1, int(0.8 * len(matched))):
                return ProtectionState.TOKENISED

    return ProtectionState.PLAIN
