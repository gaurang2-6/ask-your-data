"""Ask a business question about the retail data; get the SQL, the table, a chart and a plain answer.

    streamlit run app.py
"""
import os

import altair as alt
import pandas as pd
import streamlit as st

from askdata import db
from askdata.graph import build_graph
from askdata.llm import make_llm

EXAMPLES = [
    "Which month had the highest revenue, and how much was it?",
    "What are the top 5 countries by revenue outside the United Kingdom?",
    "How much revenue did each RFM segment bring in during 2011?",
    "Which hour of the day gets the most orders?",
    "Show monthly revenue for 2011.",
]
BLUE = "#2a78d6"

st.set_page_config(page_title="Ask your data", layout="wide")


@st.cache_resource
def agent():
    return build_graph(make_llm())


def chart(df: pd.DataFrame, spec: dict):
    kind, x, y = spec.get("type"), spec.get("x"), spec.get("y")
    if kind == "none" or x not in df.columns or y not in df.columns or len(df) < 2:
        return None
    if not pd.api.types.is_numeric_dtype(df[y]):
        return None
    if kind == "line":
        mark = alt.Chart(df).mark_line(color=BLUE, strokeWidth=2, point=True)
        x_enc = alt.X(f"{x}:T" if pd.api.types.is_datetime64_any_dtype(df[x]) or "month" in x else f"{x}:O",
                      title=None)
    else:
        mark = alt.Chart(df).mark_bar(color=BLUE, cornerRadiusEnd=4)
        x_enc = alt.X(f"{x}:N", sort="-y", title=None)
    return (mark.encode(x=x_enc, y=alt.Y(f"{y}:Q", title=y.replace("_", " ")),
                        tooltip=[x, alt.Tooltip(y, format=",.2f")])
            .properties(height=320)
            .configure_axis(grid=True, gridColor="#e4e3df", domain=False)
            .configure_view(strokeWidth=0))


st.title("Ask your data")
st.caption("Plain-English questions over two years of UK online retail sales (Dec 2009 to Dec 2011, GBP). "
           "An LLM (Claude or Gemini) writes one read-only SQL query; it is checked, run with a 10-second limit, and explained.")

KEY = "GEMINI_API_KEY" if os.environ.get("ASK_PROVIDER", "").lower() == "gemini" else "ANTHROPIC_API_KEY"
if not os.environ.get(KEY):
    st.error(f"Set {KEY} in your environment, then restart the app.")
    st.stop()
try:
    graph = agent()
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()

cols = st.columns(len(EXAMPLES))
for col, example in zip(cols, EXAMPLES):
    if col.button(example, width="stretch"):
        st.session_state.question = example

question = st.text_input("Your question", key="question", placeholder="e.g. Who are our top 10 customers?")
if not question:
    st.stop()

with st.spinner("Writing and running the query..."):
    state = graph.invoke({"question": question})

if state.get("error"):
    st.error(f"Could not answer after {state.get('attempts', 0)} attempt(s). {state['error']}")
    if state.get("sql"):
        st.code(state["sql"], language="sql")
    st.stop()

df = state["df"]
st.subheader("Answer")
st.write(state.get("explanation", ""))

left, right = st.columns([3, 2])
with left:
    c = chart(df, state.get("chart", {}))
    if c is not None:
        st.altair_chart(c, width="stretch")
    st.dataframe(df, width="stretch", hide_index=True)
    if state.get("truncated"):
        st.caption(f"Showing the first {db.MAX_ROWS:,} rows.")
with right:
    st.markdown("**SQL**")
    st.code(state["sql"], language="sql")
    st.caption(state.get("rationale", ""))
    if state.get("feedback"):
        with st.expander(f"Fixed itself after {len(state['feedback'])} failed attempt(s)"):
            for f in state["feedback"]:
                st.write(f"- {f}")
