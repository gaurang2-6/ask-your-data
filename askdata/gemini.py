"""The same two calls as llm.ClaudeLLM, made to Google Gemini (free tier via AI Studio).

Reads GEMINI_API_KEY from the environment. Set ASK_MODEL to try another Gemini model.
"""
import json
import os

from google import genai
from google.genai import errors, types

from .llm import EXPLAIN_SYSTEM, SQL_SCHEMA, SQL_SYSTEM, LLMError

DEFAULT_MODEL = "gemini-3.5-flash-lite"  # the free model the eval ran on
TIMEOUT_MS = 60_000  # a hung call becomes an LLMError instead of stalling the agent
# The free tier answers bursts with 429 (rate limit) and 503 (high demand); back off and try again.
RETRY = types.HttpRetryOptions(attempts=6, initial_delay=5, max_delay=60, http_status_codes=[429, 503])


class GeminiLLM:
    def __init__(self, model: str | None = None, client: genai.Client | None = None):
        self.model = model or os.environ.get("ASK_MODEL", DEFAULT_MODEL)
        self.client = client or genai.Client(api_key=os.environ.get("GEMINI_API_KEY"),
                                             http_options=types.HttpOptions(timeout=TIMEOUT_MS, retry_options=RETRY))

    def _generate(self, system: str, content: str, **config) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=content,
                config=types.GenerateContentConfig(system_instruction=system, **config),
            )
        except errors.ClientError as e:
            if e.code == 429 and "PerDay" in str(e.details):
                raise LLMError(f"Daily quota used up for {self.model}; try another model or tomorrow.") from e
            if e.code == 429:
                raise LLMError("Rate limited by the Gemini API; wait a moment and retry.") from e
            raise LLMError(f"Gemini API error {e.code}: {e.message}") from e
        except errors.APIError as e:
            raise LLMError(f"Gemini API error {e.code}: {e.message}") from e
        except OSError as e:
            raise LLMError("Could not reach the Gemini API.") from e
        if not response.text:
            reason = response.candidates[0].finish_reason if response.candidates else "blocked"
            raise LLMError(f"No text in the response (finish_reason={reason}).")
        return response.text

    def generate_sql(self, question: str, schema: str, feedback: list[str]) -> dict:
        content = question
        if feedback:
            content += "\n\nYour previous attempts failed:\n" + "\n".join(f"- {f}" for f in feedback) + \
                       "\nFix the query."
        text = self._generate(SQL_SYSTEM.format(schema=schema), content,
                              response_mime_type="application/json", response_json_schema=SQL_SCHEMA)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError("The model returned invalid JSON.") from e

    def explain(self, question: str, sql: str, rows: str) -> str:
        return self._generate(EXPLAIN_SYSTEM, f"Question: {question}\n\nQuery:\n{sql}\n\nResult:\n{rows}").strip()
