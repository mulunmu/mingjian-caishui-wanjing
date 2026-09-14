from pathlib import Path
from pypdf import PdfReader

root = Path("/tmp/rpt_audit")
for p in sorted(root.glob("*.pdf")):
    r = PdfReader(str(p))
    texts = []
    for i, page in enumerate(r.pages):
        t = page.extract_text() or ""
        texts.append(f"--- page {i+1} ---\n{t}")
    out = "\n".join(texts)
    out_path = root / f"{p.stem}.txt"
    out_path.write_text(out, encoding="utf-8")
    print("=" * 80)
    print("FILE", p.name, "pages", len(r.pages), "chars", len(out))
    print(out[:8000])
    if len(out) > 8000:
        print("\n...[tail]...\n")
        print(out[-3000:])
