"""Importing this package populates ``Base.metadata`` with every table.

Order matters only for readability; SQLAlchemy resolves string-based relationships
and foreign keys lazily, so the four groups can be imported in any order.
"""
from __future__ import annotations

from platform_db.models import registry  # noqa: F401
from platform_db.models import scanning  # noqa: F401
from platform_db.models import assessment  # noqa: F401
from platform_db.models import platform_tables  # noqa: F401

__all__ = ["registry", "scanning", "assessment", "platform_tables"]
