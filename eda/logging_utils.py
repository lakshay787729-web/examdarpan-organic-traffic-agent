"""Logging that never prints secrets."""
import json
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

SECRET_ENV_NAMES = ("GSC_SERVICE_ACCOUNT_JSON", "AI_API_KEY")

_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"ya29\.[0-9A-Za-z_\-]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{10,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
]


def collect_secrets(env) -> list:
    """Return secret strings (and parts of the service-account JSON) to redact."""
    secrets = set()
    for name in SECRET_ENV_NAMES:
        val = (env.get(name) or "").strip()
        if len(val) >= 6:
            secrets.add(val)
        if name == "GSC_SERVICE_ACCOUNT_JSON" and val:
            try:
                info = json.loads(val)
                for key in ("private_key", "private_key_id", "client_id"):
                    part = str(info.get(key, "")) if isinstance(info, dict) else ""
                    if len(part) >= 6:
                        secrets.add(part)
                        secrets.add(part.replace("\n", "\\n"))
            except ValueError:
                pass
    return sorted(secrets, key=len, reverse=True)


def redact(text: str, secrets=()) -> str:
    for s in secrets:
        text = text.replace(s, "***")
    for rx in _PATTERNS:
        text = rx.sub("***", text)
    return text


class RedactingFormatter(logging.Formatter):
    def __init__(self, fmt, secrets=()):
        super().__init__(fmt)
        self._secrets = list(secrets)

    def format(self, record):
        return redact(super().format(record), self._secrets)


def setup_logging(log_dir, level="INFO", env=None, console=True) -> logging.Logger:
    secrets = collect_secrets(env or {})
    logger = logging.getLogger("eda")
    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    for h in list(logger.handlers):
        logger.removeHandler(h)
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    handlers = []
    if console:
        handlers.append(logging.StreamHandler())
    try:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(Path(log_dir) / "agent.log", maxBytes=500_000, backupCount=2, encoding="utf-8"))
    except OSError:
        pass
    for h in handlers:
        h.setFormatter(RedactingFormatter(fmt, secrets))
        logger.addHandler(h)
    logger.propagate = False
    return logger
