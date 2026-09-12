"""意图识别 —— 核心业务回归样例（扩展版，200+ 条）

用途
----
对「规则引擎识别准确率」做回归实测：逐条调用 parse_intent，比对输出
function 与期望 function。全部样例命中才算通过。与 intent_engine.evaluate()
（13 条内置核心样例）互补，本文件为扩展后的全量业务回归集。

运行
----
    cd backend
    python -m app.services.intent_regression
"""
from __future__ import annotations

from app.services.intent_engine import parse_intent

# (query, expected_function)
REGRESSION_CASES: list[tuple[str, str]] = [
    # ---------------- score（评分 / 打分 / 综合分 / 风险等级 / 税务健康 / 纳税） ----------------
    ("分析企业税务健康评分", "score"),
    ("查询企业综合评分", "score"),
    ("这家公司的风险评分是多少", "score"),
    ("给这批企业打分", "score"),
    ("企业风险等级怎么划分", "score"),
    ("看看税务健康状况", "score"),
    ("纳税健康度分析", "score"),
    ("企业的综合分数是多少", "score"),
    ("风险等级评估", "score"),
    ("税务健康怎么样", "score"),
    ("信用评分查询", "score"),
    ("整体评分情况", "score"),
    ("纳税情况评分", "score"),
    ("打分排名", "score"),
    ("风险等级一览", "score"),
    ("税务健康打分", "score"),
    ("综合评分对比", "score"),
    ("企业评分多少分", "score"),
    ("风险分值", "score"),
    ("税务健康评级", "score"),
    ("综合分是多少", "score"),
    ("纳税健康评分", "score"),
    ("制造业企业的税务健康评分", "score"),
    ("批发零售行业的综合评分", "score"),

    # ---------------- authenticity（真实性 / 真伪 / 造假 / 虚开 / 可信度 / 经营真实） ----------------
    ("分析企业经营真实性", "authenticity"),
    ("这家企业经营真实吗", "authenticity"),
    ("企业数据可信度如何", "authenticity"),
    ("检查是否存在造假嫌疑", "authenticity"),
    ("发票虚开风险排查", "authenticity"),
    ("经营真伪核查", "authenticity"),
    ("企业账目可信度评估", "authenticity"),
    ("是否存在经营造假", "authenticity"),
    ("经营真实性验证", "authenticity"),
    ("数据真伪鉴别", "authenticity"),
    ("企业信用可信度分析", "authenticity"),
    ("核查经营真实性", "authenticity"),
    ("虚开发票风险", "authenticity"),
    ("企业经营可信度", "authenticity"),
    ("真伪核验", "authenticity"),
    ("真实性核查", "authenticity"),
    ("造假风险分析", "authenticity"),
    ("经营真实性评估", "authenticity"),
    ("数据造假识别", "authenticity"),
    ("可信度分析", "authenticity"),
    ("制造企业经营真实性", "authenticity"),
    ("建筑行业虚开风险", "authenticity"),

    # ---------------- fraud（舞弊 / 欺诈 / 发票异常 / 红冲 / 集中度 / 异常检测 / 进销错配） ----------------
    ("发票舞弊异常检测", "fraud"),
    ("检查发票舞弊情况", "fraud"),
    ("企业是否存在发票欺诈", "fraud"),
    ("发票异常排查", "fraud"),
    ("红冲发票分析", "fraud"),
    ("客户集中度分析", "fraud"),
    ("进销错配检测", "fraud"),
    ("异常检测分析", "fraud"),
    ("舞弊风险排查", "fraud"),
    ("发票异常检测", "fraud"),
    ("供应商集中度核查", "fraud"),
    ("进销错配分析", "fraud"),
    ("欺诈风险识别", "fraud"),
    ("发票红冲情况", "fraud"),
    ("发票舞弊排查", "fraud"),
    ("经营异常检测", "fraud"),
    ("客户集中度风险", "fraud"),
    ("进销错配风险", "fraud"),
    ("发票异常情况分析", "fraud"),
    ("舞弊检测", "fraud"),
    ("零售行业发票异常", "fraud"),
    ("批发企业进销错配", "fraud"),

    # ---------------- benchmark（对标 / 同业 / 行业对比 / 基准 / 同行） ----------------
    ("跟同业对标分析", "benchmark"),
    ("企业与同行对比", "benchmark"),
    ("行业对比分析", "benchmark"),
    ("同业对标情况", "benchmark"),
    ("跟同行比怎么样", "benchmark"),
    ("行业基准对比", "benchmark"),
    ("同业基准分析", "benchmark"),
    ("对标同行业企业", "benchmark"),
    ("行业对标分析", "benchmark"),
    ("与同行对比", "benchmark"),
    ("同业竞争对比", "benchmark"),
    ("行业基准线分析", "benchmark"),
    ("对标分析", "benchmark"),
    ("同行基准比较", "benchmark"),
    ("同业平均水平对比", "benchmark"),
    ("跟同行对标", "benchmark"),
    ("行业对比情况", "benchmark"),
    ("对标同业企业", "benchmark"),
    ("同行业对比", "benchmark"),
    ("企业对标分析", "benchmark"),
    ("制造业同业对标", "benchmark"),
    ("行业基准对比分析", "benchmark"),

    # ---------------- trend（趋势 / 走向 / 同比 / 环比 / 走势 / 变化） ----------------
    ("分析营收趋势", "trend"),
    ("行业走势如何", "trend"),
    ("营收同比变化", "trend"),
    ("环比增速分析", "trend"),
    ("经营趋势分析", "trend"),
    ("税负走向分析", "trend"),
    ("营收走势分析", "trend"),
    ("同比变化情况", "trend"),
    ("净利润趋势", "trend"),
    ("毛利率走向", "trend"),
    ("营收环比变化", "trend"),
    ("行业趋势分析", "trend"),
    ("经营趋势走向", "trend"),
    ("税负率同比变化", "trend"),
    ("营业收入趋势", "trend"),
    ("利润走势分析", "trend"),
    ("同比增速分析", "trend"),
    ("趋势变化情况", "trend"),
    ("营收走势预测", "trend"),
    ("环比走势", "trend"),
    ("制造业营收趋势", "trend"),
    ("零售行业走势", "trend"),

    # ---------------- report（报告 / 生成报告 / 出报告 / 导出 / 评估报告） ----------------
    ("生成一份评估报告", "report"),
    ("导出行业分析报告", "report"),
    ("出具企业评估报告", "report"),
    ("生成行业聚合报告", "report"),
    ("输出风险评估报告", "report"),
    ("出一份企业报告", "report"),
    ("生成经营分析报告", "report"),
    ("导出评估报告", "report"),
    ("生成 PDF 报告", "report"),
    ("出报告", "report"),
    ("生成财税分析报告", "report"),
    ("导出企业体检报告", "report"),
    ("生成风险分析报告", "report"),
    ("出评估报告", "report"),
    ("生成行业报告", "report"),
    ("导出财税报告", "report"),
    ("生成企业诊断报告", "report"),
    ("出具风险报告", "report"),
    ("生成经营体检报告", "report"),
    ("导出聚合报告", "report"),
    ("生成行业风险评估报告", "report"),
    ("出行业分析报告", "report"),

    # ---------------- email_report（邮件 / 发送报告 / 发到邮箱） ----------------
    ("把报告发到邮箱", "email_report"),
    ("发送报告到我的邮箱", "email_report"),
    ("发邮件给我", "email_report"),
    ("把评估报告发到邮箱", "email_report"),
    ("邮件发送报告", "email_report"),
    ("将报告发到指定邮箱", "email_report"),
    ("发送报告到邮箱", "email_report"),
    ("把报告发邮件给我", "email_report"),
    ("发到邮箱", "email_report"),
    ("邮件发送评估报告", "email_report"),
    ("把分析报告发到邮箱", "email_report"),
    ("邮件推送报告", "email_report"),
    ("把报告发到我的邮箱", "email_report"),
    ("发邮件", "email_report"),
    ("将报告邮件发给我", "email_report"),
    ("报告发到邮箱", "email_report"),

    # ---------------- custom_report（定制 / 自定义） ----------------
    ("定制一份风险评估报告", "custom_report"),
    ("自定义报告章节", "custom_report"),
    ("帮我定制行业报告", "custom_report"),
    ("AI 定制报告", "custom_report"),
    ("自定义一份经营分析报告", "custom_report"),
    ("定制企业体检报告", "custom_report"),
    ("自定义报告内容", "custom_report"),
    ("帮我定制评估报告", "custom_report"),
    ("定制行业聚合报告", "custom_report"),
    ("自定义财税报告", "custom_report"),
    ("定制风险分析报告", "custom_report"),
    ("自定义报告模板", "custom_report"),
    ("定制经营分析报告", "custom_report"),
    ("帮我定制一份报告", "custom_report"),
    ("自定义企业报告", "custom_report"),
    ("定制报告", "custom_report"),

    # ---------------- signal（预警 / 信号 / 告警 / 风险点 / 风险分布） ----------------
    ("有哪些风险预警信号", "signal"),
    ("企业风险预警排查", "signal"),
    ("风险信号分析", "signal"),
    ("查看风险告警", "signal"),
    ("梳理企业风险点", "signal"),
    ("各行业的风险分布", "signal"),
    ("风险预警情况", "signal"),
    ("风险信号提示", "signal"),
    ("风险告警分析", "signal"),
    ("企业风险点梳理", "signal"),
    ("风险预警信号有哪些", "signal"),
    ("预警信号分析", "signal"),
    ("风险分布情况", "signal"),
    ("风险点排查", "signal"),
    ("风险预警分析", "signal"),
    ("告警信息查询", "signal"),
    ("风险信号排查", "signal"),
    ("风险分布分析", "signal"),
    ("风险预警提示", "signal"),
    ("风险点分析", "signal"),
    ("预警情况分析", "signal"),
    ("风险信号预警", "signal"),

    # ---------------- general（无明确功能词 → 兜底） ----------------
    ("你好", "general"),
    ("谢谢", "general"),
    ("这个产品是做什么的", "general"),
    ("介绍一下你们的功能", "general"),
    ("怎么使用这个系统", "general"),
    ("你好呀", "general"),
    ("麻烦介绍一下", "general"),
    ("请问你是谁", "general"),
    ("这个系统有什么特点", "general"),
    ("怎么开始使用", "general"),
    ("感谢你的帮助", "general"),
    ("产品有哪些能力", "general"),
    ("如何使用", "general"),
    ("你好，请问", "general"),
    ("帮我解释一下", "general"),
    ("有什么可以帮我的", "general"),
]


def evaluate_regression() -> dict:
    """对全量回归样例做识别，返回 accuracy / total / correct / failures。"""
    ok = 0
    details: list[dict] = []
    for q, expect in REGRESSION_CASES:
        got = parse_intent(q).function
        hit = got == expect
        ok += int(hit)
        details.append({"query": q, "expected": expect, "got": got, "ok": hit})
    return {
        "accuracy": round(100.0 * ok / max(len(REGRESSION_CASES), 1), 2),
        "total": len(REGRESSION_CASES),
        "correct": ok,
        "failures": [d for d in details if not d["ok"]],
    }


if __name__ == "__main__":
    r = evaluate_regression()
    print(f"total={r['total']} correct={r['correct']} accuracy={r['accuracy']}%")
    if r["failures"]:
        print("--- failures ---")
        for d in r["failures"]:
            print(f"  {d['query']!r}  expect={d['expected']}  got={d['got']}")
    else:
        print("all passed")
