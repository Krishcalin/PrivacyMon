"""Synthetic Indian PII fixtures for the detector precision suite (SRS 13.1).

All values are fabricated and checksum-consistent (built with the same
generators the validators use), so no real person's data appears here. Positive
columns must be detected; negative columns look like PII but must stay clean.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from dpia_core.detectors import validators as V
from dpia_core.models import Category


# --------------------------------------------------------------------------
# Generators that build valid sample values
# --------------------------------------------------------------------------
def _aadhaar(base11: str) -> str:
    return base11 + str(V.verhoeff_checksum(base11))


def _aadhaar_vid(base15: str) -> str:
    return base15 + str(V.verhoeff_checksum(base15))


def _gstin(state: str, pan: str, entity: str = "1") -> str:
    first14 = f"{state}{pan}{entity}Z"
    return first14 + V.gstin_check_char(first14)


def _card(base_without_check: str) -> str:
    return base_without_check + str(V.luhn_checksum(base_without_check))


def _bad_verhoeff_12(base11: str) -> str:
    """A 12-digit number that fails Verhoeff (for UAN positives / Aadhaar negatives)."""
    good = V.verhoeff_checksum(base11)
    return base11 + str((good + 1) % 10)


# Valid positives
VALID_AADHAAR = [_aadhaar("23412341234"), _aadhaar("34523452345"), _aadhaar("45654654567")]
VALID_VID = [_aadhaar_vid("912345678901234"), _aadhaar_vid("987654321098765")]
VALID_PAN = ["ABCPK1234L", "AAAPZ1234C", "BNZPM5678H"]
VALID_GSTIN = [_gstin("27", "ABCPK1234L"), _gstin("19", "AAAPZ1234C")]
VALID_CARD = ["4111111111111111", _card("601100099999999"), _card("550000555555555")]
VALID_IFSC = ["HDFC0001234", "SBIN0005678", "ICIC0009999"]
VALID_UPI = ["rahul.sharma@okaxis", "ananya.roy@ybl", "customer01@paytm"]
VALID_MOBILE_STRONG = ["+91 98765 43210", "09876543210", "+919812345678"]
VALID_MOBILE_PLAIN = ["9876543210", "8123456789", "7012345678"]
VALID_EMAIL = ["ananya.roy@example.com", "rahul.sharma@acme.co.in", "k.menon@mail.org"]
VALID_PIN = ["700016", "110001", "560037"]
VALID_VEHICLE = ["WB20AB1234", "KA01MA9999", "MH12CD4567"]
VALID_DL = ["KA0120121234567", "MH0119981234567", "WB2020151234567"]
VALID_VOTER = ["ABC1234567", "WBX7654321", "KLM1112223"]
VALID_PASSPORT = ["M1234561", "N9876543", "A1000001"]
VALID_UAN = [_bad_verhoeff_12("10023456789"), _bad_verhoeff_12("11098765432")]
VALID_DOB_ADULT = ["1990-05-14", "14/05/1990", "02-11-1985"]
VALID_DOB_CHILD = ["2015-06-01", "01/09/2012", "2018-03-20"]
VALID_HEALTH = ["Diabetes", "O+", "hypertension", "insulin"]
VALID_GENDER = ["Female", "Male", "Other"]
VALID_RELIGION = ["Hindu", "Muslim", "Christian"]
VALID_ADDRESS = ["12, Park Street, Kolkata 700016", "4 MG Road, Bengaluru 560001"]
VALID_NAME = ["Ananya Roy", "Rahul Sharma", "Lakshmi Menon"]
VALID_GUARDIAN = ["Sanjay Sharma", "Meera Nair"]

# Values that look like PII but must NOT fire (negatives)
BAD_AADHAAR = [_bad_verhoeff_12("23412341234"), _bad_verhoeff_12("34534534534")]
ORDER_IDS_10 = ["1234567890", "1098765432", "1000000001"]
ORDER_IDS_12 = ["100000012345", "100987654321", "123400005678"]
INVOICE_NOS = ["INV0001234", "INV2024A991", "BILL778812"]
TXN_REFS_16 = ["1234567812345678", "1111222233334441", "9999000011112221"]
BAD_PAN = ["ABCXK1234L", "ABCDE1234Z", "12CPK1234L"]  # invalid 4th char / malformed
BAD_IFSC = ["ABCD1234567", "HDFCX001234", "SB1N0005678"]
BAD_GSTIN = ["27ABCXK1234L1Z5", "99ABCPK1234L1Z5"]  # bad embedded PAN / bad state
AMOUNTS = ["700016", "110001", "250000"]
STATUSES = ["general", "active", "pending"]
CREATED_DATES = ["2024-01-15", "2023-11-30", "2025-02-28"]


@dataclass
class SampleColumn:
    column_name: str
    values: list[str]
    expected: Category | None = None  # None => must produce no visible finding
    data_type: str | None = None


POSITIVES: list[SampleColumn] = [
    SampleColumn("aadhaar_number", VALID_AADHAAR, Category.AADHAAR),
    SampleColumn("vid", VALID_VID, Category.AADHAAR_VID),
    SampleColumn("pan_no", VALID_PAN, Category.PAN),
    SampleColumn("gstin", VALID_GSTIN, Category.GSTIN),
    SampleColumn("card_no", VALID_CARD, Category.PAYMENT_CARD),
    SampleColumn("ifsc_code", VALID_IFSC, Category.IFSC),
    SampleColumn("upi_id", VALID_UPI, Category.UPI_ID),
    SampleColumn("mobile", VALID_MOBILE_STRONG, Category.MOBILE),
    SampleColumn("contact_number", VALID_MOBILE_PLAIN, Category.MOBILE),
    SampleColumn("email", VALID_EMAIL, Category.EMAIL),
    SampleColumn("pincode", VALID_PIN, Category.PIN_CODE),
    SampleColumn("vehicle_no", VALID_VEHICLE, Category.VEHICLE_REG),
    SampleColumn("dl_no", VALID_DL, Category.DRIVING_LICENCE),
    SampleColumn("voter_id", VALID_VOTER, Category.VOTER_ID),
    SampleColumn("passport_no", VALID_PASSPORT, Category.PASSPORT),
    SampleColumn("uan", VALID_UAN, Category.EPF_UAN),
    SampleColumn("date_of_birth", VALID_DOB_ADULT, Category.DOB),
    SampleColumn("diagnosis", VALID_HEALTH, Category.HEALTH),
    SampleColumn("gender", VALID_GENDER, Category.GENDER),
    SampleColumn("religion", VALID_RELIGION, Category.CASTE_RELIGION_POLITICAL),
    SampleColumn("address", VALID_ADDRESS, Category.ADDRESS),
    SampleColumn("customer_name", VALID_NAME, Category.PERSON_NAME),
    SampleColumn("guardian", VALID_GUARDIAN, Category.CHILDREN_DATA),
]

NEGATIVES: list[SampleColumn] = [
    SampleColumn("ref", BAD_AADHAAR),
    SampleColumn("order_id", ORDER_IDS_10),
    SampleColumn("order_id", ORDER_IDS_12),
    SampleColumn("invoice_no", INVOICE_NOS),
    SampleColumn("txn_ref", TXN_REFS_16),
    SampleColumn("ref", BAD_PAN),
    SampleColumn("ref", BAD_IFSC),
    SampleColumn("ref", BAD_GSTIN),
    SampleColumn("amount", AMOUNTS),
    SampleColumn("status", STATUSES),
    SampleColumn("created_at", CREATED_DATES),
]
