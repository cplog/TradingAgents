"""Amazon Bedrock LLM client.

Requires ``pip install "tradingagents[bedrock]"`` (installs
``langchain-aws``) and configured AWS credentials (env vars,
``~/.aws/credentials``, or an IAM role).

Use e.g. ``us.anthropic.claude-opus-4-8-v1:0`` as the model ID.
"""

from __future__ import annotations

import logging
from typing import Any

from .base_client import BaseLLMClient, normalize_content

logger = logging.getLogger(__name__)


class BedrockClient(BaseLLMClient):
    """Client for Amazon Bedrock Converse API.

    Uses ``langchain_aws.chat_models.ChatBedrockConverse`` which wraps the
    Bedrock Converse API and supports structured output via
    ``with_structured_output``.
    """

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatBedrockConverse instance."""
        self.warn_if_unknown_model()
        try:
            from langchain_aws import ChatBedrockConverse
        except ImportError:
            raise ImportError(
                "Bedrock support requires the 'bedrock' extra. "
                "Install it with: pip install 'tradingagents[bedrock]'"
            )

        llm_kwargs: dict[str, Any] = {
            "model": self.model,
        }

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in ("temperature", "max_retries", "callbacks"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return ChatBedrockConverse(**llm_kwargs)

    def validate_model(self) -> bool:
        return True  # Bedrock model IDs are user-defined deployment names
