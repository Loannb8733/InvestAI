import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.domains.crowdfunding.audit.prompt import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

Provider = Callable[[list[dict[str, str]]], Awaitable[str]]
TIMEOUT_SECONDS = 90.0
MAX_TOKENS = 4096
TEMPERATURE = 0.2
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key="


async def call_anthropic(messages: list[dict[str, str]]) -> str:
    """Réponse brute de Claude ; ``ValueError`` sur toute erreur d'API."""
    try:
        import anthropic
    except ImportError as exc:
        raise ValueError("Le package 'anthropic' n'est pas installé. Utilisez Ollama ou installez anthropic.") from exc
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    logger.info("Calling Claude API for crowdfunding analysis")
    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=messages,
            timeout=TIMEOUT_SECONDS,
        )
    except anthropic.AuthenticationError as exc:
        raise ValueError("Clé API Anthropic invalide — vérifiez ANTHROPIC_API_KEY") from exc
    except anthropic.RateLimitError as exc:
        raise ValueError("Limite de requêtes Anthropic atteinte — réessayez dans quelques minutes") from exc
    except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
        logger.error("Anthropic API connectivity error: %s", exc)
        raise ValueError("Timeout ou erreur de connexion à l'API Anthropic") from exc
    except anthropic.APIError as exc:
        logger.error("Anthropic API error: %s", exc)
        raise ValueError(f"Erreur API Anthropic : {exc}") from exc
    raw_text: str = response.content[0].text
    logger.info("Claude response received (%d chars)", len(raw_text))
    return raw_text


async def _post(name: str, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        try:
            return await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ValueError(f"Timeout de connexion à l'API {name}") from exc
        except httpx.ConnectError as exc:
            raise ValueError(f"Erreur de connexion à l'API {name}") from exc


def _check_status(
    name: str, response: httpx.Response, *, auth_key: str | None = None, detail_on_400: bool = False
) -> None:
    if response.status_code == 401 and auth_key:
        raise ValueError(f"Clé API {name} invalide — vérifiez {auth_key}")
    if response.status_code == 400 and detail_on_400:
        detail = response.json().get("error", {}).get("message", response.text[:200])
        raise ValueError(f"Erreur {name} : {detail}")
    if response.status_code == 429:
        raise ValueError(f"Limite de requêtes {name} atteinte — réessayez dans quelques minutes")
    if response.status_code != 200:
        raise ValueError(f"Erreur {name} (HTTP {response.status_code}) : {response.text[:200]}")


async def call_groq(messages: list[dict[str, str]]) -> str:
    """Réponse brute de Groq (llama-3.1-8b-instant) ; ``ValueError`` sur toute erreur."""
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": messages[0]["content"]}],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": "json_object"},
    }
    logger.info("Calling Groq API (llama-3.1-8b-instant) for crowdfunding analysis")
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
    response = await _post("Groq", GROQ_URL, payload, headers)
    _check_status("Groq", response, auth_key="GROQ_API_KEY")
    data = response.json()
    try:
        raw_text: str = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise ValueError(f"Réponse Groq inattendue : {str(data)[:200]}") from exc
    logger.info("Groq response received (%d chars)", len(raw_text))
    return raw_text


async def call_gemini(messages: list[dict[str, str]]) -> str:
    """Réponse brute de Gemini 2.0 Flash ; ``ValueError`` sur toute erreur."""
    parts = [{"text": SYSTEM_PROMPT}, *({"text": message["content"]} for message in messages)]
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": TEMPERATURE,
            "maxOutputTokens": MAX_TOKENS,
            "responseMimeType": "application/json",
        },
    }
    logger.info("Calling Gemini API for crowdfunding analysis")
    response = await _post("Gemini", f"{GEMINI_URL}{settings.GEMINI_API_KEY}", payload)
    _check_status("Gemini", response, detail_on_400=True)
    data = response.json()
    try:
        raw_text: str = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise ValueError(f"Réponse Gemini inattendue : {str(data)[:200]}") from exc
    logger.info("Gemini response received (%d chars)", len(raw_text))
    return raw_text


def ollama_reachable() -> bool:
    """Faux en production quand OLLAMA_URL désigne un hôte interne à Docker, injoignable hors Compose."""
    if settings.APP_ENV != "production":
        return True
    hostname = urlparse(settings.OLLAMA_URL).hostname or ""
    return not (hostname and "." not in hostname and hostname not in ("localhost", "127"))


async def call_ollama(messages: list[dict[str, str]]) -> str:
    """Réponse brute du modèle Ollama configuré ; ``ValueError`` s'il est injoignable ou répond vide."""
    if not ollama_reachable():
        raise ValueError(f"Ollama skipped (Docker-internal URL: {settings.OLLAMA_URL})")
    url = f"{settings.OLLAMA_URL}/api/chat"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": messages[0]["content"]}],
        "stream": False,
        "format": "json",
        "options": {"temperature": TEMPERATURE, "num_predict": MAX_TOKENS},
    }
    logger.info("Calling Ollama (%s) at %s", settings.OLLAMA_MODEL, url)
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(url, json=payload)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.error("Ollama connection failed: %s: %s", type(exc).__name__, exc)
            raise ValueError(f"Ollama non disponible ({settings.OLLAMA_URL})") from exc
    if response.status_code != 200:
        raise ValueError(f"Erreur Ollama (HTTP {response.status_code}) : {response.text[:200]}")
    raw_text: str = response.json().get("message", {}).get("content", "")
    if not raw_text:
        raise ValueError("Réponse Ollama vide")
    logger.info("Ollama response received (%d chars)", len(raw_text))
    return raw_text


def configured_providers() -> list[tuple[str, Provider]]:
    """Fournisseurs configurés, dans l'ordre d'essai : Groq, Gemini, Anthropic, puis Ollama."""
    candidates: list[tuple[str, Any, Provider]] = [
        ("Groq", settings.GROQ_API_KEY, call_groq),
        ("Gemini", settings.GEMINI_API_KEY, call_gemini),
        ("Anthropic", settings.ANTHROPIC_API_KEY, call_anthropic),
        ("Ollama", settings.OLLAMA_URL, call_ollama),
    ]
    return [(name, provider) for name, configured, provider in candidates if configured]
