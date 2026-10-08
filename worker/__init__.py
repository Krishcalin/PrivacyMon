"""PrivacyMon worker: connectors and the scan pipeline (SRS 3.2, 3.3, 7.2).

The connectors turn a data source into ``dpia_core`` findings; the pipeline (a later
slice) persists them through ``platform_db`` and drives live progress. Everything here
depends on ``dpia_core`` for detection and nothing in ``dpia_core`` depends back.
"""
