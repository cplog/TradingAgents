"""Semantic convergence checker for debate termination.

When ``semantic_debate_termination`` is enabled, the checker uses a lightweight
LLM call to detect whether debate participants have converged to the same
core conclusion or are repeating points without adding new information. If
convergence is detected, the debate exits early (before the count-based ceiling
is reached), saving 1–2 LLM calls per run.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Truncate individual responses so the convergence prompt stays small.
_MAX_RESPONSE_LEN = 800


class ConvergenceChecker:
    """Check whether a debate has converged using a lightweight LLM prompt."""

    def __init__(self, llm: Any, enabled: bool = False):
        self.llm = llm
        self.enabled = enabled

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_bull_bear(self, state: dict) -> bool:
        """Return True if the bull/bear debate has converged.

        Checks only after a full round (count is even and >= 2) to minimize
        LLM calls.
        """
        if not self.enabled:
            return False

        debate = state.get("investment_debate_state") or {}
        count = debate.get("count", 0)

        # Only check after a full round (Bull + Bear both spoke).
        if count < 2 or count % 2 != 0:
            return False

        last_bull = self._last_entry(debate.get("bull_history", ""))
        last_bear = self._last_entry(debate.get("bear_history", ""))

        if not last_bull or not last_bear:
            return False

        return self._ask_yes_no(
            question=(
                "Have these two debate participants converged to the same core "
                "conclusion, or are they still fundamentally disagreeing?"
            ),
            a_label="Bull",
            a_text=last_bull,
            b_label="Bear",
            b_text=last_bear,
        )

    def check_risk(self, state: dict) -> bool:
        """Return True if the risk-team debate has converged.

        Checks only after a full round (count is a multiple of 3 and >= 3).
        """
        if not self.enabled:
            return False

        debate = state.get("risk_debate_state") or {}
        count = debate.get("count", 0)

        # Only check after a full round (Aggressive + Conservative + Neutral).
        if count < 3 or count % 3 != 0:
            return False

        agg = debate.get("current_aggressive_response", "")
        cons = debate.get("current_conservative_response", "")
        neut = debate.get("current_neutral_response", "")

        if not agg or not cons or not neut:
            return False

        return self._ask_yes_no_three_way(
            agg=agg[:_MAX_RESPONSE_LEN],
            cons=cons[:_MAX_RESPONSE_LEN],
            neut=neut[:_MAX_RESPONSE_LEN],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _last_entry(history: str) -> str:
        """Return the last non-empty line from a multi-line history."""
        lines = [ln.strip() for ln in history.splitlines() if ln.strip()]
        return lines[-1][:_MAX_RESPONSE_LEN] if lines else ""

    def _ask_yes_no(
        self,
        question: str,
        a_label: str,
        a_text: str,
        b_label: str,
        b_text: str,
    ) -> bool:
        """Pose a yes/no convergence question to the LLM."""
        prompt = (
            f"{question}\n\n"
            f"{a_label} (last argument): {a_text}\n\n"
            f"{b_label} (last argument): {b_text}\n\n"
            "Answer YES if they agree on the core conclusion or are repeating "
            "the same points without new evidence. "
            "Answer NO if they still fundamentally disagree. "
            "One word only: YES or NO."
        )
        return self._invoke(prompt)

    def _ask_yes_no_three_way(self, agg: str, cons: str, neut: str) -> bool:
        prompt = (
            "Have these three risk analysts converged to the same core "
            "conclusion about the trade?\n\n"
            f"Aggressive: {agg}\n\n"
            f"Conservative: {cons}\n\n"
            f"Neutral: {neut}\n\n"
            "Answer YES if all three agree on the core verdict (e.g., all approve "
            "or all reject), or if they are repeating the same points. "
            "Answer NO if there is still meaningful disagreement. "
            "One word only: YES or NO."
        )
        return self._invoke(prompt)

    def _invoke(self, prompt: str) -> bool:
        try:
            response = self.llm.invoke(prompt)
            text = getattr(response, "content", str(response))
            converged = "YES" in text.upper()
            if converged:
                logger.info("ConvergenceChecker: detected convergence, ending debate early.")
            return converged
        except Exception as exc:
            logger.warning("ConvergenceChecker: LLM call failed (%s), continuing debate.", exc)
            return False
