from types import SimpleNamespace

import pytest
from google.genai import errors

from askdata.gemini import GeminiLLM
from askdata.llm import LLMError, make_llm


class StubModels:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.calls = text, error, []

    def generate_content(self, model, contents, config):
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config))
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text, candidates=[])


def gemini(**kwargs):
    models = StubModels(**kwargs)
    return GeminiLLM(model="test-model", client=SimpleNamespace(models=models)), models


def test_generate_sql_asks_for_json_and_parses_it():
    llm, models = gemini(text='{"sql": "SELECT 1", "chart": {"type": "none", "x": "", "y": ""}, "rationale": "r"}')
    out = llm.generate_sql("One?", "schema here", ["Rejected: bad"])
    assert out["sql"] == "SELECT 1"
    call = models.calls[0]
    assert call.model == "test-model"
    assert call.config.response_mime_type == "application/json"
    assert "schema here" in call.config.system_instruction
    assert "Rejected: bad" in call.contents


def test_invalid_json_is_an_llm_error():
    llm, _ = gemini(text="not json")
    with pytest.raises(LLMError, match="invalid JSON"):
        llm.generate_sql("One?", "", [])


def test_empty_response_is_an_llm_error():
    llm, _ = gemini(text=None)
    with pytest.raises(LLMError, match="No text"):
        llm.explain("q", "SELECT 1", "one\n1")


@pytest.mark.parametrize("code, match", [(429, "Rate limited"), (400, "Gemini API error 400"),
                                         (503, "Gemini API error 503")])
def test_api_errors_become_llm_errors(code, match):
    cls = errors.ClientError if code < 500 else errors.ServerError
    llm, _ = gemini(error=cls(code, {"error": {"message": "boom", "status": "X"}}))
    with pytest.raises(LLMError, match=match):
        llm.explain("q", "SELECT 1", "")


def test_make_llm_picks_the_provider(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    assert isinstance(make_llm("gemini"), GeminiLLM)
    with pytest.raises(ValueError):
        make_llm("other")
