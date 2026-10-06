"""Core domain types for the PrivacyMon DPIA detection engine.

These are deliberately dependency-free dataclasses and enums so that
``dpia_core`` can be published as a standalone, reusable library
(see SRS section 14, open item on open-source release).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Tier(str, Enum):
    """Sensitivity tier (SRS section 4.3)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Ordered low -> critical, used for co-occurrence uplift and risk weighting.
TIER_ORDER: list[Tier] = [Tier.LOW, Tier.MEDIUM, Tier.HIGH, Tier.CRITICAL]

# Tier weight W_c used by the risk engine (SRS section 5.3).
TIER_WEIGHT: dict[Tier, int] = {
    Tier.LOW: 1,
    Tier.MEDIUM: 2,
    Tier.HIGH: 4,
    Tier.CRITICAL: 8,
}


def tier_uplift(tier: Tier, steps: int = 1) -> Tier:
    """Raise ``tier`` by ``steps`` levels, capped at CRITICAL (SRS 4.3)."""
    idx = TIER_ORDER.index(tier)
    return TIER_ORDER[min(idx + steps, len(TIER_ORDER) - 1)]


class DetectorKind(str, Enum):
    """How a detector reaches its verdict; sets the base score (SRS 4.4)."""

    PATTERN = "pattern"                 # B = 0.35
    PATTERN_VALIDATOR = "pattern_validator"  # B = 0.70
    NER = "ner"                         # B = 0.45
    DICTIONARY = "dictionary"           # B = 0.40


# Base score B per detector kind (SRS section 4.4).
BASE_SCORE: dict[DetectorKind, float] = {
    DetectorKind.PATTERN: 0.35,
    DetectorKind.PATTERN_VALIDATOR: 0.70,
    DetectorKind.NER: 0.45,
    DetectorKind.DICTIONARY: 0.40,
}


class ProtectionState(str, Enum):
    """Storage protection heuristic for a column (SRS section 4.5)."""

    PLAIN = "plain"
    HASHED = "hashed"
    ENCRYPTED = "encrypted"
    TOKENISED = "tokenised"
    UNKNOWN = "unknown"


class ReviewState(str, Enum):
    """Reviewer decision on a finding (SRS FR-4.6)."""

    NEW = "new"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    RECLASSIFIED = "reclassified"
    SUPPRESSED = "suppressed"


class ScanProfile(str, Enum):
    """Scan depth (SRS FR-3.4)."""

    QUICK = "quick"        # schema and names only, H = 0
    STANDARD = "standard"  # plus value sampling
    DEEP = "deep"          # higher cap, NER enabled


class Category(str, Enum):
    """Personal-data categories the detectors recognise (SRS section 4)."""

    # Structured identifiers (4.1)
    AADHAAR = "aadhaar"
    AADHAAR_VID = "aadhaar_vid"
    PAN = "pan"
    PASSPORT = "passport"
    VOTER_ID = "voter_id"
    DRIVING_LICENCE = "driving_licence"
    GSTIN = "gstin"
    BANK_ACCOUNT = "bank_account"
    IFSC = "ifsc"
    PAYMENT_CARD = "payment_card"
    UPI_ID = "upi_id"
    MOBILE = "mobile"
    EMAIL = "email"
    PIN_CODE = "pin_code"
    VEHICLE_REG = "vehicle_reg"
    EPF_UAN = "epf_uan"
    DOB = "dob"
    # Unstructured / dictionary / NER (4.2)
    PERSON_NAME = "person_name"
    ADDRESS = "address"
    GENDER = "gender"
    HEALTH = "health"
    BIOMETRIC = "biometric"
    CASTE_RELIGION_POLITICAL = "caste_religion_political"
    CHILDREN_DATA = "children_data"
    PHOTO_ID = "photo_id"


# Human-readable labels for reports and UI.
CATEGORY_LABEL: dict[Category, str] = {
    Category.AADHAAR: "Aadhaar number",
    Category.AADHAAR_VID: "Aadhaar Virtual ID",
    Category.PAN: "PAN",
    Category.PASSPORT: "Passport number",
    Category.VOTER_ID: "Voter ID (EPIC)",
    Category.DRIVING_LICENCE: "Driving licence",
    Category.GSTIN: "GSTIN",
    Category.BANK_ACCOUNT: "Bank account number",
    Category.IFSC: "IFSC code",
    Category.PAYMENT_CARD: "Payment card number",
    Category.UPI_ID: "UPI ID / VPA",
    Category.MOBILE: "Mobile number",
    Category.EMAIL: "Email address",
    Category.PIN_CODE: "PIN code",
    Category.VEHICLE_REG: "Vehicle registration",
    Category.EPF_UAN: "EPF UAN",
    Category.DOB: "Date of birth",
    Category.PERSON_NAME: "Person name",
    Category.ADDRESS: "Postal address",
    Category.GENDER: "Gender",
    Category.HEALTH: "Health data",
    Category.BIOMETRIC: "Biometric data",
    Category.CASTE_RELIGION_POLITICAL: "Caste / religion / political affiliation",
    Category.CHILDREN_DATA: "Children's data",
    Category.PHOTO_ID: "Photograph / scanned ID",
}


class ConfidenceLabel(str, Enum):
    """Threshold bands for display (SRS section 4.4)."""

    LIKELY = "likely"              # C >= 0.80
    NEEDS_REVIEW = "needs_review"  # 0.50 <= C < 0.80
    HIDDEN = "hidden"              # C < 0.50 (kept, hidden by default)


def confidence_label(
    confidence: float,
    likely_threshold: float = 0.80,
    review_threshold: float = 0.50,
) -> ConfidenceLabel:
    """Band a confidence score. Thresholds are per-tier adjustable (SRS 4.4)."""
    if confidence >= likely_threshold:
        return ConfidenceLabel.LIKELY
    if confidence >= review_threshold:
        return ConfidenceLabel.NEEDS_REVIEW
    return ConfidenceLabel.HIDDEN


@dataclass
class Locator:
    """Where a finding sits. Exactly one addressing style is populated."""

    kind: str = "database"  # "database" | "repo" | "file"
    # database style
    schema: str | None = None
    table: str | None = None
    column: str | None = None
    # repo / file style
    path: str | None = None
    line: int | None = None

    def unit_key(self) -> str:
        """Key identifying the enclosing unit (table or file) for co-occurrence."""
        if self.table is not None:
            return f"table:{self.schema or ''}.{self.table}"
        if self.path is not None:
            return f"file:{self.path}"
        return "unit:unknown"

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "schema": self.schema,
            "table": self.table,
            "column": self.column,
            "path": self.path,
            "line": self.line,
        }


@dataclass
class Finding:
    """One detected instance of a category at a location (SRS FR-4.2)."""

    category: Category
    tier: Tier
    detector_id: str
    detector_kind: DetectorKind
    confidence: float
    hit_rate: float
    locator: Locator
    evidence: list[str] = field(default_factory=list)  # masked, max 3
    protection_state: ProtectionState = ProtectionState.UNKNOWN
    combined_identity: bool = False
    base_score: float = 0.0
    context_positive: bool = False
    context_negative: bool = False
    pack_version: str = ""
    review_state: ReviewState = ReviewState.NEW

    @property
    def label(self) -> ConfidenceLabel:
        return confidence_label(self.confidence)

    def as_dict(self) -> dict:
        return {
            "category": self.category.value,
            "category_label": CATEGORY_LABEL.get(self.category, self.category.value),
            "tier": self.tier.value,
            "detector_id": self.detector_id,
            "detector_kind": self.detector_kind.value,
            "confidence": round(self.confidence, 3),
            "confidence_label": self.label.value,
            "hit_rate": round(self.hit_rate, 3),
            "locator": self.locator.as_dict(),
            "evidence": list(self.evidence),
            "protection_state": self.protection_state.value,
            "combined_identity": self.combined_identity,
            "context_positive": self.context_positive,
            "context_negative": self.context_negative,
            "pack_version": self.pack_version,
            "review_state": self.review_state.value,
        }
