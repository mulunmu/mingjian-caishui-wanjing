# -*- coding: utf-8 -*-
"""快速出一份放贷全库 PDF，并打印结构检查。"""
from __future__ import annotations

import asyncio
from pathlib import Path

from pypdf import PdfReader

from app.db.session import get_async_session_factory
from app.services.slice_report import generate_slice_report


async def main() -> None:
    Session = get_async_session_factory()
    async with Session() as db:
        rid, path, ctx = await generate_slice_report(db, scenario="loan", owner="admin@example.com")
    print("PDF", path)
    print("titles:")
    for i, c in enumerate(ctx.get("chapters") or [], 1):
        print(f"  {i}. {c.get('action_title')}")
    r = PdfReader(str(path))
    text = "\n".join((p.extract_text() or "") for p in r.pages[:3])
    for k in ("判断", "依据", "优先处置", "论断", "所以呢", "可照做", "支撑要点", "…"):
        print(f"marker {k!r}: {k in text}")
    print("--- page2 ---")
    print((r.pages[1].extract_text() or "")[:1200])
    # 拷贝到固定名便于宿主机 docker cp
    out = Path("/app/reports/_smoke_loan_memo.pdf")
    out.write_bytes(Path(path).read_bytes())
    print("copied", out)


if __name__ == "__main__":
    asyncio.run(main())
