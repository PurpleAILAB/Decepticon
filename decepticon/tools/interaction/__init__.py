"""Operator-interaction tools — agent-driven CLI prompts.

Tools in this package pause graph execution and surface a structured prompt
to the human operator. The CLI renders an interactive picker and resumes the
graph with the operator's choice.
"""

from decepticon.tools.interaction.ask_user import ask_user_question

__all__ = ["ask_user_question"]
