"""Analyst skills — loadable prompt instructions for TradingAgents analysts.

Each analyst has a subdirectory containing a ``SKILL.md`` file with its
system-prompt instructions.  The ``load_skill()`` helper strips YAML
frontmatter (if present) and returns the markdown body.

Example::

    from tradingagents.agents.skills import load_skill

    system_message = load_skill("market_analyst") + get_language_instruction()
"""

import re
from pathlib import Path

# Path to this package directory (works for editable and installed installs)
_SKILLS_DIR = Path(__file__).parent.resolve()

# Simple frontmatter parser: ---\nkey: value\n---\ncontent...
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


def load_skill(name: str) -> str:
    """Load the markdown body of an analyst skill.

    Args:
        name: Skill directory name, e.g. ``"market_analyst"``.

    Returns:
        The skill content with frontmatter stripped.

    Raises:
        FileNotFoundError: If ``{name}/SKILL.md`` does not exist.
    """
    path = _SKILLS_DIR / name / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if match:
        return match.group(2).strip()
    return text.strip()
