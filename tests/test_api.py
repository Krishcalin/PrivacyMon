"""API smoke tests (SRS section 9) using FastAPI's TestClient."""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.app.main import app

client = TestClient(app)
P = "/api/v1"


def test_healthz():
    r = client.get(f"{P}/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_version_reports_pack():
    r = client.get(f"{P}/version")
    assert r.status_code == 200
    body = r.json()
    assert body["app"] == "PrivacyMon"
    assert body["detector_pack"]


def test_controls_endpoint():
    r = client.get(f"{P}/controls", params={"framework": "dpdp"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 10
    assert any("S.8" in c["ref"] for c in body["controls"])


def test_detectors_listing():
    r = client.get(f"{P}/detectors")
    assert r.status_code == 200
    ids = {d["id"] for d in r.json()["detectors"]}
    assert "aadhaar.v1" in ids and "pan.v1" in ids


def test_detector_test_masks_evidence():
    # A valid Aadhaar (Verhoeff-consistent) in an Aadhaar column.
    from dpia_core.detectors import validators as V
    aadhaar = "23412341234" + str(V.verhoeff_checksum("23412341234"))
    r = client.post(f"{P}/detectors/test", json={
        "samples": [aadhaar], "column_name": "aadhaar_number",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["finding_count"] >= 1
    finding = body["findings"][0]
    assert finding["category"] == "aadhaar"
    # Evidence must be masked: the raw number must not appear.
    assert aadhaar not in str(body)
    assert finding["evidence"][0].startswith("XXXX")
