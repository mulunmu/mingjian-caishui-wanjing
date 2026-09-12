# -*- coding: utf-8 -*-
"""
回应致命#2「自己出题自己考」：真做盲测（留出交叉验证）

方法：
- 193 家为同一时点横截面样本，无时间先后 → 分层 K 折交叉验证（K=5，重复 R=20，不同随机种子）
- 每个测试企业的评分，其行业/发票/财务等「同行对标」只用训练折样本计算（测试企业不参与自己的基准），
  彻底避免「自己数据进自己分数」的隐性泄漏
- 阈值 40 为业务先验设定（贷前初筛），不在各折内重调；在留出折上套用，看召回/误报是否泛化
地面真值 = tax_violation_cnt>0 OR tax_arrears_cnt>0（108 阳性 / 85 阴性）
"""
import asyncio
import bisect
import random
import statistics

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models.core_metrics import CoreMetrics, LegalEvent
from app.services.assessment import _build_result
from app.services.assessment_weights import DIMENSION_LABELS

DATABASE_URL = "postgresql+asyncpg://risk_user:risk_pass@db:5432/risk_db"
THRESHOLD = 40  # 贷前初筛先验阈值（重定位后）


def auc(y, s):
    """AUC = P(阴性分数 > 阳性分数)。分数越高越安全，阳性(有违法)应得低分。"""
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


def score_one(m, ref_metrics, evs):
    r = _build_result(m, ref_metrics, evs)
    return r["overall_score"], r["dimensions"]


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

    n = len(metrics)
    npos = sum(m._label for m in metrics)
    nneg = n - npos
    print(f"N={n} 阳性={npos} 阴性={nneg}")

    # 1) 全样本（样本内）AUC，作对照
    full_scores = [score_one(m, metrics, by_ent.get(m.enterprise_id, []))[0] for m in metrics]
    full_labels = [m._label for m in metrics]
    print(f"样本内 overall AUC = {auc(full_labels, full_scores):.3f}")

    # 2) 分层 K 折重复 CV
    K, R = 5, 20
    pos = [m for m in metrics if m._label == 1]
    neg = [m for m in metrics if m._label == 0]
    repeat_aucs = []
    pooled_pred = {}   # eid -> (score, label)，仅记录 seed=0，保证每企业恰好预测一次
    pooled_dims = {}
    for seed in range(R):
        rng = random.Random(seed)
        p = pos[:]
        rng.shuffle(p)
        g = neg[:]
        rng.shuffle(g)
        p_folds = [[] for _ in range(K)]
        g_folds = [[] for _ in range(K)]
        for i, x in enumerate(p):
            p_folds[i % K].append(x)
        for i, x in enumerate(g):
            g_folds[i % K].append(x)
        folds = [p_folds[k] + g_folds[k] for k in range(K)]
        test_aucs = []
        for k in range(K):
            test = folds[k]
            train = [m for j in range(K) if j != k for m in folds[j]]
            y, s = [], []
            for m in test:
                # 参照集 = 训练折 + 自身（自身特征作输入、不参与其他测试企业；与生产 all_metrics 恒含自身一致）
                sc, dims = score_one(m, train + [m], by_ent.get(m.enterprise_id, []))
                y.append(m._label)
                s.append(sc)
                if seed == 0:
                    pooled_pred[m.enterprise_id] = (sc, m._label)
                    pooled_dims[m.enterprise_id] = dims
            test_aucs.append(auc(y, s))
        repeat_aucs.append(sum(test_aucs) / len(test_aucs))

    mean_auc = sum(repeat_aucs) / len(repeat_aucs)
    std_auc = statistics.stdev(repeat_aucs) if len(repeat_aucs) > 1 else 0.0
    print(f"留出 CV 平均 AUC = {mean_auc:.3f} ± {std_auc:.3f}（{R} 次重复 × {K} 折，样本外）")

    # 3) 留出混淆矩阵 @ threshold=40（seed=0，每企业预测一次）
    tp = fp = tn = fn = 0
    for eid, (sc, lab) in pooled_pred.items():
        pred = 1 if sc < THRESHOLD else 0
        if lab == 1 and pred == 1:
            tp += 1
        elif lab == 0 and pred == 1:
            fp += 1
        elif lab == 0 and pred == 0:
            tn += 1
        else:
            fn += 1
    rec = tp / (tp + fn) * 100 if (tp + fn) else 0
    fpr = fp / (fp + tn) * 100 if (fp + tn) else 0
    spec = tn / (tn + fp) * 100 if (tn + fp) else 0
    print(f"\n留出混淆矩阵 @阈值{THRESHOLD}（样本外，每企业预测一次）:")
    print(f"  TP={tp} FP={fp} TN={tn} FN={fn}")
    print(f"  召回率 {rec:.1f}%  误报率 {fpr:.1f}%  特异度 {spec:.1f}%")

    # 4) 分维度留出 AUC（seed=0）
    print(f"\n分维度留出 AUC（样本外，seed=0）:")
    for k in ["tax_health", "authenticity", "invoice", "industry", "legal", "finance"]:
        y = [pooled_pred[e][1] for e in pooled_pred]
        s = [pooled_dims[e][k] for e in pooled_pred]
        print(f"  {DIMENSION_LABELS[k]:8s} ({k:14s}) AUC = {auc(y, s):.3f}")


if __name__ == "__main__":
    asyncio.run(main())
