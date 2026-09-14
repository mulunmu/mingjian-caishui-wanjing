"""对运行中后端做多场景对话冒烟（可选，默认 24 条；--full 跑扩展集）。

用法（容器内）：
  python -m scripts.run_chat_natural_batch
  python -m scripts.run_chat_natural_batch --full
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("CHAT_BATCH_BASE", "http://127.0.0.1:8000/api/v1")

CORE = [
    "这家能贷吗？",
    "信用怎么样？",
    "哪里不对劲？",
    "哪里可疑要查？",
    "整体风险评分如何？",
    "经营真实性怎么样？",
    "制造行业趋势如何？",
    "批发零售哪里异常？",
    "建筑业能不能贷？",
    "纳税信用大概什么等级？",
    "红冲要不要重点查？",
    "和同业比怎么样？",
]

EXTRA = [
    f"{ind}{q}"
    for ind in ["制造", "批发零售", "建筑", "IT软件", "服务"]
    for q in ["能贷吗？", "信用怎么样？", "哪里异常？", "哪里可疑要查？"]
]


def _demo_login() -> str:
    req = urllib.request.Request(
        f"{BASE}/auth/demo-login",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["access_token"]


def _chat(token: str, query: str, session_id: str | None = None) -> dict:
    body = {"query": query}
    if session_id:
        body["session_id"] = session_id
    req = urllib.request.Request(
        f"{BASE}/chat",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    queries = CORE + (EXTRA if args.full else [])
    token = _demo_login()
    ok = fail = 0
    sid = None
    for i, q in enumerate(queries, 1):
        try:
            out = _chat(token, q, sid)
            sid = out.get("session_id") or sid
            reply = (out.get("reply") or "").strip()
            bad = []
            if "[规则模板生成]" in reply:
                bad.append("prefix")
            if not reply:
                bad.append("empty")
            first = reply.split("\n", 1)[0] if reply else ""
            if not any(k in first for k in ("稳", "弱", "好", "坏", "风险", "异常", "可疑", "谨慎", "可控", "信用", "贷", "核查", "建议", "偏")):
                bad.append("first")
            if "进销错配" in reply or "序列缺口" in reply or "六维雷达" in reply:
                bad.append("jargon")
            if bad:
                fail += 1
                print(f"FAIL [{i}] {q} :: {bad} :: {first[:60]}")
            else:
                ok += 1
                print(f"OK   [{i}] {q} :: {first[:50]}")
        except urllib.error.HTTPError as e:
            fail += 1
            print(f"FAIL [{i}] {q} :: HTTP {e.code}")
        except Exception as e:
            fail += 1
            print(f"FAIL [{i}] {q} :: {e}")
    print(f"\nSUMMARY ok={ok} fail={fail} total={ok+fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
