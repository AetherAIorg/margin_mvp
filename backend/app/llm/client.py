from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.config import settings

_chat_client: OpenAI | None = None
_embedding_client: OpenAI | None = None


def get_chat_client() -> OpenAI:
    """OpenRouter chat client (OpenAI-compatible)."""
    global _chat_client
    if _chat_client is None:
        _chat_client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers={
                "HTTP-Referer": settings.openrouter_site_url,
                "X-Title": settings.openrouter_app_name,
            },
        )
    return _chat_client


def get_embedding_client() -> OpenAI | None:
    """Optional embeddings client. OpenRouter has no embeddings endpoint."""
    global _embedding_client
    if not settings.embedding_api_key:
        return None
    if _embedding_client is None:
        kwargs: dict[str, Any] = {"api_key": settings.embedding_api_key}
        if settings.embedding_base_url:
            kwargs["base_url"] = settings.embedding_base_url
        _embedding_client = OpenAI(**kwargs)
    return _embedding_client


def label_formula(label: str, raw_formula: str, language: str, dimensions: dict) -> dict:
    if not settings.openrouter_api_key:
        return {
            "proposed_name": label,
            "description": f"Detected {language} formula for {label}",
            "confidence": 0.5,
        }
    client = get_chat_client()
    prompt = f"""Analyze this financial formula and return JSON with keys:
proposed_name, description, entity, grain, confidence (0-1).

Label: {label}
Language: {language}
Formula: {raw_formula}
Current dimensions: {json.dumps(dimensions)}

Return only valid JSON."""
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    content = response.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "proposed_name": label,
            "description": f"Detected {language} formula for {label}",
            "confidence": 0.5,
        }


def explain_formula_diff(impl_a: dict, impl_b: dict) -> str:
    if not settings.openrouter_api_key:
        return (
            f"Implementation A ({impl_a.get('location')}) differs from "
            f"Implementation B ({impl_b.get('location')}) in formula structure and dimensions."
        )
    client = get_chat_client()
    prompt = f"""Explain why these two financial metric implementations differ and the business impact.
Return 2-3 sentences.

Implementation A:
{json.dumps(impl_a, indent=2)}

Implementation B:
{json.dumps(impl_b, indent=2)}"""
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return response.choices[0].message.content or ""


def embed_text(text: str) -> list[float] | None:
    client = get_embedding_client()
    if client is None:
        return None
    response = client.embeddings.create(model=settings.embedding_model, input=text[:8000])
    return response.data[0].embedding
