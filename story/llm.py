"""LLM runtime for StoryGen.

Config-driven provider selection with two interchangeable back ends:

- LiteLLM when installed (preferred: handles provider quirks);
- direct HTTP for Gemini / Anthropic / OpenAI / Ollama when LiteLLM is absent
  or fails.

Provider order is auto-detected from environment keys. Ollama is the free,
offline fallback. Every call records which provider/model actually answered.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import io_utils

ROOT = io_utils.ROOT
CONFIG_PATH = ROOT / "llm_config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "provider_order": ["gemini", "anthropic", "openai", "ollama"],
    "models": {
        "gemini": "gemini-2.5-flash",
        "anthropic": "claude-sonnet-4-5",
        "openai": "gpt-4.1-mini",
        "ollama": "qwen2.5:3b",
    },
    "stages": {
        "collector": {"temperature": 0.6, "max_tokens": 2200},
        "judge": {"temperature": 0.2, "max_tokens": 2500},
        "writer": {"temperature": 0.85, "max_tokens": 4200},
    },
    "ollama": {"host": "http://127.0.0.1:11434", "num_ctx": 4096},
    "base_urls": {"gemini": "", "anthropic": "", "openai": ""},
    "request_timeout": 900,
    "litellm": True,
}

_ENV_KEYS = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    cfg = io_utils.load_json(CONFIG_PATH, {}) or {}
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for key, value in cfg.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def save_config(cfg: dict[str, Any]) -> None:
    io_utils.save_json(CONFIG_PATH, cfg)


def api_key(provider: str) -> str | None:
    for name in _ENV_KEYS.get(provider, ()):
        value = os.environ.get(name)
        if value:
            return value
    return None


def ollama_reachable(cfg: dict[str, Any]) -> bool:
    host = cfg.get("ollama", {}).get("host", "http://127.0.0.1:11434").rstrip("/")
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def ollama_models(cfg: dict[str, Any] | None = None) -> list[str]:
    cfg = cfg or load_config()
    host = cfg.get("ollama", {}).get("host", "http://127.0.0.1:11434").rstrip("/")
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [str(m.get("name")) for m in data.get("models", [])]
    except Exception:
        return []


def ensure_ollama(cfg: dict[str, Any], wait: float = 20.0) -> bool:
    """Start a local Ollama server if the binary exists and the port is dead."""
    if ollama_reachable(cfg):
        return True
    candidates = [
        ROOT / ".ollama" / "bin" / "ollama",
        Path.home() / ".local" / "bin" / "ollama",
        Path("/usr/local/bin/ollama"),
        Path("/usr/bin/ollama"),
    ]
    binary = next((p for p in candidates if p.exists() and os.access(p, os.X_OK)), None)
    if binary is None:
        return False
    env = dict(os.environ)
    env.setdefault("OLLAMA_MODELS", str(ROOT / ".ollama" / "models"))
    try:
        import subprocess

        subprocess.Popen(
            [str(binary), "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        return False
    deadline = time.time() + wait
    while time.time() < deadline:
        if ollama_reachable(cfg):
            return True
        time.sleep(0.5)
    return False


def available_providers(cfg: dict[str, Any] | None = None) -> list[str]:
    cfg = cfg or load_config()
    out = []
    for provider in cfg["provider_order"]:
        if provider == "ollama":
            if ollama_reachable(cfg) or any(
                p.exists()
                for p in (
                    ROOT / ".ollama" / "bin" / "ollama",
                    Path.home() / ".local" / "bin" / "ollama",
                )
            ):
                out.append(provider)
        elif api_key(provider):
            out.append(provider)
    return out


def describe_runtime(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    return {
        "config": str(CONFIG_PATH),
        "providers": available_providers(cfg),
        "order": cfg["provider_order"],
        "models": cfg["models"],
        "ollama_reachable": ollama_reachable(cfg),
        "stages": cfg["stages"],
    }


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_json(text: str) -> Any:
    """Best-effort extraction of the first JSON object/array in a string."""
    text = _strip_fences(text)
    try:
        return json.loads(text)
    except Exception:
        pass
    # scan for balanced braces / brackets
    for opening, closing in (("{", "}"), ("[", "]")):
        start = text.find(opening)
        if start == -1:
            continue
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opening:
                depth += 1
            elif ch == closing:
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
                        fixed = fixed.replace("“", '"').replace("”", '"')
                        try:
                            return json.loads(fixed)
                        except Exception:
                            break
        if depth > 0:
            continue
    raise ValueError(f"No valid JSON found in LLM output: {text[:300]!r}")


# ---------------------------------------------------------------------------
# Provider back ends (raw HTTP)
# ---------------------------------------------------------------------------

def _http_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout: float) -> Any:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _raw_gemini(prompt: str, cfg: dict[str, Any], stage: dict[str, Any], json_mode: bool) -> str:
    key = api_key("gemini")
    if not key:
        raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY not set")
    model = cfg["models"]["gemini"]
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    generation: dict[str, Any] = {
        "temperature": stage.get("temperature", 0.7),
        "maxOutputTokens": stage.get("max_tokens", 3000),
    }
    if json_mode:
        generation["responseMimeType"] = "application/json"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation,
    }
    data = _http_json(
        url, payload, {"Content-Type": "application/json"}, cfg["request_timeout"]
    )
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def _raw_anthropic(prompt: str, cfg: dict[str, Any], stage: dict[str, Any], json_mode: bool) -> str:
    key = api_key("anthropic")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    model = cfg["models"]["anthropic"]
    payload = {
        "model": model,
        "max_tokens": stage.get("max_tokens", 3000),
        "temperature": stage.get("temperature", 0.7),
        "messages": [{"role": "user", "content": prompt}],
    }
    data = _http_json(
        "https://api.anthropic.com/v1/messages",
        payload,
        {
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        cfg["request_timeout"],
    )
    return "".join(part.get("text", "") for part in data.get("content", []))


def _raw_openai(prompt: str, cfg: dict[str, Any], stage: dict[str, Any], json_mode: bool) -> str:
    key = api_key("openai")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    payload = {
        "model": cfg["models"]["openai"],
        "temperature": stage.get("temperature", 0.7),
        "max_tokens": stage.get("max_tokens", 3000),
        "messages": [{"role": "user", "content": prompt}],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    base = (cfg.get("base_urls", {}).get("openai") or "https://api.openai.com/v1").rstrip("/")
    data = _http_json(
        f"{base}/chat/completions",
        payload,
        {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        cfg["request_timeout"],
    )
    return data["choices"][0]["message"]["content"]


def _raw_ollama(prompt: str, cfg: dict[str, Any], stage: dict[str, Any], json_mode: bool) -> str:
    host = cfg.get("ollama", {}).get("host", "http://127.0.0.1:11434").rstrip("/")
    if not ollama_reachable(cfg):
        ensure_ollama(cfg)
    payload = {
        "model": cfg["models"]["ollama"],
        "stream": False,
        "messages": [{"role": "user", "content": prompt}],
        "options": {
            "temperature": stage.get("temperature", 0.7),
            "num_predict": stage.get("max_tokens", 3000),
            "num_ctx": int(cfg.get("ollama", {}).get("num_ctx", 4096)),
        },
    }
    if json_mode:
        payload["format"] = "json"
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            data = _http_json(
                f"{host}/api/chat",
                payload,
                {"Content-Type": "application/json"},
                cfg["request_timeout"],
            )
            return data["message"]["content"]
        except TimeoutError as exc:
            print(
                f"[llm] ollama timed out after {cfg['request_timeout']}s; not retrying",
                flush=True,
            )
            raise
        except Exception as exc:  # noqa: BLE001 - transient 500s happen on CPU Ollama
            last_exc = exc
            print(
                f"[llm] ollama request failed ({attempt + 1}/3): "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                if not ollama_reachable(cfg):
                    ensure_ollama(cfg)
    raise RuntimeError(f"Ollama request failed after 3 attempts: {last_exc}")


_RAW = {
    "gemini": _raw_gemini,
    "anthropic": _raw_anthropic,
    "openai": _raw_openai,
    "ollama": _raw_ollama,
}

LAST_CALL: dict[str, Any] = {"provider": None, "model": None, "calls": 0}


# ---------------------------------------------------------------------------
# LiteLLM back end
# ---------------------------------------------------------------------------

_LITELLM_MODEL = {
    "gemini": "gemini/{model}",
    "anthropic": "anthropic/{model}",
    "openai": "openai/{model}",
    "ollama": "ollama/{model}",
}


def _litellm_call(
    provider: str,
    prompt: str,
    cfg: dict[str, Any],
    stage: dict[str, Any],
    json_mode: bool,
) -> str:
    import litellm  # noqa: PLC0415

    model = _LITELLM_MODEL[provider].format(model=cfg["models"][provider])
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": stage.get("temperature", 0.7),
        "max_tokens": stage.get("max_tokens", 3000),
        "timeout": cfg["request_timeout"],
    }
    if provider == "ollama":
        kwargs["api_base"] = cfg.get("ollama", {}).get("host", "http://127.0.0.1:11434")
        kwargs["num_ctx"] = int(cfg.get("ollama", {}).get("num_ctx", 4096))
    elif cfg.get("base_urls", {}).get(provider):
        kwargs["api_base"] = cfg["base_urls"][provider]
    if json_mode and provider in ("openai", "gemini"):
        kwargs["response_format"] = {"type": "json_object"}
    resp = litellm.completion(**kwargs)
    return resp.choices[0].message.content


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _call_provider(
    provider: str,
    prompt: str,
    cfg: dict[str, Any],
    stage: dict[str, Any],
    json_mode: bool,
    use_litellm: bool,
) -> str:
    # Local Ollama goes through its native API: that path lets us enforce
    # format="json" and num_ctx, which the generic LiteLLM call does not expose
    # consistently for local models.
    if provider == "ollama":
        return _RAW["ollama"](prompt, cfg, stage, json_mode)
    if use_litellm:
        try:
            return _litellm_call(provider, prompt, cfg, stage, json_mode)
        except Exception as exc:  # noqa: BLE001 - fall through to raw HTTP
            print(f"[llm] litellm/{provider} failed ({type(exc).__name__}: {exc}); trying HTTP", flush=True)
    return _RAW[provider](prompt, cfg, stage, json_mode)


def complete(
    prompt: str,
    stage_name: str = "writer",
    provider: str | None = None,
    json_mode: bool = False,
    temperature: float | None = None,
    max_tokens: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> str:
    """Run one completion, trying providers per config until one answers."""
    cfg = cfg or load_config()
    stage = dict(cfg["stages"].get(stage_name, {}))
    if temperature is not None:
        stage["temperature"] = temperature
    if max_tokens is not None:
        stage["max_tokens"] = max_tokens

    order = list(cfg["provider_order"])
    stage_provider = cfg.get("stages", {}).get(stage_name, {}).get("provider")
    if provider:
        order = [provider] + [p for p in order if p != provider]
    elif stage_provider:
        order = [stage_provider] + [p for p in order if p != stage_provider]

    available = available_providers(cfg)
    if not available:
        raise RuntimeError(
            "No LLM provider is available. Set GEMINI_API_KEY / ANTHROPIC_API_KEY / "
            "OPENAI_API_KEY, or install Ollama and run `python storygen.py setup --pull`."
        )
    ordered = [p for p in order if p in available] + [p for p in order if p not in available]

    errors = []
    for p in ordered:
        if p == "ollama" and not ollama_reachable(cfg):
            ensure_ollama(cfg)
        try:
            text = _call_provider(p, prompt, cfg, stage, json_mode, cfg.get("litellm", True))
            if text and text.strip():
                if LAST_CALL["provider"] != p:
                    print(
                        f"[llm] answered by {p}/{cfg['models'][p]}",
                        flush=True,
                    )
                LAST_CALL.update(
                    {"provider": p, "model": cfg["models"][p], "calls": LAST_CALL["calls"] + 1}
                )
                return text
            errors.append(f"{p}: empty response")
        except Exception as exc:  # noqa: BLE001 - try next provider
            errors.append(f"{p}: {type(exc).__name__}: {exc}")
            print(f"[llm] {p} unavailable: {type(exc).__name__}: {exc}", flush=True)

    raise RuntimeError(
        "No LLM provider answered. Tried: "
        + " | ".join(errors)
        + ". Run `python storygen.py setup --pull` or set an API key."
    )


def complete_json(
    prompt: str,
    stage_name: str = "writer",
    provider: str | None = None,
    retries: int = 1,
    cfg: dict[str, Any] | None = None,
) -> Any:
    """Completion + JSON extraction, with one repair retry."""
    text = complete(prompt, stage_name=stage_name, provider=provider, json_mode=True, cfg=cfg)
    try:
        return extract_json(text)
    except ValueError as exc:
        if retries <= 0:
            raise
        repair = (
            "Your previous answer was not valid JSON. Return ONLY valid JSON, "
            "no prose, no code fences.\n\n" + prompt
        )
        text = complete(repair, stage_name=stage_name, provider=provider, json_mode=True, cfg=cfg)
        return extract_json(text)


def quick_ping(provider: str | None = None) -> str:
    """One tiny call used by setup/tests."""
    return complete("Reply with the single word: ok", stage_name="judge", provider=provider, max_tokens=8)
