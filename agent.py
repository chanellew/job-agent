import csv
import json
import sys
from datetime import date
from pathlib import Path

import anthropic
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()
MODEL = "claude-sonnet-5-5"


# ---------- 1. Tools: plain Python functions ----------
def read_file(name: str) -> str:
    return Path(name).read_text()


def read_url(url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        return f"Error: could not read the page ({e})."
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()  # strip noise: menus, scripts, footers
    return soup.get_text(separator="\n", strip=True)[:15000]


def save_application(role, company, location, score, verdict, summary) -> str:
    tracker = Path("tracker.csv")
    is_new = not tracker.exists()
    with tracker.open("a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["date", "role", "company", "location", "score", "verdict", "summary", "status"])
        w.writerow([date.today().isoformat(), role, company, location, score, verdict, summary, "to apply"])
    return f"{company} application added to the tracker."


TOOL_FUNCTIONS = {
    "read_file": read_file,
    "read_url": read_url,
    "save_application": save_application,
}

# ---------- 2. Tool descriptions, so Claude knows how to use them ----------
TOOLS = [
    {
        "name": "read_file",
        "description": "Reads a local text file (e.g. cv.md, offer.txt) and returns its content.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "File name"}},
            "required": ["name"],
        },
    },
    {
        "name": "read_url",
        "description": "Fetches the text of a job posting from its URL. If the page is unreadable or blocked, tell the user.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "save_application",
        "description": "Adds an analyzed job posting to the CSV tracker. Call it once the analysis is done.",
        "input_schema": {
            "type": "object",
            "properties": {
                "role": {"type": "string"},
                "company": {"type": "string"},
                "location": {"type": "string"},
                "score": {"type": "integer", "description": "CV/job fit, from 0 to 100"},
                "verdict": {"type": "string", "enum": ["apply", "apply with reservations", "skip"]},
                "summary": {"type": "string", "description": "2 sentences max"},
            },
            "required": ["role", "company", "location", "score", "verdict", "summary"],
        },
    },
]

# ---------- 3. Context: what makes the agent relevant ----------
SYSTEM = """You are a job search assistant for a Product Manager or Product Builder.
Workflow:
1. Read the job posting first.
2. Detect its language. If it is in French, read cv_fr.md. Otherwise, read cv_en.md.
3. Assess the fit honestly, save the result to the tracker, then give a short summary (5 lines max).
Always answer in English.

Candidate context (take it into account in your analysis):
- Current role is a VIE, a fixed-term contract ending late December 2026: this is NOT an early departure
- Available from early January 2027
- Ideally looking abroad, preferably in an English-speaking country
- Does not want a fully remote role
"""


# ---------- 4. The agent loop ----------
def run_agent(request: str):
    messages = [{"role": "user", "content": request}]

    while True:
        response = client.messages.create(
            model=MODEL, max_tokens=2000, system=SYSTEM, tools=TOOLS, messages=messages
        )
        messages.append({"role": "assistant", "content": response.content})

        # Claude is done: no more tool calls
        if response.stop_reason != "tool_use":
            for block in response.content:
                if block.type == "text":
                    print("\n" + block.text)
            return

        # Claude wants to use tools: run them and send back the results
        results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"🔧 {block.name}({json.dumps(block.input, ensure_ascii=False)[:80]})")
                output = TOOL_FUNCTIONS[block.name](**block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
        messages.append({"role": "user", "content": results})


if __name__ == "__main__":
    if len(sys.argv) > 1:
        request = f"Analyze the job posting at this URL: {sys.argv[1]} and add it to the tracker."
    else:
        request = "Analyze the job posting in offer.txt and add it to the tracker."
    run_agent(request)