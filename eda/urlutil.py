"""URL helpers."""
from urllib.parse import urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    """Lower-case scheme/host, drop fragment and trailing slash (except root)."""
    parts = urlsplit((url or "").strip())
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    if scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def host_key(url: str) -> str:
    """Host without a leading 'www.' for same-site comparisons."""
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host
