from pathlib import Path

import pandas as pd
import streamlit as st

from agent import run_agent

st.set_page_config(page_title="Job Agent", page_icon="🎯", layout="wide")
st.title("🎯 Job Agent")
st.caption("Paste a job posting URL: the agent reads it, picks the right CV, scores the fit and logs it.")

url = st.text_input("Job posting URL")

if st.button("Analyze", type="primary", disabled=not url):
    with st.status("Agent at work...", expanded=True) as status:
        result = run_agent(
            f"Analyze the job posting at this URL: {url} and add it to the tracker.",
            on_tool=st.write,
        )
        status.update(label="Done", state="complete")
    st.markdown(result)

st.subheader("📋 Tracker")
if Path("tracker.csv").exists():
    df = pd.read_csv("tracker.csv")
    st.dataframe(df.iloc[::-1], hide_index=True)  # most recent first
else:
    st.info("No applications yet.")