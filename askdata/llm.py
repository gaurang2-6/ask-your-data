"""The two Claude calls the agent makes: write the SQL, then explain the result.

Reads ANTHROPIC_API_KEY from the environment. Set ASK_MODEL to try another model, or
ASK_PROVIDER=gemini to use askdata/gemini.py instead.
"""
import json
import os
from typing import Protocol

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"

SQL_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {"type": "string", "description": "One DuckDB SELECT statement, no trailing semicolon."},
        "chart": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["bar", "line", "none"]},
                "x": {"type": "string", "description": "Result column for the x axis, or empty."},
                "y": {"type": "string", "description": "Numeric result column for the y axis, or empty."},
            },
            "required": ["type", "x", "y"],
            "additionalProperties": False,
        },
        "rationale": {"type": "string", "description": "One sentence on which tables and logic you used."},
    },
    "required": ["sql", "chart", "rationale"],
    "additionalProperties": False,
}

SQL_SYSTEM = """You are a careful analytics engineer. Turn the user's question into one DuckDB SELECT \
statement over the tables below. Rules:
- Read-only: a single SELECT (CTEs are fine). Never write, attach, copy, or read files.
- Use only the tables and columns listed. Do not invent columns.
- Return the columns that answer the question, with clear aliases. Add the label column \
(month, country, segment...) next to each number.
- For "top N" or "which ... most" questions, ORDER BY the measure and LIMIT N (LIMIT 1 for a single answer).
- Do not round numbers; the app formats them.
- If the question cannot be answered from these tables, return SELECT 'cannot answer: <reason>' AS answer.
Pick a chart: "line" for a measure over time, "bar" to compare a measure across a few categories, \
"none" for a single value or a wide table.

Tables:
{schema}"""

EXPLAIN_SYSTEM = """You explain query results to a business user in two or three plain sentences. \
Lead with the answer and its number, then one useful observation from the rows. Use GBP (£) for money. \
Do not mention SQL, tables or columns. If the result is empty, say so and suggest how to rephrase."""


class LLMError(RuntimeError):
    """The model call failed or returned something unusable."""


class LLM(Protocol):
    def generate_sql(self, question: str, schema: str, feedback: list[str]) -> dict: ...
    def explain(self, question: str, sql: str, rows: str) -> str: ...


class ClaudeLLM:
    def __init__(self, model: str | None = None, client: anthropic.Anthropic | None = None):
        self.model = model or os.environ.get("ASK_MODEL", DEFAULT_MODEL)
        self.client = client or anthropic.Anthropic()

    def _create(self, **kwargs) -> str:
        try:
            response = self.client.messages.create(model=self.model, max_tokens=16000, **kwargs)
        except anthropic.RateLimitError as e:
            raise LLMError("Rate limited by the Claude API; wait a moment and retry.") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Could not reach the Claude API.") from e
        if response.stop_reason == "refusal":
            raise LLMError("The model declined to answer this question.")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LLMError(f"No text in the response (stop_reason={response.stop_reason}).")
        return text

    def generate_sql(self, question: str, schema: str, feedback: list[str]) -> dict:
        content = question
        if feedback:
            content += "\n\nYour previous attempts failed:\n" + "\n".join(f"- {f}" for f in feedback) + \
                       "\nFix the query."
        text = self._create(
            system=[{"type": "text", "text": SQL_SYSTEM.format(schema=schema),
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
            output_config={"format": {"type": "json_schema", "schema": SQL_SCHEMA}, "effort": "medium"},
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError("The model returned invalid JSON.") from e

    def explain(self, question: str, sql: str, rows: str) -> str:
        return self._create(
            system=EXPLAIN_SYSTEM,
            messages=[{"role": "user", "content": f"Question: {question}\n\nQuery:\n{sql}\n\nResult:\n{rows}"}],
            output_config={"effort": "low"},
        ).strip()


def make_llm(provider: str | None = None, model: str | None = None) -> LLM:
    """ASK_PROVIDER=claude (default) or gemini."""
    provider = (provider or os.environ.get("ASK_PROVIDER", "claude")).lower()
    if provider == "gemini":
        from .gemini import GeminiLLM
        return GeminiLLM(model)
    if provider == "claude":
        return ClaudeLLM(model)
    raise ValueError(f"Unknown provider {provider!r}; use claude or gemini.")
