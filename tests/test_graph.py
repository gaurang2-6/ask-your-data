from askdata.graph import MAX_RETRIES, ask
from askdata.llm import LLMError


def test_happy_path(tiny_db, scripted):
    llm = scripted("SELECT country, sum(revenue) AS revenue FROM sales GROUP BY 1")
    state = ask("Revenue by country?", llm, tiny_db)
    assert state["error"] is None and state["attempts"] == 1
    assert len(state["df"]) == 3
    assert state["explanation"] == "Explained 3 rows."


def test_guard_rejection_is_fed_back_and_retried(tiny_db, scripted):
    llm = scripted("SELECT * FROM secrets", "SELECT count(*) AS n FROM sales")
    state = ask("How many lines?", llm, tiny_db)
    assert state["error"] is None and state["attempts"] == 2
    assert state["df"].n[0] == 4
    assert llm.feedback_seen[0] == []
    assert "Unknown table 'secrets'" in llm.feedback_seen[1][0]


def test_database_error_is_fed_back_and_retried(tiny_db, scripted):
    llm = scripted("SELECT no_such_column FROM sales", "SELECT count(*) AS n FROM sales")
    state = ask("How many lines?", llm, tiny_db)
    assert state["error"] is None and state["attempts"] == 2
    assert llm.feedback_seen[1][0].startswith("Database error")


def test_gives_up_after_the_retries(tiny_db, scripted):
    llm = scripted(*["SELECT * FROM secrets"] * (MAX_RETRIES + 1))
    state = ask("Show me the secrets", llm, tiny_db)
    assert state["attempts"] == MAX_RETRIES + 1
    assert state["error"].startswith("Rejected")
    assert "df" not in state and not llm.sqls


def test_api_failure_stops_without_retrying(tiny_db):
    class Broken:
        calls = 0

        def generate_sql(self, *args):
            Broken.calls += 1
            raise LLMError("Could not reach the Claude API.")

    state = ask("Anything", Broken(), tiny_db)
    assert Broken.calls == 1 and state["attempts"] == 1
    assert state["error"] == "Could not reach the Claude API."


def test_explain_off_skips_the_second_call(tiny_db, scripted):
    llm = scripted("SELECT 1 AS one")
    state = ask("One?", llm, tiny_db, explain=False)
    assert "explanation" not in state and state["df"].one[0] == 1
