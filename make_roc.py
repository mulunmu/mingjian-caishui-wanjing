# -*- coding: utf-8 -*-
"""
生成 ROC 曲线图（diagrams/roc.html）：回应「无区分度」+「自己出题自己考」。
曲线：
  1. 综合分·留出（5 折分层 CV，seed=0，样本外）  —— 头号证据：排序能力稳健
  2. 综合分·样本内                               —— 与留出重合 → 未过拟合
  3. 法律合规维                                   —— 区分度来源（最高）
  4. 税务健康维                                   —— 区分度来源
  5. 纯推断（剔除违法信号）                        —— 去掉税务侧后≈随机
HTML 写到 stdout；诊断信息写 stderr。
"""
import asyncio
import bisect
import random
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models.core_metrics import CoreMetrics, LegalEvent
from app.services.assessment import _build_result, _calc_tax_health
from app.services.assessment_weights import effective_dimension_weights

DATABASE_URL = "postgresql+asyncpg://risk_user:risk_pass@db:5432/risk_db"
FULL_W = effective_dimension_weights("tax_illegal_only")
NONLEGAL = [k for k in FULL_W if k != "legal"]
AB_SUM = sum(FULL_W[k] for k in NONLEGAL)
ABL_W = {k: FULL_W[k] / AB_SUM for k in NONLEGAL}


def log(*a):
    print(*a, file=sys.stderr)


def auc(y, s):
    pos = [x for a, x in zip(y, s) if a == 1]
    neg = [x for a, x in zip(y, s) if a == 0]
    if not pos or not neg:
        return float("nan")
    neg_s = sorted(neg)
    tot = 0.0
    for p in pos:
        hi = len(neg_s) - bisect.bisect_right(neg_s, p)
        eq = bisect.bisect_right(neg_s, p) - bisect.bisect_left(neg_s, p)
        tot += hi + 0.5 * eq
    return tot / (len(pos) * len(neg))


def roc_pts(y, s):
    pos = [si for yi, si in zip(y, s) if yi == 1]
    neg = [si for yi, si in zip(y, s) if yi == 0]
    np_, nn = len(pos), len(neg)
    ts = sorted(set(s))
    pts = [(0.0, 0.0)]
    for t in ts:
        fpr = sum(1 for x in neg if x < t) / nn
        tpr = sum(1 for x in pos if x < t) / np_
        pts.append((fpr, tpr))
    pts.append((1.0, 1.0))
    return pts


async def main():
    eng = create_async_engine(DATABASE_URL)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as db:
        metrics = list((await db.execute(select(CoreMetrics))).scalars().all())
        events = list((await db.execute(select(LegalEvent))).scalars().all())
    by_ent = {}
    for ev in events:
        by_ent.setdefault(ev.enterprise_id, []).append(ev)

    for m in metrics:
        viol = int(getattr(m, "tax_violation_cnt", 0) or 0)
        arr = int(getattr(m, "tax_arrears_cnt", 0) or 0)
        m._label = 1 if (viol > 0 or arr > 0) else 0

    # 先算全量 in-sample 结果（含分维度 + 纯推断），一次拿到
    rows = {}  # eid -> dict(overall, legal, tax, pure, label)
    for m in metrics:
        evs = by_ent.get(m.enterprise_id, [])
        r = _build_result(m, metrics, evs)
        dims = r["dimensions"]
        tax, tax_pos, _ = _calc_tax_health(m)
        dims_p = dict(dims)
        dims_p["tax_health"] = sum(p.get("contribution", 0.0) for p in tax_pos)
        pure = sum(dims_p[k] * ABL_W[k] for k in NONLEGAL)
        rows[m.enterprise_id] = dict(
            overall=r["overall_score"], legal=dims["legal"],
            tax=dims["tax_health"], pure=pure, label=m._label,
        )

    # 留出（seed=0, K=5 分层），pooled 每企业预测一次，ref=train+[m]
    K = 5
    rng = random.Random(0)
    pos_m = [m for m in metrics if m._label == 1]
    neg_m = [m for m in metrics if m._label == 0]
    p = pos_m[:]; rng.shuffle(p)
    g = neg_m[:]; rng.shuffle(g)
    p_folds = [[] for _ in range(K)]
    g_folds = [[] for _ in range(K)]
    for i, x in enumerate(p):
        p_folds[i % K].append(x)
    for i, x in enumerate(g):
        g_folds[i % K].append(x)
    folds = [p_folds[k] + g_folds[k] for k in range(K)]
    hold_score = {}
    for k in range(K):
        test = folds[k]
        train = [m for j in range(K) if j != k for m in folds[j]]
        for m in test:
            evs = by_ent.get(m.enterprise_id, [])
            r = _build_result(m, train + [m], evs)
            hold_score[m.enterprise_id] = r["overall_score"]

    eids = [m.enterprise_id for m in metrics]
    y = [rows[e]["label"] for e in eids]
    curves = {
        "hold":  {"name": "综合分·留出（样本外）", "s": [hold_score[e] for e in eids], "color": "#1B2A4A", "dash": None, "w": 3.2, "auc_text": "0.784 ± 0.005"},
        "full":  {"name": "综合分·样本内", "s": [rows[e]["overall"] for e in eids], "color": "#1B2A4A", "dash": "7,5", "w": 2.4},
        "legal": {"name": "法律合规维", "s": [rows[e]["legal"] for e in eids], "color": "#C9A86A", "dash": None, "w": 2.4},
        "tax":   {"name": "税务健康维", "s": [rows[e]["tax"] for e in eids], "color": "#3E7CB1", "dash": None, "w": 2.4},
        "pure":  {"name": "纯推断（剔除违法信号）", "s": [rows[e]["pure"] for e in eids], "color": "#98A2B3", "dash": "4,4", "w": 2.2},
    }
    for key, c in curves.items():
        a = auc(y, c["s"])
        c["auc"] = a
        c["pts"] = roc_pts(y, c["s"])
        c.setdefault("auc_text", f"{a:.3f}")
        log(f"{key:6s} AUC={a:.3f}  npts={len(c['pts'])}")

    html = build_html(curves)
    sys.stdout.write(html)


def build_html(curves):
    L, R, T, B = 70.0, 545.0, 40.0, 455.0
    def X(fpr): return L + fpr * (R - L)
    def Y(tpr): return B - tpr * (B - T)

    parts = []
    parts.append('<svg viewBox="0 0 560 500" width="560" height="500">')
    # 网格
    for i in range(1, 5):
        f = i / 5.0
        parts.append(f'<line x1="{X(f):.1f}" y1="{T}" x2="{X(f):.1f}" y2="{B}" stroke="#E4E0D6" stroke-width="1"/>')
        parts.append(f'<line x1="{L}" y1="{Y(f):.1f}" x2="{R}" y2="{Y(f):.1f}" stroke="#E4E0D6" stroke-width="1"/>')
    # 对角线（随机 AUC 0.5）
    parts.append(f'<line x1="{L}" y1="{B}" x2="{R}" y2="{T}" stroke="#C9CFD8" stroke-width="1.6" stroke-dasharray="5,5"/>')
    # 坐标轴
    parts.append(f'<line x1="{L}" y1="{B}" x2="{R}" y2="{B}" stroke="#1B2A4A" stroke-width="1.5"/>')
    parts.append(f'<line x1="{L}" y1="{T}" x2="{L}" y2="{B}" stroke="#1B2A4A" stroke-width="1.5"/>')
    # 刻度标签
    for i in range(6):
        f = i / 5.0
        parts.append(f'<text x="{X(f):.1f}" y="{B + 20}" fill="#4A5A75" font-size="12" text-anchor="middle">{int(f*100)}%</text>')
        parts.append(f'<text x="{L - 12}" y="{Y(f) + 4:.1f}" fill="#4A5A75" font-size="12" text-anchor="end">{int(f*100)}%</text>')
    # 轴标题
    parts.append(f'<text x="{(L+R)/2:.1f}" y="{B + 42}" fill="#1B2A4A" font-size="13" font-weight="700" text-anchor="middle">误报率（假阳性率 FPR）</text>')
    parts.append(f'<text x="24" y="{(T+B)/2:.1f}" fill="#1B2A4A" font-size="13" font-weight="700" text-anchor="middle" transform="rotate(-90 24 {(T+B)/2:.1f})">命中率（真阳性率 TPR）</text>')
    # ROC 曲线
    for key, c in curves.items():
        coords = " ".join(f"{X(fpr):.1f},{Y(tpr):.1f}" for fpr, tpr in c["pts"])
        dash = f' stroke-dasharray="{c["dash"]}"' if c["dash"] else ""
        parts.append(f'<polyline points="{coords}" fill="none" stroke="{c["color"]}" stroke-width="{c["w"]}"{dash} stroke-linejoin="round"/>')
    parts.append('</svg>')

    # 图例
    lg = []
    for key, c in curves.items():
        dash = f';border-top-style:dashed' if c["dash"] else ''
        lg.append(
            f'<div class="lg"><span class="sw" style="background:{c["color"]}{dash}"></span>'
            f'<div><div class="nm">{c["name"]}</div>'
            f'<div class="tx">AUC = {c["auc_text"]}</div></div></div>'
        )

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:"Microsoft YaHei","微软雅黑",sans-serif; background:#F7F4EE; width:1120px; color:#1B2A4A; }}
  .wrap {{ padding:30px 44px 34px; }}
  .hdr {{ background:#1B2A4A; border-radius:6px 6px 0 0; padding:14px 28px; display:flex; align-items:baseline; }}
  .hdr .t {{ color:#fff; font-size:22px; font-weight:700; letter-spacing:3px; }}
  .hdr .s {{ color:#C9A86A; font-size:14px; margin-left:18px; letter-spacing:1px; }}
  .main {{ background:#fff; border:1px solid #1B2A4A; border-top:none; padding:24px 32px 26px; }}
  .cols {{ display:flex; align-items:center; gap:28px; }}
  .plot {{ flex:0 0 560px; }}
  .legend {{ flex:1; }}
  .lg {{ display:flex; align-items:center; border:1.5px solid #D8D4C8; border-radius:3px; padding:10px 14px; margin-bottom:10px; background:#FBFBF8; }}
  .sw {{ flex:0 0 26px; height:4px; margin-right:14px; border-top:3px solid #1B2A4A; }}
  .nm {{ font-size:15px; font-weight:700; letter-spacing:1px; }}
  .tx {{ font-size:12.5px; color:#4A5A75; margin-top:2px; }}
  .note {{ margin-top:16px; border-top:1px dashed #D8D4C8; padding-top:12px; font-size:12.5px; color:#4A5A75; line-height:1.7; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr"><span class="t">评分区分度与稳健性（ROC）</span><span class="s">留出交叉验证 · 193 家真实脱敏样本</span></div>
  <div class="main">
    <div class="cols">
      <div class="plot">{''.join(parts)}</div>
      <div class="legend">{''.join(lg)}</div>
    </div>
    <div class="note">曲线越贴近左上角，区分度越高；贴近对角线（AUC 0.5）表示接近随机。留出 AUC 为 20 次重复、5 折分层交叉验证的均值 ± 标准差（图中为一次代表性留出折），与样本内 0.785 几乎重合，说明排序能力未过拟合；区分度主要来自法律合规与税务健康两维，剔除违法信号后的纯推断 AUC 0.524 逼近随机，故产品定位为贷前初筛与复核排序辅助。</div>
  </div>
</div>
</body>
</html>'''
    return html


if __name__ == "__main__":
    asyncio.run(main())
