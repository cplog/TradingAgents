"""Analyst tool chains fall back when NVIDIA NIM rejects tool binding."""

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.utils.agent_utils import (
    _tool_routing_rejected,
    invoke_tool_chain_with_openrouter_fallback,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "message",
    [
        "No endpoints found that support tool use",
        (
            "Error code: 404 - {'detail': "
            "\"Function 'ffd13b18-1c55-4a7a-b71a-acbfde9ce8a0': "
            "Not found for account 'ah9_gNLM'\"}"
        ),
    ],
)
def test_tool_routing_rejected(message):
    assert _tool_routing_rejected(RuntimeError(message))


@pytest.mark.unit
def test_nvidia_tool_chain_falls_back_without_tools(monkeypatch):
    chain = MagicMock()
    llm = MagicMock()
    fallback_msg = MagicMock()
    llm.invoke.return_value = fallback_msg
    chain.invoke.side_effect = RuntimeError(
        "Error code: 404 - Function 'ffd13b18-1c55-4a7a-b71a-acbfde9ce8a0': Not found"
    )

    monkeypatch.setattr(
        "tradingagents.dataflows.config.get_config",
        lambda: {"llm_provider": "nvidia"},
    )

    result = invoke_tool_chain_with_openrouter_fallback(chain, llm, [])
    assert result is fallback_msg
    llm.invoke.assert_called_once()
    chain.invoke.assert_called_once()
