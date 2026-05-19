"""Graph node labels for analyst ids (supports snake_case ids like hot_money)."""


def analyst_title_words(analyst_id: str) -> str:
    """Title-case segment after underscores (e.g. hot_money -> Hot Money)."""
    return " ".join(part.capitalize() for part in analyst_id.split("_"))


def analyst_graph_analyst_node_name(analyst_id: str) -> str:
    """LangGraph node name for the analyst agent (e.g. Hot Money Analyst)."""
    return f"{analyst_title_words(analyst_id)} Analyst"


def analyst_msg_clear_node_name(analyst_id: str) -> str:
    """LangGraph node name for the message-clear step after an analyst."""
    return f"Msg Clear {analyst_title_words(analyst_id)}"
