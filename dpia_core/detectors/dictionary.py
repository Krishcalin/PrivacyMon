"""Dictionary and metadata detectors (SRS section 4.2).

These cover categories that have no checksum: gender, health, caste/religion,
children's data, address and person name, plus column-metadata detection for
biometric and photo/scanned-ID columns. A spaCy NER model boosts person-name
and address recall in the Deep profile (SRS 4.2); it is optional and wired in
``dpia_core.ner`` so the core has no heavy dependency.
"""
from __future__ import annotations

import re

from ..models import Category, DetectorKind, Tier
from .base import DetectorSpec


def _word_set(value: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9+]+", value.lower()) if t}


# --------------------------------------------------------------------------
# Gender
# --------------------------------------------------------------------------
_GENDER_TERMS = {"m", "f", "male", "female", "other", "transgender", "trans",
                 "nonbinary", "non-binary"}


def _gender_match(value: str) -> bool:
    v = value.strip().lower()
    return v in _GENDER_TERMS


# --------------------------------------------------------------------------
# Health (diagnoses, medicines, blood groups, disability)
# --------------------------------------------------------------------------
_HEALTH_TERMS = {
    "diabetes", "diabetic", "hypertension", "asthma", "cancer", "tuberculosis",
    "tb", "hiv", "aids", "covid", "hepatitis", "epilepsy", "depression",
    "anxiety", "pregnancy", "pregnant", "thyroid", "cardiac", "stroke",
    "insulin", "metformin", "paracetamol", "amoxicillin", "chemotherapy",
    "dialysis", "disability", "disabled", "blind", "deaf", "wheelchair",
    "schizophrenia", "bipolar", "anaemia", "jaundice",
}
_BLOOD_GROUP_RE = re.compile(r"\b(?:A|B|AB|O)\s?(?:\+|-|positive|negative|pos|neg)\b", re.I)


def _health_match(value: str) -> bool:
    if _BLOOD_GROUP_RE.search(value):
        return True
    return bool(_word_set(value) & _HEALTH_TERMS)


# --------------------------------------------------------------------------
# Caste / religion / political affiliation
# --------------------------------------------------------------------------
_RELIGION_TERMS = {
    "hindu", "hinduism", "muslim", "islam", "christian", "christianity",
    "sikh", "sikhism", "buddhist", "buddhism", "jain", "jainism", "parsi",
    "zoroastrian", "jewish",
}
_CASTE_TERMS = {"general", "obc", "sc", "st", "ews", "bc", "mbc", "sbc"}
_POLITICAL_TERMS = {"bjp", "inc", "congress", "aap", "cpi", "cpim", "tmc",
                    "dmk", "aidmk", "shivsena", "ncp"}
_CRP_TERMS = _RELIGION_TERMS | _CASTE_TERMS | _POLITICAL_TERMS


def _crp_match(value: str) -> bool:
    return bool(_word_set(value) & _CRP_TERMS)


# --------------------------------------------------------------------------
# Address (Indian address tokens, must look like an address)
# --------------------------------------------------------------------------
_ADDRESS_TOKENS = {
    "road", "rd", "lane", "nagar", "para", "sarani", "marg", "gali", "colony",
    "block", "sector", "po", "ps", "dist", "street", "apartment", "flat",
    "society", "vihar", "puram", "chowk", "bazar", "bazaar", "layout",
}
_PIN_RE = re.compile(r"\b[1-9]\d{5}\b")


def _address_match(value: str) -> bool:
    toks = _word_set(value)
    if not (toks & _ADDRESS_TOKENS):
        return False
    # Require corroboration: a PIN code, a comma, or a street number.
    return bool(_PIN_RE.search(value) or "," in value or re.search(r"\d", value))


# --------------------------------------------------------------------------
# Person name (dictionary of common Indian given names and surnames)
# --------------------------------------------------------------------------
_NAME_TERMS = {
    # given names
    "ananya", "arjun", "aditya", "rahul", "rohan", "priya", "pooja", "sneha",
    "vikram", "anjali", "kavya", "ishaan", "aarav", "diya", "meera", "ravi",
    "sanjay", "deepak", "neha", "riya", "karan", "simran", "arun", "lakshmi",
    "ganesh", "suresh", "ramesh", "gita", "sita", "mohan",
    # Bengali / regional given names and surnames
    "soumya", "debashish", "sourav", "rimi", "tanmoy", "sayan", "moumita",
    # surnames
    "sharma", "verma", "gupta", "singh", "kumar", "patel", "reddy", "nair",
    "iyer", "menon", "das", "roy", "banerjee", "chatterjee", "mukherjee",
    "ghosh", "bose", "sen", "dutta", "khan", "shaikh", "ansari", "pillai",
    "rao", "naidu", "chowdhury", "mondal", "sarkar",
}


def _name_match(value: str) -> bool:
    toks = _word_set(value)
    return bool(toks & _NAME_TERMS) and len(toks) <= 5


def build_dictionary_detectors() -> list[DetectorSpec]:
    return [
        DetectorSpec(
            id="gender.v1",
            category=Category.GENDER,
            tier=Tier.LOW,
            kind=DetectorKind.DICTIONARY,
            value_matcher=_gender_match,
            context_positive=["gender", "sex"],
            requires_context=True,
            description="Gender term in a gender/sex column.",
        ),
        DetectorSpec(
            id="health.v1",
            category=Category.HEALTH,
            tier=Tier.CRITICAL,
            kind=DetectorKind.DICTIONARY,
            value_matcher=_health_match,
            context_positive=["health", "diagnosis", "medical", "disease",
                              "blood_group", "bloodgroup", "ailment", "condition"],
            description="Diagnosis, medicine, blood group or disability term.",
        ),
        DetectorSpec(
            id="caste_religion_political.v1",
            category=Category.CASTE_RELIGION_POLITICAL,
            tier=Tier.CRITICAL,
            kind=DetectorKind.DICTIONARY,
            value_matcher=_crp_match,
            context_positive=["caste", "religion", "community", "category",
                              "political", "affiliation"],
            requires_context=True,
            description="Caste, religion or political affiliation in a matching column.",
        ),
        DetectorSpec(
            id="address.v1",
            category=Category.ADDRESS,
            tier=Tier.MEDIUM,
            kind=DetectorKind.DICTIONARY,
            value_matcher=_address_match,
            context_positive=["address", "addr", "street", "residence", "location"],
            description="Indian postal address tokens with corroboration.",
        ),
        DetectorSpec(
            id="person_name.v1",
            category=Category.PERSON_NAME,
            tier=Tier.LOW,
            kind=DetectorKind.NER,
            value_matcher=_name_match,
            context_positive=["name", "first_name", "surname", "last_name",
                              "applicant_name", "father_name", "spouse_name",
                              "customer_name", "full_name"],
            description="Person name by dictionary; spaCy NER boosts in Deep profile.",
        ),
        DetectorSpec(
            id="children_data.v1",
            category=Category.CHILDREN_DATA,
            tier=Tier.CRITICAL,
            kind=DetectorKind.DICTIONARY,
            value_matcher=lambda v: bool(v and str(v).strip()),  # fires on column presence
            context_positive=["minor", "guardian", "student_class", "child",
                              "under18", "ward", "parent_consent"],
            requires_context=True,
            description="Children's-data columns (guardian, student class, minor).",
        ),
    ]


# --------------------------------------------------------------------------
# Column-metadata detection (biometric, photo / scanned ID) — SRS 4.2.
# These look at column name and SQL data type, not sampled values.
# --------------------------------------------------------------------------
_BINARY_TYPES = {"bytea", "blob", "longblob", "mediumblob", "varbinary",
                 "binary", "image", "raw", "bfile"}
_BIOMETRIC_NAME_TOKENS = {"fingerprint", "finger_print", "iris", "face",
                          "faceprint", "template", "biometric", "retina"}
_PHOTO_NAME_TOKENS = {"photo", "photograph", "image", "picture", "scan",
                      "selfie", "id_scan", "document_image"}


def scan_column_metadata(column_name: str | None, data_type: str | None):
    """Return (Category, Tier) metadata hits for a column, or an empty list."""
    hits: list[tuple[Category, Tier]] = []
    name = (column_name or "").lower()
    name_toks = {t for t in re.split(r"[^a-z0-9]+", name) if t}
    dtype = (data_type or "").lower()
    is_binary = any(t in dtype for t in _BINARY_TYPES)
    if (name_toks & _BIOMETRIC_NAME_TOKENS) and (is_binary or not dtype):
        hits.append((Category.BIOMETRIC, Tier.CRITICAL))
    if (name_toks & _PHOTO_NAME_TOKENS) and (is_binary or not dtype):
        hits.append((Category.PHOTO_ID, Tier.HIGH))
    return hits
