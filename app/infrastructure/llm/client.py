"""AnthropicInterpreter: LLM interpretation of completed deterministic
results. Fails explicitly (MissingApiKeyError) before any network call when
no API key is configured — deterministic results are always retained."""

import logging
import os
from typing import Any

from app.config.settings import Settings, get_settings
from app.domain.entities import (
    EconomicChange,
    LLMInterpretation,
    MetricDelta,
    TaxCalculatorResult,
    TaxFairAdapterResult,
)
from app.domain.errors import LLMInterpretationError, MissingApiKeyError
from app.infrastructure.llm.prompts import PROMPT_VERSION, SYSTEM_V1, render_user_prompt

logger = logging.getLogger(__name__)


class AnthropicInterpreter:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def interpret(
        self,
        change: EconomicChange,
        deltas: list[MetricDelta],
        tax_result: TaxCalculatorResult | None,
        adapter_result: TaxFairAdapterResult | None,
        context: dict[str, Any],
    ) -> LLMInterpretation:
        if not deltas:
            raise LLMInterpretationError(
                "No metric deltas provided; interpretation runs only after "
                "deterministic results exist"
            )
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise MissingApiKeyError()

        prompt = render_user_prompt(change, deltas, tax_result, adapter_result, context)
        try:
            import anthropic

            client = anthropic.Anthropic()
            response = client.messages.create(
                model=self.settings.llm_model,
                max_tokens=self.settings.llm_max_tokens,
                system=SYSTEM_V1,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise LLMInterpretationError(f"Anthropic API call failed: {exc}") from exc

        text_parts = [b.text for b in response.content if getattr(b, "type", "") == "text"]
        text = "\n".join(text_parts).strip()
        if not text or getattr(response, "stop_reason", None) == "refusal":
            raise LLMInterpretationError(
                f"LLM returned no usable interpretation (stop_reason="
                f"{getattr(response, 'stop_reason', None)!r})"
            )
        usage = getattr(response, "usage", None)
        return LLMInterpretation(
            model_id=response.model,
            prompt_version=PROMPT_VERSION,
            prompt_text=prompt,
            response_text=text,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            stop_reason=getattr(response, "stop_reason", None),
        )
