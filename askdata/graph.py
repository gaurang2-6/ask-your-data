"""The agent as a LangGraph state machine.

    generate_sql -> guard -> execute -> explain
         ^            |         |
         +--- retry --+---------+   (up to MAX_RETRIES, with the error fed back)
"""
from pathlib import Path
from typing import TypedDict

import pandas as pd
from langgraph.graph import END, START, StateGraph

from . import db
from .guard import GuardError, check
from .llm import LLM, LLMError

MAX_RETRIES = 2
PREVIEW_ROWS = 30


class State(TypedDict, total=False):
    question: str
    sql: str
    chart: dict
    rationale: str
    feedback: list[str]   # errors from earlier attempts, shown to the model
    attempts: int
    error: str | None     # set when the latest step failed
    fatal: bool           # the model call itself failed; retrying will not help
    df: pd.DataFrame
    truncated: bool
    explanation: str


def build_graph(llm: LLM, db_path: Path | None = None, explain: bool = True):
    schema = db.schema_context(db_path)

    def generate_sql(state: State) -> State:
        try:
            out = llm.generate_sql(state["question"], schema, state.get("feedback", []))
        except LLMError as e:
            return {"error": str(e), "fatal": True, "attempts": state.get("attempts", 0) + 1}
        return {"sql": out["sql"], "chart": out["chart"], "rationale": out["rationale"],
                "attempts": state.get("attempts", 0) + 1, "error": None}

    def guard(state: State) -> State:
        try:
            return {"sql": check(state["sql"])}
        except GuardError as e:
            return {"error": f"Rejected: {e}", "feedback": state.get("feedback", []) + [f"Rejected: {e}"]}

    def execute(state: State) -> State:
        try:
            result = db.run_query(state["sql"], db_path)
        except db.QueryError as e:
            return {"error": f"Database error: {e}",
                    "feedback": state.get("feedback", []) + [f"Database error: {e}"]}
        return {"df": result.df, "truncated": result.truncated}

    def explain_result(state: State) -> State:
        rows = state["df"].head(PREVIEW_ROWS).to_csv(index=False) if len(state["df"]) else "(no rows)"
        if state.get("truncated"):
            rows += f"\n(first {PREVIEW_ROWS} of more than {db.MAX_ROWS} rows)"
        elif len(state["df"]) > PREVIEW_ROWS:
            rows += f"\n(first {PREVIEW_ROWS} of {len(state['df'])} rows)"
        try:
            return {"explanation": llm.explain(state["question"], state["sql"], rows)}
        except LLMError as e:
            return {"explanation": f"(No explanation: {e})"}

    def after_step(next_node: str):
        def route(state: State) -> str:
            if not state.get("error"):
                return next_node
            if state.get("fatal") or state.get("attempts", 0) > MAX_RETRIES:
                return END
            return "generate_sql"
        return route

    g = StateGraph(State)
    g.add_node("generate_sql", generate_sql)
    g.add_node("guard", guard)
    g.add_node("execute", execute)
    g.add_edge(START, "generate_sql")
    g.add_conditional_edges("generate_sql", after_step("guard"), ["guard", END])
    g.add_conditional_edges("guard", after_step("execute"), ["execute", "generate_sql", END])
    if explain:
        g.add_node("explain", explain_result)
        g.add_conditional_edges("execute", after_step("explain"), ["explain", "generate_sql", END])
        g.add_edge("explain", END)
    else:
        g.add_conditional_edges("execute", after_step(END), [END, "generate_sql"])
    return g.compile()


def ask(question: str, llm: LLM, db_path: Path | None = None, explain: bool = True) -> State:
    return build_graph(llm, db_path, explain).invoke({"question": question})
