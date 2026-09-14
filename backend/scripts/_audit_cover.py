# -*- coding: utf-8 -*-
from app.services.report_html import build_report_html
from tests.test_report_structure import _full_context

ctx = _full_context()
ctx["cover_meta"] = {
    "scenario_label": "评级",
    "subject": "制造",
    "one_liner": "一句话结论",
    "risk_level": "中等",
    "business_level": "中等",
    "sample_count": "59",
    "frame": "rating",
}
html = build_report_html(ctx, "audit_cover")
cover = html.split("<h2>执行摘要</h2>")[0]
checks = {
    "cover_no_badge_dom": 'class="scenario-badge"' not in cover,
    "cover_no_oneliner_dom": 'class="one-liner"' not in cover,
    "cover_no_grade_text": "群体风险判断" not in cover,
    "cover_has_date": "报告日期" in cover,
    "body_has_so_what": "所以呢" in html,
    "body_has_details": "<details" in html,
    "no_appendix_word": "附录" not in html,
}
for k, v in checks.items():
    print(("PASS" if v else "FAIL"), k)
assert all(checks.values()), checks
print("COVER_CHAPTER_AUDIT_OK")
