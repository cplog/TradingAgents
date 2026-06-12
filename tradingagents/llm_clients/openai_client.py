import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Error patterns from OpenAI Responses API when it auto-detects image-like
# strings in text content and the model does not support vision.
_RESPONSES_IMAGE_ERROR_RE = re.compile(
    r"does not support image|image\.png|image_url"
)

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from .api_key_env import get_api_key_env
from .base_client import BaseLLMClient, normalize_content
from .capabilities import get_capabilities
from .validators import validate_model


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with normalized content output and capability-aware binding.

    The Responses API returns content as a list of typed blocks
    (reasoning, text, etc.). ``invoke`` normalizes to string for
    consistent downstream handling.

    ``with_structured_output`` consults the per-model capability table
    (``capabilities.get_capabilities``) to pick the method and to decide
    whether ``tool_choice`` may be sent. Models that reject ``tool_choice``
    (e.g. DeepSeek V4 and reasoner — per their official tool-calling
    guide) still bind the schema as a tool, but no ``tool_choice``
    parameter is sent.

    Provider-specific quirks beyond structured-output (e.g. DeepSeek's
    reasoning_content roundtrip) live in subclasses so this base class
    stays small.
    """

    def invoke(self, input, config=None, **kwargs):
        if not self.use_responses_api:
            return normalize_content(super().invoke(input, config, **kwargs))
        try:
            return normalize_content(super().invoke(input, config, **kwargs))
        except Exception as exc:
            err_str = str(exc).lower()
            if _RESPONSES_IMAGE_ERROR_RE.search(err_str):
                logger.warning(
                    "Responses API rejected content as image input (%s); "
                    "retrying with Chat Completions on this call "
                    "and disabling Responses API for subsequent requests",
                    exc,
                )
                self.use_responses_api = False
                return normalize_content(super().invoke(input, config, **kwargs))
            raise

    def with_structured_output(self, schema, *, method=None, **kwargs):
        caps = get_capabilities(self.model_name)
        if caps.preferred_structured_method == "none":
            raise NotImplementedError(
                f"{self.model_name} has no structured-output method available; "
                f"agent factories will fall back to free-text generation."
            )
        method = method or caps.preferred_structured_method
        # When the model rejects tool_choice, suppress langchain's hardcoded
        # value. The schema is still bound as a tool — exactly what
        # DeepSeek's official tool-calling examples do.
        if method == "function_calling" and not caps.supports_tool_choice:
            kwargs.setdefault("tool_choice", None)
        return super().with_structured_output(schema, method=method, **kwargs)


def _input_to_messages(input_: Any) -> list:
    """Normalise a langchain LLM input to a list of message objects.

    Accepts a list of messages, a ``ChatPromptValue`` (from a
    ChatPromptTemplate), or anything else (treated as no messages).
    Used by providers that need to walk the outgoing message history;
    in particular DeepSeek thinking-mode propagation must work for
    both bare-list invocations and ChatPromptTemplate-driven ones, so
    treating only ``list`` here would silently skip half the call sites.
    """
    if isinstance(input_, list):
        return input_
    if hasattr(input_, "to_messages"):
        return input_.to_messages()
    return []


class DeepSeekChatOpenAI(NormalizedChatOpenAI):
    """DeepSeek-specific overrides on top of the OpenAI-compatible client.

    Thinking-mode round-trip is the only DeepSeek-specific behavior that
    stays here. When DeepSeek's thinking models return a response with
    ``reasoning_content``, that field must be echoed back as part of the
    assistant message on the next turn or the API fails with HTTP 400.
    ``_create_chat_result`` captures it on receive and
    ``_get_request_payload`` re-attaches it on send.

    Tool-choice handling for V4 and reasoner — those models reject the
    ``tool_choice`` parameter — is handled by the capability dispatch in
    ``NormalizedChatOpenAI.with_structured_output``, not here.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        outgoing = payload.get("messages", [])
        for message_dict, message in zip(outgoing, _input_to_messages(input_)):
            if not isinstance(message, AIMessage):
                continue
            reasoning = message.additional_kwargs.get("reasoning_content")
            if reasoning is not None:
                message_dict["reasoning_content"] = reasoning
        return payload

    def _create_chat_result(self, response, generation_info=None):
        chat_result = super()._create_chat_result(response, generation_info)
        response_dict = (
            response
            if isinstance(response, dict)
            else response.model_dump(
                exclude={"choices": {"__all__": {"message": {"parsed"}}}}
            )
        )
        for generation, choice in zip(
            chat_result.generations, response_dict.get("choices", [])
        ):
            reasoning = choice.get("message", {}).get("reasoning_content")
            if reasoning is not None:
                generation.message.additional_kwargs["reasoning_content"] = reasoning
        return chat_result


class MinimaxChatOpenAI(NormalizedChatOpenAI):
    """MiniMax-specific overrides on top of the OpenAI-compatible client.

    M2.x reasoning models embed ``<think>...</think>`` blocks directly in
    ``message.content`` by default, which would pollute saved reports.
    Per platform.minimax.io/docs/api-reference/text-openai-api, setting
    ``reasoning_split=True`` in the request body redirects the thinking
    block into ``reasoning_details`` so ``content`` stays clean.

    Tool-choice handling for M2.x — those models accept only the string
    enum ``{"none", "auto"}`` and reject langchain's function-spec dict —
    is handled by the capability dispatch in
    ``NormalizedChatOpenAI.with_structured_output``, not here.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        payload.setdefault("reasoning_split", True)
        return payload


class OpenRouterChatOpenAI(NormalizedChatOpenAI):
    """OpenRouter-compatible structured output without relying on tool routing.

    Many OpenRouter model routes return HTTP 404 with *No endpoints found that
    support tool use* when LangChain uses ``method=function_calling``. Preferring
    ``json_schema`` (then ``json_mode``) maps to OpenAI-style ``response_format``
    instead of binding the schema as an API tool.
    """

    def with_structured_output(self, schema, *, method=None, **kwargs):
        caps = get_capabilities(self.model_name)
        if caps.preferred_structured_method == "none":
            raise NotImplementedError(
                f"{self.model_name} has no structured-output method available; "
                f"agent factories will fall back to free-text generation."
            )
        if method is None:
            if caps.supports_json_schema:
                method = "json_schema"
            elif caps.supports_json_mode:
                method = "json_mode"
            else:
                method = caps.preferred_structured_method
        if method == "function_calling" and not caps.supports_tool_choice:
            kwargs.setdefault("tool_choice", None)
        return ChatOpenAI.with_structured_output(self, schema, method=method, **kwargs)


class NvidiaChatOpenAI(NormalizedChatOpenAI):
    """NVIDIA NIM-compatible structured output without relying on tool routing.

    NVIDIA's OpenAI-compatible API (integrate.api.nvidia.com) returns HTTP 404
    from Cloudflare when LangChain uses ``method=function_calling`` because the
    gateway cannot locate the auto-generated function binding. Preferring
    ``json_schema`` (then ``json_mode``) uses ``response_format`` instead of
    binding the schema as an API tool, which NIM handles correctly.
    """

    def with_structured_output(self, schema, *, method=None, **kwargs):
        caps = get_capabilities(self.model_name)
        if caps.preferred_structured_method == "none":
            raise NotImplementedError(
                f"{self.model_name} has no structured-output method available; "
                f"agent factories will fall back to free-text generation."
            )
        if method is None:
            if caps.supports_json_schema:
                method = "json_schema"
            elif caps.supports_json_mode:
                method = "json_mode"
            else:
                method = caps.preferred_structured_method
        if method == "function_calling" and not caps.supports_tool_choice:
            kwargs.setdefault("tool_choice", None)
        return ChatOpenAI.with_structured_output(self, schema, method=method, **kwargs)


# Kwargs forwarded from user config to ChatOpenAI
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort", "temperature",
    "api_key", "callbacks", "http_client", "http_async_client",
)

# Provider base URLs. API-key env vars live in api_key_env.PROVIDER_API_KEY_ENV
# (one canonical mapping consulted by both this client and the CLI's
# interactive key-prompt). Dual-region providers (qwen/glm/minimax) keep
# separate endpoints because international and China accounts cannot share
# credentials (#758).
_PROVIDER_BASE_URL = {
    "xai":        "https://api.x.ai/v1",
    "deepseek":   "https://api.deepseek.com",
    "qwen":       "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "qwen-cn":    "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "glm":        "https://api.z.ai/api/paas/v4/",
    "glm-cn":     "https://open.bigmodel.cn/api/paas/v4/",
    "minimax":    "https://api.minimax.io/v1",
    "minimax-cn": "https://api.minimaxi.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "nvidia":     "https://integrate.api.nvidia.com/v1",
    "ollama":     "http://localhost:11434/v1",
    "ollama-local": "http://localhost:11434/v1",
    "ollama-remote": "http://localhost:11434/v1",
}


def _resolve_provider_base_url(provider: str) -> Optional[str]:
    """Default base URL for ``provider``, with env-var overrides where defined.

    Currently only Ollama supports env-var overrides. Resolution order:
    1) ``OLLAMA_BASE_URL`` (existing convention)
    2) ``OLLAMA_CF_URL`` (Cloudflare tunnel/front-door alias)

    This keeps backward compatibility while allowing users to keep Cloudflare
    endpoint vars grouped as ``OLLAMA_CF_*``. The check is call-time, not
    import-time, so tests that monkeypatch env after import behave correctly.
    """
    if provider == "ollama-local":
        env_url = os.environ.get("OLLAMA_BASE_URL")
        if env_url:
            return env_url
    elif provider == "ollama-remote":
        env_url = os.environ.get("OLLAMA_CF_URL") or os.environ.get("OLLAMA_BASE_URL")
        if env_url:
            return env_url
    elif provider == "ollama":
        env_url = os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_CF_URL")
        if env_url:
            return env_url
    return _PROVIDER_BASE_URL.get(provider)


def _normalize_ollama_openai_base_url(raw: Optional[str]) -> Optional[str]:
    """Ensure Ollama OpenAI-compatible base URL ends with /v1."""
    if not raw:
        return raw
    base = raw.rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def _resolve_ollama_api_key(provider: str) -> str:
    """Resolve auth token for Ollama-compatible endpoints.

    Local ``ollama-serve`` does not require auth, so ``"ollama"`` remains the
    fallback sentinel token. For remote front-doors (Cloudflare Tunnel, API
    gateway), allow users to supply:
    - ``OLLAMA_CF_TOKEN`` (preferred for Cloudflare naming consistency)
    - ``OLLAMA_API_KEY`` (generic alias)
    """
    if provider == "ollama-local":
        return os.environ.get("OLLAMA_API_KEY") or "ollama"
    return os.environ.get("OLLAMA_CF_TOKEN") or os.environ.get("OLLAMA_API_KEY") or "ollama"


def _resolve_ollama_headers(provider: str) -> dict[str, str]:
    """Return optional extra headers for Ollama front-doors."""
    if provider != "ollama-remote":
        return {}

    headers: dict[str, str] = {}
    access_token = os.environ.get("OLLAMA_CF_TOKEN", "").strip()
    client_id = os.environ.get("OLLAMA_CF_CLIENT_ID", "").strip()
    client_secret = os.environ.get("OLLAMA_CF_CLIENT_SECRET", "").strip()
    if access_token:
        headers["CF-Access-Token"] = access_token
    if client_id and client_secret:
        headers["CF-Access-Client-Id"] = client_id
        headers["CF-Access-Client-Secret"] = client_secret
    return headers
class OpenAIClient(BaseLLMClient):
    """Client for OpenAI, Ollama, OpenRouter, and xAI providers.

    Uses standard Chat Completions for all providers.  The Responses API
    (/v1/responses) is deliberately not enabled because its auto-detection
    of .png strings in tool outputs as image input breaks on non-vision
    models.  Chat Completions supports ``reasoning_effort`` with function
    tools across all current OpenAI model families (GPT-4.1, GPT-5, o-series),
    so there is no capability gap from using Chat Completions.
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        # Provider-specific base URL and auth. An explicit base_url on the
        # client (e.g. a corporate proxy) takes precedence over the
        # provider default so users can route through their own gateway.
        if self.provider in _PROVIDER_BASE_URL:
            llm_kwargs["base_url"] = self.base_url or _resolve_provider_base_url(self.provider)
            if self.provider in ("ollama", "ollama-local", "ollama-remote"):
                llm_kwargs["base_url"] = _normalize_ollama_openai_base_url(llm_kwargs["base_url"])
            api_key_env = get_api_key_env(self.provider)
            if api_key_env:
                api_key = os.environ.get(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
                else:
                    raise ValueError(
                        f"API key for provider '{self.provider}' is not set. "
                        f"Please set the {api_key_env} environment variable "
                        f"(e.g. add {api_key_env}=your_key to your .env file)."
                    )
            else:
                llm_kwargs["api_key"] = _resolve_ollama_api_key(self.provider)
                extra_headers = _resolve_ollama_headers(self.provider)
                if extra_headers:
                    llm_kwargs["default_headers"] = extra_headers
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url

        # Ollama (especially behind Cloudflare) needs a client-side timeout
        # that stays under the proxy's hard ceiling (Cloudflare = 120 s).
        # 90 s gives headroom for network jitter while still triggering
        # LangChain retries before the connection is dropped.
        if self.provider in ("ollama", "ollama-local", "ollama-remote"):
            llm_kwargs.setdefault("timeout", 90)

        # Forward user-provided kwargs
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # Native OpenAI: leave use_responses_api as None (default) so
        # Chat Completions is used. The Responses API is not required:
        # Chat Completions supports reasoning_effort with function tools
        # across all current model families (GPT-4.1, GPT-5, o-series),
        # and avoids the Responses API's auto-detection of .png strings
        # as image input (which breaks on non-vision models).

        # Provider-specific quirks live in their own subclasses so the
        # base NormalizedChatOpenAI stays free of provider branches.
        if self.provider == "deepseek":
            chat_cls = DeepSeekChatOpenAI
        elif self.provider in ("minimax", "minimax-cn"):
            chat_cls = MinimaxChatOpenAI
        elif self.provider == "openrouter":
            chat_cls = OpenRouterChatOpenAI
        elif self.provider == "nvidia":
            chat_cls = NvidiaChatOpenAI
        else:
            chat_cls = NormalizedChatOpenAI
        return chat_cls(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for the provider."""
        return validate_model(self.provider, self.model)
