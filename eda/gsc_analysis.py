"""Turn Search Console rows into plain-language opportunities. Real data in, flags out."""
from .urlutil import normalize_url

# Rough rule-of-thumb average CTR by position. NOT Google data; only used to spot pages
# that look unusually weak for where they rank.
_CTR = {1: 0.28, 2: 0.15, 3: 0.10, 4: 0.07, 5: 0.05, 6: 0.04, 7: 0.03, 8: 0.025, 9: 0.02, 10: 0.018}


def expected_ctr(position: float) -> float:
    return _CTR.get(max(1, round(position)), 0.01)


def analyze_gsc(data: dict, cfg: dict) -> dict:
    by_page = {}
    for row in data.get("pages", []):
        url = normalize_url(row["keys"][0])
        by_page[url] = {"clicks": row.get("clicks", 0), "impressions": row.get("impressions", 0),
                        "ctr": row.get("ctr", 0.0), "position": row.get("position", 0.0), "flags": []}
    prev = {normalize_url(r["keys"][0]): r for r in data.get("prev_pages", [])}
    min_imp = cfg["min_impressions"]
    for url, m in by_page.items():
        imp, pos = m["impressions"], m["position"]
        if imp >= min_imp and pos <= 20 and m["ctr"] < expected_ctr(pos) * cfg["low_ctr_factor"]:
            m["flags"].append("LOW_CTR")
        if imp >= min_imp * 2 and m["clicks"] <= cfg["few_clicks_max"]:
            m["flags"].append("FEW_CLICKS")
        if imp >= min_imp and cfg["striking_min_position"] <= pos <= cfg["striking_max_position"]:
            m["flags"].append("STRIKING_DISTANCE")
        p = prev.get(url)
        if p and p.get("clicks", 0) >= 10 and m["clicks"] <= p["clicks"] * (1 - cfg["decline_pct"] / 100.0):
            m["flags"].append("DECLINING")
            m["prev_clicks"] = p["clicks"]
    for url, p in prev.items():
        if url not in by_page and p.get("clicks", 0) >= 10:
            by_page[url] = {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0,
                            "flags": ["DECLINING"], "prev_clicks": p["clicks"]}

    queries = {}
    for row in data.get("page_queries", []):
        q, page = row["keys"][0], normalize_url(row["keys"][1])
        queries.setdefault(q, []).append({"url": page, "impressions": row.get("impressions", 0),
                                          "clicks": row.get("clicks", 0), "position": row.get("position", 0.0)})
    cannibal = []
    for q, rows in queries.items():
        strong = [r for r in rows if r["impressions"] >= cfg["min_query_impressions"]]
        if len(strong) >= 2:
            strong.sort(key=lambda r: -r["impressions"])
            cannibal.append({"query": q, "pages": strong[:5], "total_impressions": sum(r["impressions"] for r in strong)})
    cannibal.sort(key=lambda c: (-c["total_impressions"], c["query"]))

    top_queries = {}
    for q, rows in queries.items():
        for r in rows:
            top_queries.setdefault(r["url"], []).append({"query": q, "impressions": r["impressions"],
                                                         "clicks": r["clicks"], "position": r["position"]})
    for url in top_queries:
        top_queries[url].sort(key=lambda r: (-r["impressions"], r["query"]))
        top_queries[url] = top_queries[url][:5]
    return {"by_page": by_page, "cannibalization": cannibal[:30], "top_queries": top_queries,
            "period": data.get("period", {})}
