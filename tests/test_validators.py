"""Validator tests: checksums and structural rules (SRS 4.1)."""
from __future__ import annotations

import pytest

from dpia_core.detectors import validators as V


def test_verhoeff_roundtrip_and_tamper():
    base = "23412341234"
    check = V.verhoeff_checksum(base)
    number = base + str(check)
    assert V.verhoeff_validate(number)
    # Tampering with any digit breaks the checksum.
    tampered = ("3" if number[0] != "3" else "4") + number[1:]
    assert not V.verhoeff_validate(tampered)


def test_aadhaar_valid_and_leading_digit_rule():
    good = "23412341234" + str(V.verhoeff_checksum("23412341234"))
    assert V.aadhaar_valid(good)
    assert V.aadhaar_valid(good[:4] + " " + good[4:8] + " " + good[8:])  # spaced form
    assert not V.aadhaar_valid("1234")           # too short
    assert not V.aadhaar_valid("0" + good[1:])   # cannot start with 0


def test_luhn_and_payment_card():
    assert V.luhn_validate("4111111111111111")
    assert V.payment_card_valid("4111111111111111")
    assert not V.payment_card_valid("4111111111111112")  # bad checksum
    assert not V.payment_card_valid("1234567812345678")  # first digit not 3-6
    base = "601100099999999"
    assert V.payment_card_valid(base + str(V.luhn_checksum(base)))


def test_pan():
    assert V.pan_valid("ABCPK1234L")
    assert not V.pan_valid("ABCXK1234L")  # 4th char not a holder type
    assert not V.pan_valid("12CPK1234L")


def test_gstin():
    check = V.gstin_check_char("27ABCPK1234L1Z")
    assert V.gstin_valid("27ABCPK1234L1Z" + check)
    assert not V.gstin_valid("99ABCPK1234L1Z" + check)   # bad state code
    assert not V.gstin_valid("27ABCXK1234L1Z" + check)   # bad embedded PAN


def test_ifsc_and_pin():
    assert V.ifsc_valid("HDFC0001234")
    assert not V.ifsc_valid("HDFCX001234")  # 5th char must be 0
    assert V.pin_code_valid("700016")
    assert not V.pin_code_valid("012345")   # cannot start with 0


def test_driving_licence_and_vehicle():
    assert V.driving_licence_valid("KA0120121234567")
    assert not V.driving_licence_valid("ZZ0120121234567")  # bad state
    assert not V.driving_licence_valid("KA0118001234567")  # year before 1950
    assert V.vehicle_reg_valid("WB20AB1234")
    assert not V.vehicle_reg_valid("ZZ20AB1234")


def test_upi_vs_email():
    assert V.upi_valid("rahul@okaxis")
    assert not V.upi_valid("rahul@example.com")   # dotted domain is an email
    assert V.email_valid("rahul@example.com")
    assert not V.email_valid("noreply@example.com")  # role address excluded


def test_epf_uan_distinguished_from_aadhaar():
    aadhaar = "23412341234" + str(V.verhoeff_checksum("23412341234"))
    assert not V.epf_uan_valid(aadhaar)  # passes Verhoeff -> it's an Aadhaar
    uan = "10023456789" + str((V.verhoeff_checksum("10023456789") + 1) % 10)
    assert V.epf_uan_valid(uan)


def test_dob_plausibility_and_age():
    assert V.dob_valid("1990-05-14")
    assert V.dob_valid("14/05/1990")
    assert not V.dob_valid("1800-01-01")  # implausible age
    assert V.age_from_dob("2015-06-01") < 18
