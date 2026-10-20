"""Keyword ideas derived ONLY from an article's own content.

Nothing here is search-volume data. Every idea is an estimate to be checked
against Search Console before it is used.
"""
from .textutil import normalize_ws

# family label -> words that show the article already covers that topic
INTENT_FAMILIES = {
    "eligibility": ["eligibility", "\u092a\u093e\u0924\u094d\u0930\u0924\u093e", "\u092f\u094b\u0917\u094d\u092f\u0924\u093e"],
    "last date": ["last date", "closing date", "\u0905\u0902\u0924\u093f\u092e \u0924\u093f\u0925\u093f"],
    "notification": ["notification", "\u0905\u0927\u093f\u0938\u0942\u091a\u0928\u093e", "\u0935\u093f\u091c\u094d\u091e\u093e\u092a\u0928"],
    "syllabus": ["syllabus", "\u092a\u093e\u0920\u094d\u092f\u0915\u094d\u0930\u092e"],
    "admit card": ["admit card", "\u090f\u0921\u092e\u093f\u091f \u0915\u093e\u0930\u094d\u0921", "\u092a\u094d\u0930\u0935\u0947\u0936 \u092a\u0924\u094d\u0930"],
    "result": ["result", "\u092a\u0930\u093f\u0923\u093e\u092e", "\u0930\u093f\u091c\u0932\u094d\u091f"],
    "how to apply": ["how to apply", "apply online", "\u0906\u0935\u0947\u0926\u0928 \u0915\u0948\u0938\u0947", "\u0911\u0928\u0932\u093e\u0907\u0928 \u0906\u0935\u0947\u0926\u0928"],
    "salary": ["salary", "pay scale", "\u0935\u0947\u0924\u0928"],
    "age limit": ["age limit", "\u0906\u092f\u0941 \u0938\u0940\u092e\u093e"],
    "cut off": ["cut off", "cutoff", "\u0915\u091f\u0911\u092b", "\u0915\u091f \u0911\u092b"],
}
EXAM_HINTS = ("recruitment", "vacancy", "exam", "result", "admit card", "syllabus", "notification",
              "bharti", "\u092d\u0930\u094d\u0924\u0940", "\u092a\u0930\u0940\u0915\u094d\u0937\u093e", "\u092a\u0930\u093f\u0923\u093e\u092e",
              "\u0930\u093f\u091c\u0932\u094d\u091f", "\u092a\u093e\u0920\u094d\u092f\u0915\u094d\u0930\u092e", "\u090f\u0921\u092e\u093f\u091f",
              "\u0905\u0927\u093f\u0938\u0942\u091a\u0928\u093e", "\u0935\u093f\u091c\u094d\u091e\u093e\u092a\u0928")


def intents_present(text_lower: str) -> list:
    return sorted(label for label, words in INTENT_FAMILIES.items() if any(w in text_lower for w in words))


def looks_exam_related(text_lower: str) -> bool:
    return any(h in text_lower for h in EXAM_HINTS)


def clean_title(title: str) -> str:
    title = normalize_ws(title)
    for sep in (" | ", " - ", " \u2013 ", " \u2014 "):
        if sep in title:
            title = title.split(sep)[0]
    return title.strip()


def topic_of(page: dict) -> str:
    base = (page.get("h1s") or [""])[0] or clean_title(page.get("title", ""))
    return " ".join(base.split()[:6])


def build_ideas(page: dict, kw_cfg: dict) -> dict:
    max_phrases = int(kw_cfg.get("max_phrases", 12))
    max_ideas = int(kw_cfg.get("max_ideas", 10))
    phrases, seen = [], set()

    def add(text, source, note=""):
        key = normalize_ws(text).lower()
        if key and key not in seen and len(phrases) < max_phrases:
            seen.add(key)
            phrases.append({"phrase": normalize_ws(text), "source": source, "note": note})

    if page.get("title"):
        add(clean_title(page["title"]), "title")
    for h in (page.get("h1s") or [])[:1]:
        add(h, "main heading (H1)")
    for h in (page.get("h2s") or [])[:6]:
        if len(h) <= 80:
            add(h, "sub-heading (H2)")
    for phrase, count in page.get("phrases", []):
        add(phrase, "repeated in text", f"appears {count} times")

    gaps, ideas = [], []
    if page.get("exam_related"):
        present = set(page.get("intents_present", []))
        topic = topic_of(page)
        for label in INTENT_FAMILIES:
            if label not in present:
                gaps.append(label)
                if topic and len(ideas) < max_ideas:
                    ideas.append(f"{topic} {label}")
    return {"phrases": phrases, "coverage_gaps": gaps, "query_ideas": ideas}
