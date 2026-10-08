"""Connectors (SRS 3.2). A connector turns one data source into findings.

The SDK contract (FR-2.9): a connector implements ``test()``, ``enumerate()`` and
``scan_unit()`` — no change to ``dpia_core`` or the pipeline is needed to add one.
"""
from __future__ import annotations

from worker.connectors.base import Connector, ConnectorTest, ScanUnit

__all__ = ["Connector", "ConnectorTest", "ScanUnit"]
