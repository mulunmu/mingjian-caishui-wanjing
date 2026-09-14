import json
from collections import Counter
r=json.load(open("backend/_dialog_boundary_report.json",encoding="utf-8"))
print("total",r["total"],"ok",r["ok"],"fail",r["fail"])
for k,v in sorted(r["by_family"].items(), key=lambda x:-x[1]["fail"]):
    print(f"  {k}: ok={v['ok']} fail={v['fail']}")
c=Counter()
for items in r["fail_samples"].values():
    for it in items:
        for e in it["errors"]:
            if "overview" in e: c["overview_reread"]+=1
            elif e=="preach" or e.startswith("preach"): c["preach"]+=1
            elif e.startswith("parse"): c["parse_mismatch"]+=1
            else: c[e[:40]]+=1
print("tags",dict(c))
for fam in ["negotiate_slice","scope_guard","anaphora"]:
    print("##",fam)
    for it in (r["fail_samples"].get(fam) or [])[:4]:
        print(it["id"], it["errors"], (it.get("reply") or "")[:90].replace("\n"," "))
