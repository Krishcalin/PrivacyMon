"""Structured identifier detectors (SRS section 4.1).

Each detector pairs a pattern with a validator so that no finding is produced
on pattern alone except where the SRS marks context as sufficient.
"""
from __future__ import annotations

import re

from ..models import Category, DetectorKind, Tier
from .base import COMMON_NEGATIVE, DetectorSpec
from . import validators as V

# Case-insensitive flag for alpha-bearing identifiers; numeric ones stay plain.
_I = re.IGNORECASE


def _has_intl_prefix(value: str) -> bool:
    v = value.strip()
    return v.startswith("+91") or v.startswith("0")


def build_structured_detectors() -> list[DetectorSpec]:
    return [
        DetectorSpec(
            id="aadhaar.v1",
            category=Category.AADHAAR,
            tier=Tier.CRITICAL,
            kind=DetectorKind.PATTERN_VALIDATOR,
            pattern=re.compile(r"(?<!\d)[2-9]\d{3}\s?\d{4}\s?\d{4}(?!\d)"),
            validator=V.aadhaar_valid,
            context_positive=["aadhaar", "aadhar", "uid", "uidai", "adhar"],
            context_negative=COMMON_NEGATIVE + ["uan", "pf"],
            description="Aadhaar number, 12 digits, Verhoeff check on the 12th digit.",
        ),
        DetectorSpec(
            id="aadhaar_vid.v1",
            category=Category.AADHAAR_VID,
            tier=Tier.CRITICAL,
            kind=DetectorKind.PATTERN_VALIDATOR,
            pattern=re.compile(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}\s?\d{4}(?!\d)"),
            validator=V.aadhaar_vid_valid,
            context_positive=["vid", "virtual_id", "virtualid"],
            context_negative=COMMON_NEGATIVE + ["card", "cc"],
            requires_context=True,  # 16-digit space collides with payment cards
            description="Aadhaar Virtual ID, 16 digits, Verhoeff check.",
        ),
        DetectorSpec(
            id="pan.v1",
            category=Category.PAN,
            tier=Tier.HIGH,
            kind=DetectorKind.PATTERN_VALIDATOR,
            pattern=re.compile(r"(?<![A-Z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Z0-9])", _I),
            validator=V.pan_valid,
            context_positive=["pan", "pan_no", "permanent_account", "tax_id"],
            description="Permanent Account Number; 4th char encodes holder type.",
        ),
        DetectorSpec(
            id="passport.v1",
            category=Category.PASSPORT,
            tier=Tier.HIGH,
            kind=DetectorKind.PATTERN,
            pattern=re.compile(r"(?<![A-Z0-9])[A-PR-WY][1-9]\d\s?\d{4}[1-9](?![A-Z0-9])", _I),
            context_positive=["passport", "ppt_no", "ppt", "travel_doc"],
            requires_context=True,  # structural only
            description="Indian passport number, structural pattern only.",
        ),
        DetectorSpec(
            id="voter_id.v1",
            category=Category.VOTER_ID,
            tier=Tier.HIGH,
            kind=DetectorKind.PATTERN,
            pattern=re.compile(r"(?<![A-Z0-9])[A-Z]{3}[0-9]{7}(?![A-Z0-9])", _I),
            context_positive=["epic", "voter", "election", "voter_id"],
            requires_context=True,
            description="Voter ID (EPIC), structural; context required.",
        ),
        DetectorSpec(
            id="driving_licence.v1",
            category=Category.DRIVING_LICENCE,
            tier=Tier.HIGH,
            kind=DetectorKind.PATTERN_VALIDATOR,
            pattern=re.compile(
                r"(?<![A-Z0-9])[A-Z]{2}[-\s]?\d{2}[-\s]?\d{4}[-\s]?\d{7}(?![A-Z0-9])", _I),
            validator=V.driving_licence_valid,
            context_positive=["dl", "driving", "licence", "license", "dl_no"],
            description="Driving licence; state RTO code and plausible year.",
        ),
        DetectorSpec(
            id="gstin.v1",
            category=Category.GSTIN,
            tier=Tier.MEDIUM,
            kind=DetectorKind.PATTERN_VALIDATOR,
            pattern=re.compile(
                r"(?<![A-Z0-9])[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z](?![A-Z0-9])", _I),
            validator=V.gstin_valid,
            context_positive=["gst", "gstin"],
            description="GSTIN; state code, embedded PAN and mod-36 check digit.",
        ),
        DetectorSpec(
            id="payment_card.v1",
            category=Category.PAYMENT_CARD,
            tier=Tier.HIGH,
            kind=DetectorKind.PATTERN_VALIDATOR,
            pattern=re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)"),
            validator=V.payment_card_valid,
            context_positive=["card", "cc", "card_no", "creditcard", "debitcard"],
            context_negative=COMMON_NEGATIVE,
            description="Payment card; Luhn checksum and IIN first digit 3-6.",
        ),
        DetectorSpec(
            id="upi.v1",
            category=Category.UPI_ID,
            tier=Tier.HIGH,
            kind=DetectorKind.PATTERN_VALIDATOR,
            pattern=re.compile(r"(?<![\w.\-])[\w.\-]{2,256}@[a-zA-Z]{2,64}(?![\w.\-])"),
            validator=V.upi_valid,
            context_positive=["upi", "vpa", "upi_id"],
            description="UPI VPA; the suffix must be a known PSP handle.",
        ),
        DetectorSpec(
            id="bank_account.v1",
            category=Category.BANK_ACCOUNT,
            tier=Tier.HIGH,
            kind=DetectorKind.PATTERN,
            pattern=re.compile(r"(?<!\d)\d{9,18}(?!\d)"),
            context_positive=["account", "acct", "a_c", "ac_no", "bank", "account_no"],
            context_negative=COMMON_NEGATIVE,
            requires_context=True,
            description="Bank account number; context required (9-18 digits).",
        ),
        DetectorSpec(
            id="ifsc.v1",
            category=Category.IFSC,
            tier=Tier.LOW,
            kind=DetectorKind.PATTERN_VALIDATOR,
            pattern=re.compile(r"(?<![A-Z0-9])[A-Z]{4}0[A-Z0-9]{6}(?![A-Z0-9])", _I),
            validator=V.ifsc_valid,
            context_positive=["ifsc", "branch", "ifsc_code"],
            description="IFSC code; 5th character is always 0.",
        ),
        DetectorSpec(
            id="mobile.v1",
            category=Category.MOBILE,
            tier=Tier.MEDIUM,
            kind=DetectorKind.PATTERN,
            pattern=re.compile(r"(?<![\d+])(?:\+?91[-\s]?|0[-\s]?)?[6-9]\d{4}[-\s]?\d{5}(?!\d)"),
            context_positive=["mobile", "phone", "msisdn", "contact", "cell", "mob"],
            context_negative=COMMON_NEGATIVE,
            strong_match=_has_intl_prefix,  # +91 / 0 prefix fires without context
            requires_context=True,
            description="Indian mobile; context required unless +91/0 prefix present.",
        ),
        DetectorSpec(
            id="email.v1",
            category=Category.EMAIL,
            tier=Tier.MEDIUM,
            kind=DetectorKind.PATTERN_VALIDATOR,
            pattern=re.compile(r"(?<![\w.+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?![\w\-])"),
            validator=V.email_valid,
            context_positive=["email", "mail", "e_mail", "email_id"],
            description="Email address with a dotted domain; role addresses excluded.",
        ),
        DetectorSpec(
            id="pin_code.v1",
            category=Category.PIN_CODE,
            tier=Tier.LOW,
            kind=DetectorKind.PATTERN_VALIDATOR,
            pattern=re.compile(r"(?<!\d)[1-9]\d{5}(?!\d)"),
            validator=V.pin_code_valid,
            context_positive=["pin", "pincode", "postal", "zip", "pin_code"],
            context_negative=COMMON_NEGATIVE,
            requires_context=True,
            description="Postal PIN code; address component, context required.",
        ),
        DetectorSpec(
            id="vehicle_reg.v1",
            category=Category.VEHICLE_REG,
            tier=Tier.MEDIUM,
            kind=DetectorKind.PATTERN_VALIDATOR,
            pattern=re.compile(
                r"(?<![A-Z0-9])[A-Z]{2}[-\s]?\d{1,2}[-\s]?[A-Z]{1,3}[-\s]?\d{4}(?![A-Z0-9])", _I),
            validator=V.vehicle_reg_valid,
            context_positive=["vehicle", "reg_no", "rc", "registration", "vehicle_no"],
            description="Vehicle registration; leading state RTO code.",
        ),
        DetectorSpec(
            id="epf_uan.v1",
            category=Category.EPF_UAN,
            tier=Tier.MEDIUM,
            kind=DetectorKind.PATTERN_VALIDATOR,
            pattern=re.compile(r"(?<!\d)\d{12}(?!\d)"),
            validator=V.epf_uan_valid,  # 12 digits that FAIL Verhoeff
            context_positive=["uan", "pf", "epf", "uan_no"],
            context_negative=COMMON_NEGATIVE + ["aadhaar", "aadhar"],
            requires_context=True,
            description="EPF UAN; 12 digits failing Verhoeff, context required.",
        ),
        DetectorSpec(
            id="dob.v1",
            category=Category.DOB,
            tier=Tier.MEDIUM,
            kind=DetectorKind.PATTERN_VALIDATOR,
            pattern=re.compile(
                r"(?<![\d/])(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
                r"\d{1,2}[-\s][A-Za-z]{3,9}[-\s]\d{2,4})(?![\d/])"),
            validator=V.dob_valid,
            context_positive=["dob", "birth", "born", "date_of_birth", "birthdate"],
            context_negative=["created", "updated", "modified", "expiry", "issue",
                              "txn_date", "order_date"],
            requires_context=True,
            description="Date of birth; parsed year implies age 0-110.",
        ),
    ]
