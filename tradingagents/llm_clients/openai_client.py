import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

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
        return normalize_content(super().invoke(input, config, **kwargs))

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
        for message_dict, message in zip(outgoing, _input_to_messages(input_), strict=False):
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
            chat_result.generations, response_dict.get("choices", []), strict=False
        ):
            reasoning = choice.get("message", {}).get("reasoning_content")
            if reasoning is not None:
                generation.message.additional_kwargs["reasoning_content"] = reasoning
        return chat_result


class MinimaxChatOpenAI(NormalizedChatOpenAI):
    """MiniMax-specific overrides on top of the OpenAI-compatible client.

    M2.x reasoning models embed ``<think>...</think>`` blocks directly in
    ``message.content`` by default, which would pollute saved reports.
    Per platform.minimax.io/docs/api-reference/text-openai-api,
    ``reasoning_split=True`` redirects the thinking block into
    ``reasoning_details`` so ``content`` stays clean. It is sent via
    ``extra_body`` (not a top-level kwarg) because the openai SDK validates
    top-level params and rejects unknown ones like reasoning_split (#826).

    The flag is gated by ``ModelCapabilities.requires_reasoning_split`` so
    only M2.x reasoning models receive it; non-reasoning MiniMax endpoints
    (Coding Plan, MiniMax-Text-01) never see it.

    Tool-choice handling for M2.x — those models accept only the string
    enum ``{"none", "auto"}`` and reject langchain's function-spec dict —
    is handled by the capability dispatch in
    ``NormalizedChatOpenAI.with_structured_output``, not here.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if get_capabilities(self.model_name).requires_reasoning_split:
            extra_body = payload.setdefault("extra_body", {})
            extra_body.setdefault("reasoning_split", True)
        return payload


# ---------------------------------------------------------------------------
# Backward-compat helpers: base-url and key resolution (public for tests)
# ---------------------------------------------------------------------------

def _resolve_provider_base_url(provider: str) -> str:
    """Resolve the base URL for an OpenAI-compatible provider.

    Order of preference: env var > spec default > SDK default.
    Mirrors the logic in ``OpenAIClient.get_llm``.
    """
    spec = OPENAI_COMPATIBLE_PROVIDERS.get(provider)
    if spec is None:
        return ""
    if spec.base_url_env:
        return os.environ.get(spec.base_url_env) or spec.base_url or ""
    return spec.base_url or ""


def _normalize_ollama_openai_base_url(url: str) -> str:
    """Append ``/v1`` to an Ollama base URL if missing."""
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


def _resolve_ollama_api_key(provider: str) -> str:
    """Resolve the API key for an Ollama provider."""
    env_keys = {"OLLAMA_CF_TOKEN", "OLLAMA_API_KEY"}
    for key in ("OLLAMA_CF_TOKEN", "OLLAMA_API_KEY"):
        val = os.environ.get(key)
        if val:
            return val
    return "ollama"


def _resolve_ollama_headers(provider: str) -> dict[str, str]:
    """Resolve Cloudflare Access headers for remote Ollama."""
    headers = {}
    if "remote" not in provider:
        return headers
    token = os.environ.get("OLLAMA_CF_TOKEN")
    if token:
        headers["CF-Access-Token"] = token
    for hdr, env in [("CF-Access-Client-Id", "OLLAMA_CF_CLIENT_ID"),
                     ("CF-Access-Client-Secret", "OLLAMA_CF_CLIENT_SECRET")]:
        val = os.environ.get(env)
        if val:
            headers[hdr] = val
    return headers


# Kwargs forwarded from user config to ChatOpenAI
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort", "temperature",
    "api_key", "callbacks", "http_client", "http_async_client",
)


class _PreferJsonSchemaMixin:
    """Mixin for providers whose structured output 404s under function_calling.

    OpenRouter and NVIDIA NIM both prefer ``json_schema`` (or ``json_mode``)
    over ``function_calling`` because their API gateways 404 on the
    auto-generated function binding.
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


class NvidiaChatOpenAI(_PreferJsonSchemaMixin, NormalizedChatOpenAI):
    """NVIDIA NIM — prefers JSON-schema structured output over tool calling."""


class OpenRouterChatOpenAI(_PreferJsonSchemaMixin, NormalizedChatOpenAI):
    """OpenRouter — prefers JSON-schema structured output over tool calling."""


@dataclass(frozen=True)
class ProviderSpec:
    """Declarative config for one OpenAI-compatible provider.

    The OpenAI-compatible family (OpenAI, xAI, DeepSeek, Qwen, GLM, MiniMax,
    OpenRouter, Ollama, and any user endpoint) all speak the same Chat
    Completions API and differ only by these fields — so one row here replaces
    the former per-provider base-URL dict, auth handling, and client-class
    branches. Native Anthropic / Google use their own clients (genuinely
    different APIs) and are intentionally NOT in this registry.

    The API-key env var stays in ``api_key_env.PROVIDER_API_KEY_ENV`` (the single
    source consulted by both this client and the CLI prompt); only behavior that
    is provider-specific (base URL, key optionality, wire-format quirks via
    ``chat_class``) lives here.
    """

    chat_class: type = NormalizedChatOpenAI   # provider quirks live in the subclass
    base_url: str | None = None            # default endpoint (None -> SDK default)
    base_url_env: str | None = None        # env var that overrides base_url (e.g. OLLAMA_BASE_URL)
    key_optional: bool = False             # don't require/prompt; send a placeholder if unset
    placeholder_key: str = "EMPTY"         # sent when no key is available (keyless local servers)
    require_base_url: bool = False         # error if no base_url is resolved (generic endpoint)
    use_responses_api: bool = False        # native OpenAI Responses API


# Single source of truth for the OpenAI-compatible provider family. Dual-region
# providers (qwen/glm/minimax) keep separate endpoints because international and
# China accounts cannot share credentials (#758).
OPENAI_COMPATIBLE_PROVIDERS: dict[str, ProviderSpec] = {
    "openai":     ProviderSpec(use_responses_api=True),
    "xai":        ProviderSpec(base_url="https://api.x.ai/v1"),
    "deepseek":   ProviderSpec(base_url="https://api.deepseek.com", chat_class=DeepSeekChatOpenAI),
    "qwen":       ProviderSpec(base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    "qwen-cn":    ProviderSpec(base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"),
    "glm":        ProviderSpec(base_url="https://api.z.ai/api/paas/v4/"),
    "glm-cn":     ProviderSpec(base_url="https://open.bigmodel.cn/api/paas/v4/"),
    "minimax":    ProviderSpec(base_url="https://api.minimax.io/v1", chat_class=MinimaxChatOpenAI),
    "minimax-cn": ProviderSpec(base_url="https://api.minimaxi.com/v1", chat_class=MinimaxChatOpenAI),
    "openrouter": ProviderSpec(base_url="https://openrouter.ai/api/v1", chat_class=OpenRouterChatOpenAI),
    "mistral":    ProviderSpec(base_url="https://api.mistral.ai/v1"),
    # Moonshot's OpenAI-compatible endpoint is branded as Kimi; accept both names.
    "kimi":       ProviderSpec(base_url="https://api.moonshot.ai/v1"),
    "moonshot":   ProviderSpec(base_url="https://api.moonshot.ai/v1"),
    "groq":       ProviderSpec(base_url="https://api.groq.com/openai/v1"),
    "nvidia":     ProviderSpec(base_url="https://integrate.api.nvidia.com/v1", chat_class=NvidiaChatOpenAI),
    "ollama":     ProviderSpec(base_url="http://localhost:11434/v1", base_url_env="OLLAMA_BASE_URL",
                               key_optional=True, placeholder_key="ollama"),
    # Generic endpoint: user supplies base_url; key optional (keyless local).
    "openai_compatible": ProviderSpec(require_base_url=True, key_optional=True),
}


def is_openai_compatible(provider: str) -> bool:
    """True if ``provider`` is registered in the OpenAI-compatible family.

    Native Anthropic / Google use their own clients; everything else in the
    registry speaks Chat Completions. This is the single source of truth
    consumed by the factory and any downstream code that needs to know
    whether a provider is OpenAI-compatible.
    """
    return provider.lower() in OPENAI_COMPATIBLE_PROVIDERS


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI, Ollama, OpenRouter, and all OpenAI-compatible providers.

    Uses the ``OPENAI_COMPATIBLE_PROVIDERS`` registry as the single source of
    truth for base URLs, auth rules, and provider-specific wire-format
    subclasses. A new provider is added with one row in the registry — no
    branch in this class required.
    """

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance."""
        spec = OPENAI_COMPATIBLE_PROVIDERS.get(self.provider)
        if spec is None:
            raise ValueError(f"Unknown OpenAI-compatible provider: {self.provider}")

        llm_kwargs: dict[str, Any] = {"model": self.model}

        # Resolve base URL: explicit URL > env-var override > provider default.
        if self.base_url:
            llm_kwargs["base_url"] = self.base_url
        elif spec.base_url_env:
            llm_kwargs["base_url"] = (
                os.environ.get(spec.base_url_env) or spec.base_url
            )
        elif spec.base_url:
            llm_kwargs["base_url"] = spec.base_url
        elif spec.require_base_url:
            raise ValueError(
                f"Provider '{self.provider}' requires a base_url; set "
                f"``backend_url`` in config or the "
                f"``TRADINGAGENTS_LLM_BACKEND_URL`` env var."
            )

        has_custom_endpoint = bool(llm_kwargs.get("base_url"))

        # Only check the official model catalog when we are talking to the
        # provider's default endpoint. Custom/OpenAI-compatible proxies (e.g.
        # a local LiteLLM gateway) can host arbitrary model names like
        # ``kimi-k2.6`` without triggering a warning.
        if not has_custom_endpoint:
            self.warn_if_unknown_model()

        # Resolve API key or placeholder. Custom endpoints are often keyless,
        # so fall back to the provider's placeholder when no key is available.
        if spec.key_optional:
            api_key_env = get_api_key_env(self.provider)
            llm_kwargs["api_key"] = (
                os.environ.get(api_key_env) if api_key_env else None
            ) or spec.placeholder_key
        else:
            api_key_env = get_api_key_env(self.provider)
            api_key = os.environ.get(api_key_env) if api_key_env else None
            if api_key:
                llm_kwargs["api_key"] = api_key
            elif has_custom_endpoint:
                llm_kwargs["api_key"] = spec.placeholder_key
            else:
                raise ValueError(
                    f"API key for provider '{self.provider}' is not set. "
                    f"Please set the {api_key_env} environment variable "
                    f"(e.g. add {api_key_env}=your_key to your .env file)."
                )

        # Forward user-provided kwargs
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return spec.chat_class(**llm_kwargs)

    def validate_model(self) -> bool:
        return validate_model(self.provider, self.model)
