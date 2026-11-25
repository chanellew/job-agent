from pathlib import Path

import pandas as pd
import streamlit as st

from agent import STATUSES, run_agent

st.set_page_config(page_title="Job Agent", page_icon="🎯", layout="wide")
st.title("🎯 Job Agent")
st.caption("Paste a job posting URL, or ask the agent something (e.g. 'Find AI PM roles in London', 'Mark YOOBIC as applied', 'Write a cover letter for Thiga').")

user_input = st.text_input("URL or request")

if st.button("Run", type="primary", disabled=not user_input):
    if user_input.strip().startswith("http"):
        prompt = f"Analyze the job posting at this URL: {user_input.strip()} and add it to the tracker."
    else:
        prompt = user_input

    with st.status("Agent at work...", expanded=True) as status:
        result = run_agent(prompt, on_tool=st.write)
        status.update(label="Done", state="complete")
    st.markdown(result)

st.subheader("📋 Tracker")
if Path("tracker.csv").exists():
    df = pd.read_csv("tracker.csv").iloc[::-1]  # most recent first
    edited = st.data_editor(
        df,
        hide_index=True,
        disabled=[c for c in df.columns if c != "status"],  # only status is editable
        column_config={
            "status": st.column_config.SelectboxColumn("status", options=STATUSES, required=True),
            "url": st.column_config.LinkColumn("link", display_text="open"),
            "score": st.column_config.ProgressColumn("score", min_value=0, max_value=100, format="%d"),
            "summary": st.column_config.TextColumn("summary", width="large"),
        },
    )
    if not edited.equals(df):
        edited.iloc[::-1].to_csv("tracker.csv", index=False)  # restore original order before saving
        st.toast("Status saved ✅")
else:
    st.info("No applications yet.")

st.subheader("✉️ Drafts")
drafts = sorted(Path("drafts").glob("*.md"), reverse=True) if Path("drafts").exists() else []
if drafts:
    for d in drafts:
        with st.expander(d.stem.replace("_", " · ")):
            try:
                st.code(d.read_text(), language=None, wrap_lines=True)  # copy button top-right
            except TypeError:  # older Streamlit versions don't support wrap_lines
                st.code(d.read_text(), language=None)
else:
    st.info("No drafts yet. Try: 'Write a LinkedIn message for YOOBIC'.")
