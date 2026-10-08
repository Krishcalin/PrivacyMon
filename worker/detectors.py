"""Load custom detectors from the database and merge them with the built-in pack
(SRS FR-4.7). Custom detectors are rows in ``detector_packs`` (active) + ``detectors``,
created through the admin UI; each row is compiled into a ``DetectorSpec`` via the vetted
``dpia_core.detectors.compile`` registry (no executable code is ever stored or run).

Kept separate from ``factory`` so the merge happens once per scan, not once per connector.
"""
from __future__ import annotations

from dpia_core.detectors.compile import DetectorCompileError, spec_from_row
from dpia_core.detectors.registry import DEFAULT_PACK_VERSION, default_detectors


def load_custom_detectors(session) -> list:
    """Compile every detector in an ACTIVE custom pack into a ``DetectorSpec``. A row
    that will not compile is skipped (never fails a scan). Returns [] on any error."""
    try:
        from platform_db.enums import DetectorPackSource
        from platform_db.models.scanning import Detector, DetectorPack
    except Exception:  # noqa: BLE001
        return []
    out: list = []
    try:
        active_pack_ids = [
            p.id for p in session.query(DetectorPack).filter(
                DetectorPack.active.is_(True),
                DetectorPack.source == DetectorPackSource.CUSTOM).all()]
        if not active_pack_ids:
            return []
        rows = session.query(Detector).filter(Detector.pack_id.in_(active_pack_ids)).all()
        for r in rows:
            try:
                out.append(spec_from_row(r))
            except DetectorCompileError:
                continue
    except Exception:  # noqa: BLE001 — a DB hiccup must not stop the scan
        return []
    return out


def effective_detectors(session) -> tuple[list, str]:
    """The detector chain a scan should run: built-in pack + active custom detectors.
    Returns (detectors, pack_version). The version is tagged ``+custom`` when any custom
    detector is included, so findings record which chain produced them."""
    custom = load_custom_detectors(session)
    detectors = default_detectors() + custom
    version = DEFAULT_PACK_VERSION + ("+custom" if custom else "")
    return detectors, version
