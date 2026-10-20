"""Text helpers: tokenizing (English + Hindi), n-grams, dates, hashing.

Note: Python's regex \\w does not match Devanagari vowel signs, so we split on
whitespace/punctuation instead of using \\w.
"""
import hashlib
import re
from collections import Counter
from datetime import date, datetime

_SPLIT = re.compile(r"[\s\.,;:!?\"'\u201c\u201d\u2018\u2019()\[\]{}<>|/\\\-\u2013\u2014_+=*&^%$#@~`\u0964\u0965\u2022\u00b7\u2026]+")
_SENT = re.compile(r"[\.\u0964\u0965!?\n\r|\u2022]+")

STOPWORDS = set(
    """a an the and or but if of to in on at by for with from as is are was were be been being this that
    these those it its into than then so such not no yes can will would should could may might must do
    does did done have has had you your we our they their he she his her i me my us them there here
    which who whom what when where why how also all any each more most other some very just only over
    under about after before between during out up down off per via etc""".split()
) | set(
    """\u0915\u093e \u0915\u0940 \u0915\u0947 \u092e\u0947\u0902 \u0939\u0948 \u0939\u0948\u0902 \u0914\u0930 \u0938\u0947 \u0915\u094b \u092a\u0930 \u090f\u0915 \u092f\u0939 \u092f\u0947 \u0935\u0939 \u0935\u0947 \u0925\u093e \u0925\u0940 \u0925\u0947 \u092d\u0940 \u0924\u094b \u0939\u0940 \u0915\u093f
    \u0932\u093f\u090f \u0932\u093f\u092f\u0947 \u0926\u094d\u0935\u093e\u0930\u093e \u0924\u0915 \u092f\u093e \u091c\u094b \u0907\u0938 \u0909\u0938 \u0915\u0930 \u0915\u0930\u0947\u0902 \u0915\u0930\u0947 \u0939\u094b\u0917\u093e \u0939\u094b \u0917\u092f\u093e \u0917\u0908 \u0917\u090f \u0938\u093e\u0925 \u092c\u093e\u0926 \u0905\u092a\u0928\u0947 \u0905\u092a\u0928\u0940
    \u0938\u092d\u0940 \u0915\u0941\u091b \u0935\u093e\u0932\u0947 \u0935\u093e\u0932\u0940 \u0935\u093e\u0932\u093e \u0930\u0939\u0947 \u0930\u0939\u093e \u091c\u093e \u0905\u092c \u091c\u092c \u0924\u092c \u0915\u094b\u0908 \u0928\u0939\u0940\u0902 \u0938\u0915\u0924\u0947 \u0938\u0915\u0924\u093e \u0938\u0915\u0924\u0940""".split()
)

_MONTHS_EN = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_MONTHS_HI = {
    "\u091c\u0928\u0935\u0930\u0940": 1, "\u092b\u0930\u0935\u0930\u0940": 2, "\u092b\u093c\u0930\u0935\u0930\u0940": 2,
    "\u092e\u093e\u0930\u094d\u091a": 3, "\u0905\u092a\u094d\u0930\u0948\u0932": 4, "\u092e\u0908": 5,
    "\u091c\u0942\u0928": 6, "\u091c\u0941\u0932\u093e\u0908": 7, "\u0905\u0917\u0938\u094d\u0924": 8,
    "\u0938\u093f\u0924\u0902\u092c\u0930": 9, "\u0938\u093f\u0924\u092e\u094d\u092c\u0930": 9,
    "\u0905\u0915\u094d\u091f\u0942\u092c\u0930": 10, "\u0905\u0915\u094d\u0924\u0942\u092c\u0930": 10,
    "\u0928\u0935\u0902\u092c\u0930": 11, "\u0928\u0935\u092e\u094d\u092c\u0930": 11,
    "\u0926\u093f\u0938\u0902\u092c\u0930": 12, "\u0926\u093f\u0938\u092e\u094d\u092c\u0930": 12,
}
_NUM_DATE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")
_EN_DATE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(\d{4})\b",
    re.I,
)
_HI_DATE = re.compile(r"(\d{1,2})\s+(" + "|".join(re.escape(m) for m in _MONTHS_HI) + r")\s*,?\s*(\d{4})")

DEADLINE_KEYWORDS = (
    "last date", "closing date", "last day to apply", "apply before", "deadline",
    "\u0905\u0902\u0924\u093f\u092e \u0924\u093f\u0925\u093f", "\u0905\u0902\u0924\u093f\u092e \u0926\u093f\u0928\u093e\u0902\u0915",
    "\u0906\u0935\u0947\u0926\u0928 \u0915\u0940 \u0905\u0902\u0924\u093f\u092e",
)


def normalize_ws(text) -> str:
    return " ".join((text or "").split())


def tokenize(text) -> list:
    return [t for t in _SPLIT.split((text or "").lower()) if t]


def content_hash(text) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def is_noise(tok: str) -> bool:
    return tok in STOPWORDS or len(tok) < 2 or (tok.isdigit() and len(tok) < 4)


def top_terms(text, n=15) -> list:
    counts = Counter(t for t in tokenize(text) if not is_noise(t))
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [[t, c] for t, c in ranked[:n]]


def top_phrases(text, n=12, min_count=2) -> list:
    counts = Counter()
    for sent in _SENT.split(text or ""):
        toks = tokenize(sent)
        for size in (2, 3):
            for i in range(len(toks) - size + 1):
                gram = toks[i:i + size]
                if gram[0] in STOPWORDS or gram[-1] in STOPWORDS:
                    continue
                if any(len(t) < 2 for t in gram):
                    continue
                counts[" ".join(gram)] += 1
    ranked = sorted(((p, c) for p, c in counts.items() if c >= min_count),
                    key=lambda kv: (-kv[1], -len(kv[0].split()), kv[0]))
    kept = []
    for phrase, c in ranked:
        if any(phrase in k and kc >= c for k, kc in kept):
            continue
        kept.append((phrase, c))
        if len(kept) >= n:
            break
    return [[p, c] for p, c in kept]


def find_dates(chunk: str) -> list:
    found = []
    for rx, kind in ((_NUM_DATE, "num"), (_EN_DATE, "en"), (_HI_DATE, "hi")):
        for m in rx.finditer(chunk or ""):
            try:
                if kind == "num":
                    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                elif kind == "en":
                    d, mo, y = int(m.group(1)), _MONTHS_EN[m.group(2).lower()[:3]], int(m.group(3))
                else:
                    d, mo, y = int(m.group(1)), _MONTHS_HI[m.group(2)], int(m.group(3))
                found.append(date(y, mo, d))
            except (ValueError, KeyError):
                continue
    return found


def find_deadline_dates(text: str, window: int = 120) -> list:
    """ISO dates that appear shortly after 'last date'-style words."""
    low = (text or "").lower()
    out = set()
    for kw in DEADLINE_KEYWORDS:
        start = 0
        while True:
            idx = low.find(kw, start)
            if idx < 0:
                break
            for d in find_dates(text[idx: idx + window]):
                out.add(d.isoformat())
            start = idx + len(kw)
    return sorted(out)


def parse_iso_date(value):
    """Parse '2026-03-01', '2026-03-01T10:00:00Z' etc. Returns date or None."""
    if not value:
        return None
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
    return None
