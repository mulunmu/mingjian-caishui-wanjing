"""Rebuild semantic embeddings for all validated RAG tools."""
from __future__ import annotations

import argparse
import json

from app.db.urls import get_sync_engine
from app.services.tool_embedding_index import build_tool_embedding_index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    report = build_tool_embedding_index(get_sync_engine(), force=args.force)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
