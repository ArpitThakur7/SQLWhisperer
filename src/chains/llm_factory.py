"""LLM Provider Factory for SQLWhisperer.

Abstracts LLM instantiation to support:
1. Groq (100% Free & Fast: Llama 3.3 70B, Qwen 2.5 Coder)
2. Google Gemini (100% Free Tier: Gemini 2.0 Flash)
3. Ollama (100% Free & Offline: Qwen 2.5 Coder, DeepSeek Coder)
4. OpenRouter (Free models: meta-llama/llama-3.3-70b-instruct:free)
5. OpenAI (GPT-4o, GPT-4o-mini)

Now accepts an optional ``SessionConfig`` to resolve provider, model, and
API key on a per-request basis — eliminating the stale-singleton bug.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from src.config.settings import settings
from src.config.session import SessionConfig, DEFAULT_SESSION
from loguru import logger


class LLMConfigurationError(Exception):
    """Raised when the LLM provider is misconfigured (e.g. missing API key)."""


def get_chat_llm(
    temperature: float | None = None,
    session: SessionConfig | None = None,
) -> BaseChatModel:
    """Return a configured ChatModel instance.

    Parameters
    ----------
    temperature:
        Override temperature.  ``None`` uses the global default.
    session:
        Per-request overrides for provider, model, and API key.
        When ``None``, falls back to global ``settings``.
    """
    cfg = session or DEFAULT_SESSION
    temp = temperature if temperature is not None else cfg.resolved_temperature
    provider = cfg.resolved_llm_provider
    model = cfg.resolved_model
    api_key = cfg.resolved_api_key

    # 1. Groq (100% Free Tier, Ultra-Fast Inference)
    if provider == "groq":
        if not api_key or api_key == "ollama":
            raise LLMConfigurationError(
                "Groq requires an API key. Get one free at https://console.groq.com/keys"
            )
        logger.debug(f"Instantiating Groq model: {model}")
        return ChatOpenAI(
            model=model,
            temperature=temp,
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )

    # 2. Google Gemini (Free Tier via OpenAI-compatible endpoint)
    if provider == "gemini":
        if not api_key or api_key == "ollama":
            raise LLMConfigurationError(
                "Gemini requires an API key. Get one free at https://aistudio.google.com/app/apikey"
            )
        logger.debug(f"Instantiating Gemini model: {model}")
        return ChatOpenAI(
            model=model,
            temperature=temp,
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )

    # 3. OpenRouter (Free community models)
    if provider == "openrouter":
        if not api_key or api_key == "ollama":
            raise LLMConfigurationError(
                "OpenRouter requires an API key. Get one at https://openrouter.ai/keys"
            )
        logger.debug(f"Instantiating OpenRouter model: {model}")
        return ChatOpenAI(
            model=model,
            temperature=temp,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    # 4. Local SLM / Ollama (100% Free & Offline on RTX 4050 GPU)
    if provider in ("ollama", "local_slm"):
        base_url = f"{cfg.resolved_ollama_base_url.rstrip('/')}/v1"
        logger.debug(f"Instantiating Local SLM / Ollama model: {model} @ {base_url}")
        return ChatOpenAI(
            model=model,
            temperature=temp,
            api_key="ollama",
            base_url=base_url,
        )

    # 5. Default to OpenAI
    if not api_key:
        raise LLMConfigurationError(
            "OpenAI requires an API key. Set OPENAI_API_KEY in .env or enter one in the UI."
        )
    logger.debug(f"Instantiating OpenAI model: {model}")
    return ChatOpenAI(
        model=model,
        temperature=temp,
        api_key=api_key,
    )


def get_chat_llm_with_fallbacks(
    temperature: float | None = None,
    session: SessionConfig | None = None,
) -> BaseChatModel:
    """Return a resilient ChatModel with automated multi-provider fallback cascade.

    If the primary provider experiences rate limits (429) or cloud outages (5xx),
    LangChain will failover seamlessly to configured secondary providers.
    """
    primary = get_chat_llm(temperature=temperature, session=session)
    cfg = session or DEFAULT_SESSION
    primary_provider = cfg.resolved_llm_provider

    fallbacks: list[BaseChatModel] = []
    # Candidate priority sequence
    candidates = ["gemini", "groq", "openai", "ollama"]

    for prov in candidates:
        if prov == primary_provider:
            continue
        try:
            fb_session = SessionConfig(
                llm_provider=prov,
                api_key=None,
                model=None,
            )
            fb_llm = get_chat_llm(temperature=temperature, session=fb_session)
            fallbacks.append(fb_llm)
        except Exception:
            # Skip providers that don't have configured credentials
            continue

    if fallbacks:
        logger.debug(f"Attached {len(fallbacks)} fallback providers for resilient cascade.")
        return primary.with_fallbacks(fallbacks)
    return primary

