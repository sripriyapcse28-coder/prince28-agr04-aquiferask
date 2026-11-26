"""Check connectivity to the configured LLM providers."""

import time

import httpx

from aquiferask.config import get_settings


def ping_provider(client, name, api_key, base_url, model):
    if not api_key:
        print(f"{name:<8} SKIPPED  API key not configured")
        return

    url = f"{base_url.rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with pong"}],
        "max_tokens": 256,
    }

    start = time.perf_counter()

    try:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        elapsed = int((time.perf_counter() - start) * 1000)
        result = response.json()

        message = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})

        print(
            f"{name:<8} OK       {model} said "
            f"'{message}' in {elapsed} ms, "
            f"tokens in={usage.get('prompt_tokens', 0)} "
            f"out={usage.get('completion_tokens', 0)}"
        )

    except httpx.HTTPStatusError as error:
        print(f"{name:<8} FAILED   HTTP {error.response.status_code}")
        print(error.response.text[:500])

    except (httpx.HTTPError, KeyError, IndexError, ValueError) as error:
        print(f"{name:<8} FAILED   {type(error).__name__}: {error}")


def main():
    settings = get_settings()

    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        ping_provider(
            client,
            "gemini",
            settings.gemini_api_key,
            settings.llm_primary_base_url,
            settings.llm_primary_model,
        )

        ping_provider(
            client,
            "groq",
            settings.groq_api_key,
            settings.llm_fallback_base_url,
            settings.llm_fallback_model,
        )


if __name__ == "__main__":
    main()
