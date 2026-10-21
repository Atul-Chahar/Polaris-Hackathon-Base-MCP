"""Minimal JSON-mode LLM client (Gemini primary, NVIDIA NIM fallback).

    from llm_client import complete_json
    obj = complete_json(system_prompt, user_prompt, timeout=4.0)  # dict or None

Never raises. Returns None on any error / timeout / missing keys.

Env vars (a `.env` in the repo root is loaded if present; real env wins):
    LLM_PROVIDER    gemini | nim | none   (default: gemini if GEMINI_API_KEY,
                                           else nim if NVIDIA_API_KEY, else none)
    GEMINI_API_KEY, GEMINI_MODEL          (default gemini-2.5-flash-lite)
    NVIDIA_API_KEY, NIM_MODEL             (default google/gemma-3-12b-it; alt
                                           nv-mistralai/mistral-nemo-12b-instruct.
                                           NOTE: meta/llama-3.x models are EOL (HTTP 410))
    LLM_FALLBACK    1 (default) / 0       try the other provider if primary fails
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent


def _load_dotenv(path: Path = _ROOT / ".env") -> None:
    try:
        if not path.is_file():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            elif " #" in val:
                val = val.split(" #", 1)[0].rstrip()
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception as e:  # pragma: no cover
        _warn(f"failed to load .env: {e}")


def _warn(msg: str) -> None:
    try:
        print(f"[llm_client] WARNING: {msg}", file=sys.stderr, flush=True)
    except Exception:
        pass


_load_dotenv()

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# Shared keep-alive client. httpx.Client is thread-safe for concurrent requests.
_client_lock = threading.Lock()
_client: httpx.Client | None = None

# Simple circuit breaker: after a 429/5xx, skip that provider for a while so we
# don't burn the per-call budget on a provider that is rate-limiting us.
_cooldown_until: dict[str, float] = {}
_COOLDOWN_S = {"429": 20.0, "5xx": 5.0}

# NIM: remember if the model rejected response_format so we stop sending it.
_nim_no_response_format = False


def _http() -> httpx.Client:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = httpx.Client(
                    http2=False,
                    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10,
                                        keepalive_expiry=120),
                    headers={"Content-Type": "application/json"},
                )
    return _client


def _cfg(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _has_key(provider: str) -> bool:
    if provider == "gemini":
        return bool(_cfg("GEMINI_API_KEY"))
    if provider == "nim":
        return bool(_cfg("NVIDIA_API_KEY"))
    return False


def _primary_provider() -> str:
    p = _cfg("LLM_PROVIDER").lower()
    if p in ("gemini", "nim", "none"):
        return p
    if _has_key("gemini"):
        return "gemini"
    if _has_key("nim"):
        return "nim"
    return "none"


def is_enabled() -> bool:
    """True if at least one provider is configured and usable."""
    p = _primary_provider()
    return p != "none" and (_has_key(p) or _has_key("gemini") or _has_key("nim"))


# ----------------------------------------------------------------- parsing --
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _parse_json_obj(text: str) -> dict | None:
    if not text:
        return None
    t = _FENCE_RE.sub("", text.strip())
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            return obj[0]
    except Exception:
        pass
    # Extract the first balanced {...} block.
    start = t.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(t)):
            c = t[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(t[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except Exception:
                        pass
                    break
        start = t.find("{", start + 1)
    return None


def _note_status(provider: str, status: int) -> None:
    if status == 429:
        _cooldown_until[provider] = time.monotonic() + _COOLDOWN_S["429"]
    elif status >= 500:
        _cooldown_until[provider] = time.monotonic() + _COOLDOWN_S["5xx"]


def _cooling(provider: str) -> bool:
    return time.monotonic() < _cooldown_until.get(provider, 0.0)


# ----------------------------------------------------------------- gemini ---
def _gemini_thinking(model: str) -> dict | None:
    m = model.lower()
    if "2.5" in m:
        return {"thinkingBudget": 0}  # disable thinking -> much lower latency
    if m.startswith("gemini-3") or "gemini-3" in m:
        return {"thinkingLevel": "minimal" if "flash" in m else "low"}
    return None


def _call_gemini(system: str, user: str, timeout: float) -> dict | None:
    key = _cfg("GEMINI_API_KEY")
    model = _cfg("GEMINI_MODEL", "gemini-2.5-flash-lite")
    gen_cfg: dict = {"temperature": 0, "responseMimeType": "application/json",
                     "maxOutputTokens": int(_cfg("LLM_MAX_TOKENS", "512") or 512)}
    thinking = _gemini_thinking(model)
    if thinking:
        gen_cfg["thinkingConfig"] = thinking
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": gen_cfg,
    }
    deadline = time.monotonic() + timeout
    for attempt in range(2):
        remaining = deadline - time.monotonic()
        if remaining <= 0.05:
            _warn("gemini: out of time")
            return None
        r = _http().post(GEMINI_URL.format(model=model), json=body,
                         headers={"x-goog-api-key": key}, timeout=remaining)
        if (r.status_code == 400 and attempt == 0 and "thinkingConfig" in gen_cfg
                and "think" in r.text.lower()):
            gen_cfg.pop("thinkingConfig", None)  # model may not support it; retry once
            continue
        if r.status_code != 200:
            _note_status("gemini", r.status_code)
            _warn(f"gemini HTTP {r.status_code}: {r.text[:200]!r}")
            return None
        data = r.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        except Exception:
            _warn(f"gemini: unexpected response {str(data)[:200]!r}")
            return None
        obj = _parse_json_obj(text)
        if obj is None:
            _warn(f"gemini: non-JSON output {text[:200]!r}")
        return obj
    return None


# -------------------------------------------------------------------- nim ---
def _call_nim(system: str, user: str, timeout: float) -> dict | None:
    global _nim_no_response_format
    key = _cfg("NVIDIA_API_KEY")
    model = _cfg("NIM_MODEL", "google/gemma-3-12b-it")
    sys_txt = system + "\nRespond with a single JSON object only, no prose."
    if "gemma" in model.lower():  # Gemma chat templates have no system role
        messages = [{"role": "user", "content": f"{sys_txt}\n\n{user}"}]
    else:
        messages = [{"role": "system", "content": sys_txt}, {"role": "user", "content": user}]
    body: dict = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": int(_cfg("LLM_MAX_TOKENS", "512") or 512),
        "stream": False,
    }
    deadline = time.monotonic() + timeout
    for attempt in range(2):
        if not _nim_no_response_format:
            body["response_format"] = {"type": "json_object"}
        else:
            body.pop("response_format", None)
        remaining = deadline - time.monotonic()
        if remaining <= 0.05:
            _warn("nim: out of time")
            return None
        r = _http().post(NIM_URL, json=body, timeout=remaining,
                         headers={"Authorization": f"Bearer {key}",
                                  "Accept": "application/json"})
        if r.status_code in (400, 422) and attempt == 0 and not _nim_no_response_format:
            _nim_no_response_format = True  # model rejected response_format; retry plain
            continue
        if r.status_code != 200:
            _note_status("nim", r.status_code)
            _warn(f"nim HTTP {r.status_code}: {r.text[:200]!r}")
            return None
        data = r.json()
        try:
            text = data["choices"][0]["message"].get("content") or ""
        except Exception:
            _warn(f"nim: unexpected response {str(data)[:200]!r}")
            return None
        obj = _parse_json_obj(text)
        if obj is None:
            _warn(f"nim: non-JSON output {text[:200]!r}")
        return obj
    return None


_CALLERS = {"gemini": _call_gemini, "nim": _call_nim}


def _try(provider: str, system: str, user: str, timeout: float) -> dict | None:
    if not _has_key(provider):
        return None
    if _cooling(provider):
        _warn(f"{provider}: in cooldown after rate-limit/error, skipping")
        return None
    try:
        return _CALLERS[provider](system, user, timeout)
    except httpx.TimeoutException:
        _warn(f"{provider}: timeout after {timeout:.2f}s")
    except Exception as e:
        _warn(f"{provider}: {type(e).__name__}: {e}")
    return None


def complete_json(system: str, user: str, timeout: float = 4.0) -> dict | None:
    """One JSON-mode completion. Returns a dict, or None on any failure. Never raises."""
    try:
        primary = _primary_provider()
        if primary == "none":
            return None
        deadline = time.monotonic() + max(0.1, timeout)
        order = [primary]
        if _cfg("LLM_FALLBACK", "1") != "0":
            other = "nim" if primary == "gemini" else "gemini"
            order.append(other)
        for prov in order:
            remaining = deadline - time.monotonic()
            if remaining < 0.3:
                break
            res = _try(prov, system, user, remaining)
            if res is not None:
                return res
        return None
    except Exception as e:  # absolute safety net
        _warn(f"complete_json: {type(e).__name__}: {e}")
        return None


if __name__ == "__main__":
    sys_p = ("You rewrite search queries. Return JSON: "
             '{"keywords": [str], "filters": {"category": str|null}, "intent": str}.')
    usr_p = "cheap waterproof hiking boots for women under $100"
    print(f"provider={_primary_provider()} gemini_model={_cfg('GEMINI_MODEL', 'gemini-2.5-flash-lite')} "
          f"nim_model={_cfg('NIM_MODEL', 'google/gemma-3-12b-it')}")
    for i in range(int(sys.argv[1]) if len(sys.argv) > 1 else 3):
        t0 = time.perf_counter()
        out = complete_json(sys_p, usr_p, timeout=4.0)
        print(f"[{i}] {(time.perf_counter() - t0) * 1000:.0f} ms -> {out}")
