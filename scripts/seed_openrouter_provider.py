#!/usr/bin/env python3
"""Seed OpenRouter provider with a strongest→weakest free-model fallback chain.

Idempotent:
  - creates `openrouter-default` if absent
  - if it exists, only updates `config.fallback_models` + `model_name`
    (API key, enabled, is_default are preserved)

The chain is the project's default for «после триала Claude → бесплатные мощные
модели OpenRouter»: при недоступности первой (HTTP 402/404/429/5xx —
`_RETRIABLE_STATUSES` в `cloud_llm_service.py`) бридж автоматически переходит
к следующей. Все позиции — `:free` варианты на OpenRouter.

Порядок ОТ МОЩНЫХ К СЛАБЕЕ (по состоянию на январь 2026 — переоценивать раз в
квартал, free-модели приходят/уходят):

  1. deepseek/deepseek-r1:free               — рассуждающая модель уровня o1
  2. deepseek/deepseek-chat-v3.1:free        — 671B MoE, general-purpose
  3. meta-llama/llama-3.3-70b-instruct:free  — 70B, крепкая база
  4. qwen/qwen-2.5-72b-instruct:free         — 72B, сильный multilingual (ru/kz)
  5. nvidia/llama-3.1-nemotron-70b-instruct:free — instruct-fine-tune от nvidia
  6. google/gemini-2.0-flash-exp:free        — gemini flash experimental
  7. meta-llama/llama-3.2-11b-vision-instruct:free — средний размер + vision
  8. mistralai/mistral-nemo:free             — 12B, дешёвый fallback
  9. meta-llama/llama-3.1-8b-instruct:free   — 8B, самый лёгкий

Run:
  venv/bin/python scripts/seed_openrouter_provider.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import AsyncSessionLocal
from db.repositories.cloud_provider import CloudProviderRepository


PROVIDER_ID = "openrouter-default"
PROVIDER_NAME = "OpenRouter (free chain)"

FALLBACK_CHAIN = [
    "deepseek/deepseek-r1:free",
    "deepseek/deepseek-chat-v3.1:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "nvidia/llama-3.1-nemotron-70b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.2-11b-vision-instruct:free",
    "mistralai/mistral-nemo:free",
    "meta-llama/llama-3.1-8b-instruct:free",
]

PRIMARY_MODEL = FALLBACK_CHAIN[0]


async def main() -> None:
    async with AsyncSessionLocal() as session:
        repo = CloudProviderRepository(session)
        existing = await session.get(
            __import__("db.models", fromlist=["CloudLLMProvider"]).CloudLLMProvider,
            PROVIDER_ID,
        )

        config = {
            "fallback_models": FALLBACK_CHAIN,
            "temperature": 0.7,
            "max_tokens": 4096,
        }

        if existing:
            preserved_config = existing.get_config() or {}
            preserved_config["fallback_models"] = FALLBACK_CHAIN
            preserved_config.setdefault("temperature", 0.7)
            preserved_config.setdefault("max_tokens", 4096)
            await repo.update_provider(
                PROVIDER_ID,
                model_name=PRIMARY_MODEL,
                config=preserved_config,
            )
            await session.commit()
            print(
                f"  ✓ Updated {PROVIDER_ID} — fallback chain refreshed ({len(FALLBACK_CHAIN)} models)"
            )
            return

        await repo.create_provider(
            name=PROVIDER_NAME,
            provider_type="openrouter",
            api_key=None,  # admin fills via /admin/llm UI
            base_url="https://openrouter.ai/api/v1",
            model_name=PRIMARY_MODEL,
            id=PROVIDER_ID,
            enabled=False,  # disabled until admin pastes API key
            is_default=False,
            description=(
                "Бесплатные мощные модели OpenRouter — fallback после триала Claude. "
                "Цепочка от мощных к слабым: при недоступности первой модели "
                "(rate-limit/402/5xx) бридж автоматически переходит к следующей. "
                "Нужно: вставить API key (https://openrouter.ai/keys) и включить."
            ),
            config=config,
        )
        await session.commit()
        print(
            f"  ✓ Created {PROVIDER_ID} — primary={PRIMARY_MODEL}, "
            f"fallback chain={len(FALLBACK_CHAIN)} models (disabled, нужен API key)"
        )


if __name__ == "__main__":
    asyncio.run(main())
