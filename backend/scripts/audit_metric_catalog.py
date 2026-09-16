"""CLI wrapper for the Metric Catalog v2 coverage audit."""
from __future__ import annotations

from app.services.metric_catalog_v2 import build_metric_catalog_audit, main


__all__ = ["build_metric_catalog_audit"]


if __name__ == "__main__":
    main()
