"""CLI：MySQL 源库二次脱敏。

用法:
  python -m scripts.redact_mysql_pii          # dry-run
  python -m scripts.redact_mysql_pii --apply  # 不可逆写库
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.mysql_redaction import apply_redaction, probe_redaction_state


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="执行不可逆 UPDATE")
    args = ap.parse_args()
    probe = probe_redaction_state()
    print("probe:", probe)
    if not args.apply:
        print("dry-run only; pass --apply to write")
        return 0
    n = apply_redaction()
    print(f"updated rows≈{n}")
    print("after:", probe_redaction_state())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
