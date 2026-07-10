"""
Reasoning Agent — generates plain-English narrative from Signal Engine output.

Uses NVIDIA NIM (OpenAI-compatible endpoint) per NIM_REFERENCE.md.
The LLM receives ONLY the structured signal output — never raw spreadsheet
data. It explains the scores but cannot override them.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

from src.models import SignalResult

logger = logging.getLogger(__name__)

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
NIM_MODELS = [
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.3-70b-instruct",
    "meta/llama-3.1-70b-instruct",
]


def _build_prompt(signal: SignalResult, project_name: str) -> tuple[str, str]:
    """Build the system + user prompt for the Reasoning Agent.

    The prompt gives the LLM the structured signal output and asks it to
    write a concise paragraph explaining the scores, citing specific evidence.
    """
    signal_data = signal.model_dump()

    system = (
        "You are a project health analyst. You receive structured RAG signal "
        "data computed by a deterministic engine, and your job is to write a "
        "concise plain-English paragraph explaining the health status. Rules:\n"
        "1. You CANNOT override the computed RAG colors — only explain them.\n"
        "2. You MUST cite specific task names and numbers from the evidence list.\n"
        "3. If any dimension is 'Not Assessed', explicitly state why.\n"
        "4. If there is a disagreement between computed and source-reported status, "
        "explain the contradiction clearly.\n"
        "5. Keep it to 3-5 sentences. Be direct, not hedging."
    )

    user = (
        f"Project: {project_name}\n\n"
        f"Signal data:\n{json.dumps(signal_data, indent=2)}\n\n"
        "Write a concise paragraph explaining this project's health status. "
        "Cite specific evidence. If the disagreement_flag is true, lead with that."
    )

    return system, user


def generate_reasoning(
    signal: SignalResult,
    project_name: str,
    api_key: Optional[str] = None,
) -> str:
    """Call NIM to generate a plain-English reasoning narrative with fallback models.

    Args:
        signal: The SignalResult from the Signal Engine.
        project_name: Human-readable project name for context.
        api_key: NVIDIA NIM API key. If None, reads from NVIDIA_API_KEY env var.
    """
    key = api_key or os.environ.get("NVIDIA_API_KEY")
    if not key:
        msg = (
            "LLM reasoning unavailable — NVIDIA_API_KEY not set. "
            "Signal data above is the authoritative output. "
            "Set NVIDIA_API_KEY environment variable with your nvapi- key "
            "from build.nvidia.com to enable AI-generated narratives."
        )
        logger.warning(msg)
        signal.data_gaps.append("Reasoning Agent: NVIDIA_API_KEY not configured")
        return msg

    system_prompt, user_prompt = _build_prompt(signal, project_name)

    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=NIM_BASE_URL,
            api_key=key,
            max_retries=0,
        )

        max_retries = 3
        last_error = None

        for model_name in NIM_MODELS:
            logger.info("Attempting reasoning generation with model: %s", model_name)
            for attempt in range(max_retries):
                try:
                    model_timeout = 45.0
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.3,
                        max_tokens=2000,
                        timeout=model_timeout,
                    )
                    reasoning = response.choices[0].message.content
                    if reasoning:
                        return reasoning.strip()
                    else:
                        msg = "LLM returned empty response — signal data is authoritative"
                        signal.data_gaps.append(f"Reasoning Agent ({model_name}): empty response")
                        return msg

                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    
                    # If model is deprecated or unauthorized, immediately skip to next model
                    if any(term in error_str for term in ["not found", "404", "unauthorized", "invalid model"]):
                        logger.warning("Model %s unavailable. Trying fallback.", model_name)
                        break

                    # Retry transient network issues ONLY for the 8B model to avoid wasting time on queued 70B models
                    is_transient = any(term in error_str for term in ["429", "timed out", "timeout", "rate limit", "connection"])
                    if is_transient and attempt < max_retries - 1 and "8b" in model_name:
                        wait = 2 ** (attempt + 1)
                        logger.warning(
                            "NIM error on %s, retrying in %ds (attempt %d/%d): %s",
                            model_name, wait, attempt + 1, max_retries, e
                        )
                        time.sleep(wait)
                        continue
                    
                    logger.warning("Model %s failed: %s. Trying next model.", model_name, e)
                    break
        
        # If all models failed
        raise last_error if last_error else Exception("All fallback models failed")

    except Exception as e:
        msg = (
            f"LLM reasoning unavailable — NIM call failed: {e}. "
            "Signal data above is the authoritative output."
        )
        logger.error("Reasoning Agent NIM call failed: %s", e)
        signal.data_gaps.append(f"Reasoning Agent: NIM call failed ({e})")
        return msg
    return "LLM reasoning unavailable — exceeded retries."
