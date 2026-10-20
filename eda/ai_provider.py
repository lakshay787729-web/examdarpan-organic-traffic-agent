"""Optional AI suggestions. Disabled unless config + an API key are present."""
import logging

import requests

log = logging.getLogger("eda.ai")


class AIError(Exception):
    pass


SYSTEM = ("You are a careful SEO editor for an Indian government-jobs and exam information website. "
          "Give practical, honest suggestions. NEVER invent facts, dates, vacancies, or statistics. "
          "If something must be confirmed on the official notification, say 'verify on the official notice'. "
          "Do not promise rankings or traffic. Reply in the same language as the article where sensible.")


def build_prompt(page: dict, issues: list, ideas: dict, max_chars: int) -> str:
    parts = [f"Title: {page.get('title', '')}", f"Meta description: {page.get('description', '')}",
             f"H1: {' / '.join(page.get('h1s', []))}", f"H2: {' | '.join(page.get('h2s', [])[:10])}",
             f"Word count: {page.get('word_count')}", f"Dates in text near 'last date': {page.get('deadline_dates')}",
             f"Detected issues: {'; '.join(i['message'] for i in issues[:8])}",
             f"Topics not covered: {', '.join(ideas.get('coverage_gaps', []))}",
             f"Article excerpt: {page.get('excerpt', '')}"]
    body = "\n".join(parts)[:max_chars]
    return (body + "\n\nTask: give (1) two better SEO title options under 60 characters, (2) one meta description under "
            "155 characters, (3) up to 4 genuinely useful FAQ questions readers may have, (4) facts that must be "
            "verified against official sources. Use only what is in the text above. Keep it short.")


class GeminiProvider:
    def __init__(self, api_key, model, timeout, session=None):
        self.key, self.model, self.timeout = api_key, model, timeout
        self.session = session or requests.Session()

    def generate(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        try:
            r = self.session.post(url, headers={"x-goog-api-key": self.key, "Content-Type": "application/json"},
                                  json={"systemInstruction": {"parts": [{"text": SYSTEM}]},
                                        "contents": [{"parts": [{"text": prompt}]}]}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise AIError(f"AI request failed ({type(exc).__name__})")
        if r.status_code != 200:
            raise AIError(f"AI provider returned HTTP {r.status_code}")
        try:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError, ValueError, TypeError):
            raise AIError("AI response had an unexpected shape")


class OpenAICompatProvider:
    def __init__(self, api_key, model, base_url, timeout, session=None):
        self.key, self.model, self.base, self.timeout = api_key, model, base_url.rstrip("/"), timeout
        self.session = session or requests.Session()

    def generate(self, prompt: str) -> str:
        try:
            r = self.session.post(f"{self.base}/chat/completions",
                                  headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                                  json={"model": self.model, "messages": [{"role": "system", "content": SYSTEM},
                                                                           {"role": "user", "content": prompt}]},
                                  timeout=self.timeout)
        except requests.RequestException as exc:
            raise AIError(f"AI request failed ({type(exc).__name__})")
        if r.status_code != 200:
            raise AIError(f"AI provider returned HTTP {r.status_code}")
        try:
            return r.json()["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, ValueError, TypeError, AttributeError):
            raise AIError("AI response had an unexpected shape")


def build_provider(ai_cfg: dict, env: dict, session=None):
    """Return a provider or None (AI off / no key). Never raises for missing config."""
    name = ai_cfg.get("provider", "none")
    key = (env.get("AI_API_KEY") or "").strip()
    if name == "none" or not key or int(ai_cfg.get("max_calls_per_run", 0)) <= 0:
        return None
    if name == "gemini":
        return GeminiProvider(key, ai_cfg["model"], ai_cfg["timeout_seconds"], session)
    if name == "openai_compatible":
        return OpenAICompatProvider(key, ai_cfg["model"], ai_cfg["base_url"], ai_cfg["timeout_seconds"], session)
    return None
