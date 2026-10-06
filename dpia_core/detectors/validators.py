"""Structural and checksum validators for Indian personal identifiers.

Regex alone over-matches badly on Indian data (a 12-digit UAN looks like an
Aadhaar, a 10-digit order number like a mobile), so these validators gate the
pattern detectors (SRS section 4.1). Each ``*_valid`` function takes the raw
matched string and returns a bool; generator helpers (``verhoeff_checksum``,
``gstin_check_char``) exist so test fixtures can build internally-consistent
valid samples.
"""
from __future__ import annotations

import datetime as _dt
import re

# --------------------------------------------------------------------------
# Verhoeff checksum (Aadhaar, Aadhaar VID)
# --------------------------------------------------------------------------
_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_VERHOEFF_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def _digits(value: str) -> list[int]:
    return [int(c) for c in value if c.isdigit()]


def verhoeff_validate(value: str) -> bool:
    """True if the full number (including check digit) satisfies Verhoeff."""
    digits = _digits(value)
    if not digits:
        return False
    c = 0
    for i, item in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][item]]
    return c == 0


def verhoeff_checksum(value: str) -> int:
    """Return the Verhoeff check digit to append to ``value`` (no check digit)."""
    digits = _digits(value)
    c = 0
    for i, item in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][item]]
    return _VERHOEFF_INV[c]


def aadhaar_valid(value: str) -> bool:
    digits = _digits(value)
    if len(digits) != 12 or digits[0] in (0, 1):
        return False
    return verhoeff_validate(value)


def aadhaar_vid_valid(value: str) -> bool:
    digits = _digits(value)
    return len(digits) == 16 and verhoeff_validate(value)


# --------------------------------------------------------------------------
# Luhn checksum (payment cards)
# --------------------------------------------------------------------------
def luhn_validate(value: str) -> bool:
    digits = _digits(value)
    if len(digits) < 12:
        return False
    total = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def luhn_checksum(value: str) -> int:
    """Return the Luhn check digit to append to ``value`` (no check digit)."""
    digits = _digits(value)
    total = 0
    parity = (len(digits) + 1) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - (total % 10)) % 10


# Major IIN first digits: 3 Amex/Diners, 4 Visa, 5 Mastercard/Maestro, 6 RuPay/Discover.
def payment_card_valid(value: str) -> bool:
    digits = _digits(value)
    if not (13 <= len(digits) <= 19):
        return False
    if digits[0] not in (3, 4, 5, 6):
        return False
    return luhn_validate(value)


# --------------------------------------------------------------------------
# PAN
# --------------------------------------------------------------------------
# 4th char is the holder type (SRS section 4.1).
_PAN_ENTITY = set("PCHFATBLJG")
_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


def pan_valid(value: str) -> bool:
    v = value.strip().upper()
    if not _PAN_RE.match(v):
        return False
    return v[3] in _PAN_ENTITY


# --------------------------------------------------------------------------
# GSTIN (mod-36 check char, embedded PAN, state code)
# --------------------------------------------------------------------------
_GST_CODE = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_GST_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
# State codes 01-38 are assigned (SRS says 01-38).
_GST_STATES = {f"{n:02d}" for n in range(1, 39)}


def gstin_check_char(first14: str) -> str:
    """GSTN mod-36 check character for the first 14 characters."""
    factor = 2
    total = 0
    n = len(_GST_CODE)
    for ch in reversed(first14.upper()):
        cp = _GST_CODE.index(ch)
        prod = factor * cp
        total += prod // n + prod % n
        factor = 1 if factor == 2 else 2
    return _GST_CODE[(n - (total % n)) % n]


def gstin_valid(value: str) -> bool:
    v = value.strip().upper()
    if not _GST_RE.match(v):
        return False
    if v[:2] not in _GST_STATES:
        return False
    if not pan_valid(v[2:12]):
        return False
    return gstin_check_char(v[:14]) == v[14]


# --------------------------------------------------------------------------
# IFSC
# --------------------------------------------------------------------------
_IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def ifsc_valid(value: str) -> bool:
    # 5th character is always 0 (reserved). Bank-code-in-RBI-list check needs a
    # data file and is deferred; structural match is specific enough on its own.
    return bool(_IFSC_RE.match(value.strip().upper()))


# --------------------------------------------------------------------------
# State / RTO codes (driving licence, vehicle registration)
# --------------------------------------------------------------------------
_RTO_STATES = {
    "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ", "HR",
    "HP", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP", "MZ",
    "NL", "OD", "OR", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK", "UA",
    "UP", "WB", "AN",
}
_DL_RE = re.compile(r"^([A-Z]{2})[-\s]?(\d{2})[-\s]?(\d{4})[-\s]?(\d{7})$")


def driving_licence_valid(value: str) -> bool:
    m = _DL_RE.match(value.strip().upper())
    if not m:
        return False
    if m.group(1) not in _RTO_STATES:
        return False
    year = int(m.group(3))
    return 1950 <= year <= _dt.date.today().year


_VEHICLE_RE = re.compile(r"^([A-Z]{2})[-\s]?(\d{1,2})[-\s]?([A-Z]{1,3})[-\s]?(\d{4})$")


def vehicle_reg_valid(value: str) -> bool:
    m = _VEHICLE_RE.match(value.strip().upper())
    return bool(m) and m.group(1) in _RTO_STATES


# --------------------------------------------------------------------------
# PIN code (first digit maps to a postal region 1-8; 9 is Army Postal Service)
# --------------------------------------------------------------------------
_PIN_RE = re.compile(r"^[1-9][0-9]{5}$")


def pin_code_valid(value: str) -> bool:
    v = value.strip()
    return bool(_PIN_RE.match(v)) and v[0] in "12345678"


# --------------------------------------------------------------------------
# EPF UAN (12 digits that FAIL Verhoeff — this is what distinguishes it from
# an Aadhaar, SRS section 4.1)
# --------------------------------------------------------------------------
def epf_uan_valid(value: str) -> bool:
    digits = _digits(value)
    return len(digits) == 12 and not verhoeff_validate(value)


# --------------------------------------------------------------------------
# UPI VPA (handle@psp) — the PSP suffix must be a known handle
# --------------------------------------------------------------------------
_UPI_PSPS = {
    "okaxis", "okhdfcbank", "okicici", "oksbi", "ybl", "ibl", "axl", "paytm",
    "apl", "upi", "aubank", "barodampay", "cnrb", "fbl", "idfcbank", "indus",
    "kbl", "kotak", "pingpay", "rbl", "sbi", "yesbank", "hdfcbank", "icici",
    "axisbank", "jupiteraxis", "slc", "waaxis", "yapl", "freecharge",
}


def upi_valid(value: str) -> bool:
    v = value.strip().lower()
    if "@" not in v:
        return False
    handle, _, psp = v.rpartition("@")
    if not handle or "." in psp:  # a dot in the suffix means it is an email domain
        return False
    return psp in _UPI_PSPS


# --------------------------------------------------------------------------
# Email (reject system / role addresses, require a dotted domain)
# --------------------------------------------------------------------------
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_EMAIL_SYSTEM_LOCALS = {
    "noreply", "no-reply", "donotreply", "do-not-reply", "admin", "postmaster",
    "mailer-daemon", "root", "webmaster", "hostmaster", "abuse",
}


def email_valid(value: str) -> bool:
    v = value.strip()
    if not _EMAIL_RE.match(v):
        return False
    local = v.split("@", 1)[0].lower()
    return local not in _EMAIL_SYSTEM_LOCALS


# --------------------------------------------------------------------------
# Date of birth plausibility (parsed year implies a living person's age)
# --------------------------------------------------------------------------
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_dob(value: str) -> _dt.date | None:
    """Parse the date formats listed in SRS section 4.1, else None."""
    v = value.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
        try:
            return _dt.datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    m = re.match(r"^(\d{1,2})[-\s]([A-Za-z]{3})[a-z]*[-\s](\d{2,4})$", v)
    if m:
        mon = _MONTHS.get(m.group(2).lower())
        if mon:
            year = int(m.group(3))
            if year < 100:
                year += 1900 if year > 30 else 2000
            try:
                return _dt.date(year, mon, int(m.group(1)))
            except ValueError:
                return None
    return None


def dob_valid(value: str) -> bool:
    d = parse_dob(value)
    if d is None:
        return False
    age = (_dt.date.today() - d).days / 365.25
    return 0 <= age <= 110


def age_from_dob(value: str) -> float | None:
    d = parse_dob(value)
    if d is None:
        return None
    return (_dt.date.today() - d).days / 365.25
