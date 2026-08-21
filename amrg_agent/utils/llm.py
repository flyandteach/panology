"""
Shared LLM calling helper. Anthropic primary, OpenAI fallback, mock fallback
when no API key is configured (mirrors book_agent's agents/*.py convention).
"""

import os

import config


def call_llm(prompt: str, mock_response: str = "", max_tokens: int = None) -> str:
    """Call the configured LLM. Falls back to a caller-supplied mock string
    if no API key is available or the call fails, so the pipeline can still
    be exercised end-to-end (e.g. in CI, or before secrets are configured)."""
    max_tokens = max_tokens or config.MAX_TOKENS

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model=config.DEFAULT_LLM_MODEL,
                max_tokens=max_tokens,
                temperature=config.TEMPERATURE,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except ImportError:
            pass
        except Exception as e:
            print(f"[LLM warning] Anthropic call failed: {e}. Falling back.")

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except ImportError:
            pass
        except Exception as e:
            print(f"[LLM warning] OpenAI call failed: {e}. Falling back.")

    return mock_response
