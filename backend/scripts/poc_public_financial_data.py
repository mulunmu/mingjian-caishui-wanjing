"""Public-company financial report and risk-signal acquisition PoC.

This script validates one end-to-end path without paid APIs:
CNINFO metadata -> public PDF download -> text/table parsing -> field extraction
-> risk-event extraction -> evidence JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber


CNINFO_BASE = "https://www.cninfo.com.cn"
CNINFO_STATIC = "https://static.cninfo.com.cn"
STOCK_LIST_URL = f"{CNINFO_BASE}/new/data/szse_stock.json"
ANNOUNCEMENT_URL = f"{CNINFO_BASE}/new/hisAnnouncement/query"


def _request(url: str, *, data: bytes | None = None) -> bytes:
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0 risk-assessment-poc/1.0",
            "Referer": f"{CNINFO_BASE}/",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _find_org(code: str) -> tuple[str, str]:
    payload = json.loads(_request(STOCK_LIST_URL).decode("utf-8", "ignore"))
    rows = payload.get("stockList") or payload.get("data") or []
    for row in rows:
        if str(row.get("code")) == code:
            return str(row.get("orgId") or ""), str(row.get("zwjc") or code)
    raise RuntimeError(f"CNINFO stock not found: {code}")


def _find_report(code: str, org_id: str, year: int) -> dict[str, Any]:
    body = urllib.parse.urlencode(
        {
            "pageNum": 1,
            "pageSize": 30,
            "column": "sse" if code.startswith("6") else "szse",
            "tabName": "fulltext",
            "plate": "sh" if code.startswith("6") else "sz",
            "stock": f"{code},{org_id}",
            "searchkey": "",
            "secid": "",
            "category": "category_ndbg_szsh",
            "trade": "",
            "seDate": "",
        }
    ).encode()
    payload = json.loads(_request(ANNOUNCEMENT_URL, data=body).decode("utf-8", "ignore"))
    reports = payload.get("announcements") or []
    candidates = [
        item
        for item in reports
        if f"{year}年年度报告" in str(item.get("announcementTitle") or "")
        and "英文" not in str(item.get("announcementTitle") or "")
        and "摘要" not in str(item.get("announcementTitle") or "")
    ]
    if not candidates:
        raise RuntimeError(f"annual report not found for {code} {year}")
    return candidates[0]


def _download_pdf(report: dict[str, Any], cache_dir: Path) -> Path:
    url = f"{CNINFO_STATIC}/{str(report['adjunctUrl']).lstrip('/')}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    suffix = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    path = cache_dir / f"{report.get('secCode')}_{report.get('announcementId')}_{suffix}.pdf"
    if not path.exists():
        path.write_bytes(_request(url))
    return path


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _field_from_pages(
    page_texts: list[tuple[int, str]],
    *,
    patterns: list[str],
    min_value: float = 0.0,
) -> dict[str, Any] | None:
    candidates: list[tuple[float, int, str]] = []
    for page_no, text in page_texts:
        compact = _compact(text)
        for pattern in patterns:
            for match in re.finditer(pattern, compact, re.S):
                raw = match.group(1)
                value = float(raw.replace(",", ""))
                if value < min_value:
                    continue
                snippet = compact[max(0, match.start() - 80) : match.end() + 120]
                candidates.append((value, page_no, re.sub(r"\s+", " ", snippet)))
    if not candidates:
        return None
    value, page_no, snippet = candidates[0]
    return {"value": value, "unit": "元", "page": page_no, "snippet": snippet}
    return None


def _extract_financial_fields(page_texts: list[tuple[int, str]]) -> dict[str, Any]:
    specs = {
        "operating_revenue": {
            "patterns": [
                r"营业收入\s*([0-9][0-9,]*\.\d{2})",
                r"营业总收入[:：]?\s*([0-9][0-9,]*\.\d{2})",
            ],
            "min_value": 1_000_000.0,
        },
        "net_profit_attributable": {
            "patterns": [
                r"归属于上市公司股东的净\s*([0-9][0-9,]*\.\d{2})",
                r"归属于上市公司股东的净利润[:：]?\s*([0-9][0-9,]*\.\d{2})",
            ],
            "min_value": 1_000_000.0,
        },
        "operating_cash_flow": {
            "patterns": [r"经营活动产生的现金流量净额\s*([0-9][0-9,]*\.\d{2})"],
            "min_value": 1_000_000.0,
        },
        "total_assets": {
            "patterns": [r"资产总计\s*([0-9][0-9,]*\.\d{2})"],
            "min_value": 1_000_000.0,
        },
        "total_liabilities": {
            "patterns": [r"(?<!流动)负债合计\s*([0-9][0-9,]*\.\d{2})"],
            "min_value": 1_000_000.0,
        },
    }
    output: dict[str, Any] = {}
    for field, spec in specs.items():
        output[field] = _field_from_pages(
            page_texts,
            patterns=spec["patterns"],
            min_value=float(spec["min_value"]),
        )
    return output


EVENT_TERMS = {
    "going_concern": ["持续经营"],
    "impairment": ["减值"],
    "related_party": ["关联交易", "关联方"],
    "guarantee": ["对外担保", "担保"],
    "litigation": ["诉讼", "仲裁"],
    "regulatory_penalty": ["处罚", "罚款", "监管"],
    "debt_default": ["债务违约", "逾期债务", "违约"],
    "auditor_change": ["更换会计师事务所", "审计机构变更"],
    "management_change": ["管理层变动", "董事辞职", "高管辞职"],
    "restatement": ["会计差错", "前期差错更正"],
    "earnings_warning": ["业绩预告", "业绩快报"],
    "risk_disclosure": ["风险提示", "重大风险"],
}

POSITIVE_TERMS = ["增长", "提升", "改善", "稳健", "增加", "完成", "盈利"]
NEGATIVE_TERMS = ["下降", "减少", "亏损", "减值", "处罚", "诉讼", "违约", "风险", "终止"]


def _snippet(text: str, term: str) -> str:
    index = text.find(term)
    if index < 0:
        return ""
    return re.sub(r"\s+", " ", text[max(0, index - 60) : index + 120]).strip()


def _extract_events(page_texts: list[tuple[int, str]]) -> dict[str, Any]:
    events: dict[str, Any] = {}
    for event, terms in EVENT_TERMS.items():
        hits = []
        seen: set[tuple[int, str]] = set()
        for page_no, text in page_texts:
            for term in terms:
                if term not in text:
                    continue
                key = (page_no, term)
                if key in seen:
                    continue
                seen.add(key)
                hits.append({"page": page_no, "term": term, "snippet": _snippet(text, term)})
                if len(hits) >= 5:
                    break
            if len(hits) >= 5:
                break
        events[event] = hits
    return events


def _sentiment(page_texts: list[tuple[int, str]]) -> dict[str, int | float]:
    corpus = "\n".join(text for _, text in page_texts)
    positive = sum(corpus.count(term) for term in POSITIVE_TERMS)
    negative = sum(corpus.count(term) for term in NEGATIVE_TERMS)
    total = positive + negative
    return {
        "positive_hits": positive,
        "negative_hits": negative,
        "simple_score": round((positive - negative) / total, 4) if total else 0.0,
    }


def run(code: str, year: int, output: Path) -> dict[str, Any]:
    started = time.perf_counter()
    org_id, company_name = _find_org(code)
    report = _find_report(code, org_id, year)
    cache_dir = Path(os.getenv("TEMP", "/tmp")) / "risk_assessment_public_poc"
    pdf_path = _download_pdf(report, cache_dir)
    page_texts: list[tuple[int, str]] = []
    table_count = 0
    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        for page_no, page in enumerate(pdf.pages, 1):
            page_texts.append((page_no, page.extract_text() or ""))
            table_count += len(page.extract_tables() or [])
    fields = _extract_financial_fields(page_texts)
    audit_checks = {
        "has_assets_and_liabilities": bool(fields.get("total_assets") and fields.get("total_liabilities")),
        "assets_ge_liabilities": bool(
            fields.get("total_assets")
            and fields.get("total_liabilities")
            and fields["total_assets"]["value"] >= fields["total_liabilities"]["value"]
        ),
    }
    result = {
        "company": {"code": code, "name": company_name, "org_id": org_id},
        "report": {
            "title": report.get("announcementTitle"),
            "announcement_id": report.get("announcementId"),
            "url": f"{CNINFO_STATIC}/{str(report.get('adjunctUrl')).lstrip('/')}",
            "pdf_bytes": pdf_path.stat().st_size,
            "page_count": page_count,
            "table_count": table_count,
        },
        "financial_fields": fields,
        "audit_checks": audit_checks,
        "event_candidates": _extract_events(page_texts),
        "sentiment": _sentiment(page_texts),
        "sentiment_note": "Lexicon baseline only; event extraction must take precedence over generic sentiment.",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", default="600519")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument(
        "--output",
        default="报告/上市公司公开数据PoC结果.json",
    )
    args = parser.parse_args()
    result = run(args.code, args.year, Path(args.output))
    print(json.dumps(result, ensure_ascii=False, indent=2)[:12000])


if __name__ == "__main__":
    main()
