"""Thin Deepgram REST client (speech-to-text + text-to-speech) and a keyterm linter."""

from __future__ import annotations

import os
import re
import time

import requests

API = "https://api.deepgram.com/v1"
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_KEYTERMS = 100
MAX_KEYTERM_TOKENS = 500
GENERIC_WORDS = {"the", "and", "is", "a", "an", "of", "to", "in", "it", "that", "for", "on", "with"}


class DeepgramError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"Deepgram returned {status}: {body[:300]}")
        self.status = status


def lint_keyterms(terms: list[str]) -> list[str]:
    """Flag keyterm formats the docs call invalid. The API accepts them without an error."""
    problems = []
    for t in terms:
        if "," in t or ";" in t:
            parts = [p.strip() for p in re.split(r"[,;]", t) if p.strip()]
            problems.append(
                f"{t!r} looks like a list. The docs say it is treated as ONE literal term. "
                f"Use the documented form, one term per parameter: {parts}"
            )
        if re.search(r":\s*-?\d+(\.\d+)?$", t):
            problems.append(
                f"{t!r} has a weight. The docs say keyterm does not support weights. "
                f"Use {re.sub(r':\s*-?\d+(\.\d+)?$', '', t)!r}."
            )
        if "\n" in t:
            problems.append(f"{t!r} contains a line break; split it into separate terms.")
        if t.strip().lower() in GENERIC_WORDS:
            problems.append(f"{t!r} is a generic word; it is rarely misheard and wastes budget.")
    if len(terms) > MAX_KEYTERMS:
        problems.append(f"{len(terms)} terms exceeds the {MAX_KEYTERMS}-term limit.")
    approx_tokens = sum(max(1, round(len(t.split()) * 1.5)) for t in terms)
    if approx_tokens > MAX_KEYTERM_TOKENS:
        problems.append(f"~{approx_tokens} tokens across keyterms; the limit is {MAX_KEYTERM_TOKENS}.")
    return problems


class Deepgram:
    def __init__(self, api_key: str | None = None, timeout: float = 60.0, max_retries: int = 3,
                 session: requests.Session | None = None):
        self.api_key = api_key or os.environ.get("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise ValueError("No Deepgram API key. Set DEEPGRAM_API_KEY (free credit at https://console.deepgram.com).")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()

    def _post(self, path: str, params, **kwargs) -> requests.Response:
        headers = {"Authorization": f"Token {self.api_key}", **kwargs.pop("headers", {})}
        for attempt in range(self.max_retries + 1):
            resp = self.session.post(f"{API}{path}", params=params, headers=headers,
                                     timeout=self.timeout, **kwargs)
            if resp.status_code == 200:
                return resp
            if resp.status_code not in RETRY_STATUSES or attempt == self.max_retries:
                raise DeepgramError(resp.status_code, resp.text)
            time.sleep(min(2.0**attempt, 8.0))
        raise AssertionError("unreachable")

    def speak(self, text: str, voice: str = "aura-2-thalia-en", sample_rate: int = 8000) -> bytes:
        """Synthesize WAV audio. 8 kHz by default, the same bandwidth as a phone call."""
        params = {"model": voice, "encoding": "linear16", "container": "wav", "sample_rate": sample_rate}
        return self._post("/speak", params, json={"text": text},
                          headers={"Content-Type": "application/json"}).content

    def listen(self, audio: bytes, keyterms: list[str] | None = None, model: str = "nova-3",
               mimetype: str = "audio/wav") -> dict:
        """Pre-recorded transcription. Each keyterm is sent as its own repeated query parameter."""
        params: list[tuple[str, str]] = [("model", model), ("smart_format", "true")]
        params += [("keyterm", t) for t in (keyterms or [])]
        resp = self._post("/listen", params, data=audio, headers={"Content-Type": mimetype})
        return resp.json()


def transcript_of(response: dict) -> str:
    return response["results"]["channels"][0]["alternatives"][0]["transcript"]
