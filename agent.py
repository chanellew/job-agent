import csv
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import anthropic
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()
MODEL = "claude-sonnet-5-5"
STATUSES = ["to apply", "applied", "interview", "offer", "rejected", "skipped"]


# ---------- 1. Tools: plain Python functions ----------
def read_file(name: str) -> str:
    path = Path(name)
    if not path.exists():
        return f"Error: {name} does not exist."
    return path.read_text()


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


def save_application(role, company, location, score, verdict, summary, url="") -> str:
    tracker = Path("tracker.csv")
    is_new = not tracker.exists()
    if url and not is_new:
        with tracker.open() as f:
            if any(r.get("url") == url for r in csv.DictReader(f)):
                return "Not saved: this URL is already in the tracker."
    with tracker.open("a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["date", "role", "company", "location", "score", "verdict", "summary", "status", "url"])
        w.writerow([date.today().isoformat(), role, company, location, score, verdict, summary, "to apply", url])
    return f"{company} application added to the tracker."

def read_tracker() -> str:
    tracker = Path("tracker.csv")
    if not tracker.exists():
        return "The tracker is empty."
    with tracker.open() as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return "The tracker is empty."
    return "\n".join(
        f"- {r['company']} | {r['role']} | added {r['date']} | score {r['score']} | {r['status']} | {r.get('url', '')}"
        for r in rows
    )

def update_status(company: str, status: str, role: str = "") -> str:
    tracker = Path("tracker.csv")
    if not tracker.exists():
        return "The tracker is empty."
    with tracker.open() as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    matches = [
        r for r in rows
        if company.lower() in r["company"].lower() and role.lower() in r["role"].lower()
    ]
    if not matches:
        return f"No posting found for {company}."
    if len(matches) > 1:
        options = "; ".join(f"{r['company']} - {r['role']}" for r in matches)
        return f"Several postings match, ask the user which one: {options}"

    matches[0]["status"] = status
    with tracker.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return f"{matches[0]['company']} - {matches[0]['role']} marked as '{status}'."


# Guardrail: clichés and length limits are checked in code, not just in the prompt
BANNED_PHRASES = [
    "je serais ravie", "je serais ravi", "c'est exactement", "passionnée par", "passionné par",
    "n'hésitez pas", "dynamique et motivée", "je me permets", "vivement intéressée",
    "i would be thrilled", "i am excited to apply", "i am writing to express", "passionate about",
    "perfect fit", "dynamic and motivated", "don't hesitate", "i believe i would be",
]
MAX_WORDS = {"linkedin-message": 60, "email": 150, "cover-letter": 330}


def self_centered_ratio(text: str) -> float:
    """Share of sentences that start with 'je/j'/I/my/mon...'."""
    sentences = [x.strip() for x in re.split(r"[.!?\n]+", text) if len(x.strip().split()) > 3]
    if not sentences:
        return 0.0
    me_starts = r"^(je|j'|j’|moi|mon|ma|mes|i|i'm|i’ve|i've|my|me)\b"
    return sum(bool(re.match(me_starts, x, re.IGNORECASE)) for x in sentences) / len(sentences)


def save_draft(company: str, kind: str, content: str) -> str:
    found = [p for p in BANNED_PHRASES if p in content.lower()]
    if found:
        return f"Not saved: rewrite without these clichés: {', '.join(found)}."
    ratio = self_centered_ratio(content)
    if ratio > 0.35:  # a real letter needs some "je": the opening and closing
        return (f"Not saved: {ratio:.0%} of sentences start with 'I/je/my'. Max 35%. "
                "Rewrite so more sentences start from the company, its clients, the problem or the work.")
    words = len(content.split())
    if words > MAX_WORDS[kind]:
        return f"Not saved: {words} words, the limit for a {kind} is {MAX_WORDS[kind]}. Cut it down."
    folder = Path("drafts")
    folder.mkdir(exist_ok=True)
    name = f"{datetime.now():%Y-%m-%d_%H%M}_{company.lower().replace(' ', '-')}_{kind}.md"  # keeps every version
    (folder / name).write_text(content)
    return f"Draft saved as drafts/{name}."

TOOL_FUNCTIONS = {
    "read_file": read_file,
    "read_url": read_url,
    "save_application": save_application,
    "read_tracker": read_tracker,
    "update_status": update_status,
    "save_draft": save_draft,
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
                "url": {"type": "string", "description": "Job posting URL, if known"},
            },
            "required": ["role", "company", "location", "score", "verdict", "summary"],
        },
    },
    {
        "name": "read_tracker",
        "description": "Returns all job postings already saved in the tracker (company, role, date, score, status, URL).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "update_status",
        "description": "Updates the status of a posting already in the tracker.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "status": {"type": "string", "enum": STATUSES},
                "role": {"type": "string", "description": "Optional, only if the company has several postings"},
            },
            "required": ["company", "status"],
        },
    },
    # Server tool: the web search runs on Anthropic's side, we don't implement it ($10 / 1,000 searches)
    {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 5,  # max searches per request, to keep costs under control
        # read_url can't read these sites (login wall / JavaScript), so don't bother finding postings there
        "blocked_domains": ["linkedin.com", "indeed.com", "glassdoor.com"],
    },
    {
        "name": "save_draft",
        "description": "Saves a drafted message or cover letter so the user can copy it later.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "kind": {"type": "string", "enum": ["linkedin-message", "email", "cover-letter"]},
                "content": {"type": "string", "description": "The full draft, ready to send"},
            },
            "required": ["company", "kind", "content"],
        },
    },
]

# ---------- 3. Context: what makes the agent relevant ----------
SYSTEM = """You are a job search assistant for a Product Manager.

If the user gives a job posting (URL or file), follow this workflow:
1. Call read_tracker to see which postings are already saved.
2. Read the job posting.
3. If it is already in the tracker (same URL, or same company AND same role), stop there:
   do not analyze or save it, just tell the user when it was added and its score.
4. Otherwise, detect its language. If it is in French, read cv_fr.md. Otherwise, read cv_en.md.
5. Assess the fit honestly, save the result (including the URL) to the tracker,
   then give a short summary (5 lines max).

If the user asks to update an application (e.g. "I applied to YOOBIC"), use update_status.
If several postings match, ask which one.

If the user asks for a message or cover letter for a posting:
1. Call read_tracker to find it and its URL (or use the URL the user gives), then read the posting,
   the CV matching its language, and about_me.md (her motivations, stories and writing style).
2. Identify the ONE thing this company needs most from this hire, based on the posting.
3. Write the draft in the posting's language.
   A cover letter keeps the classic format of a real letter, in this order:
   - Greeting addressed to the team, e.g. "Chère équipe Thiga," / "Dear YOOBIC team,".
   - Opening paragraph: say which role she is applying for, then in the same paragraph, why this
     role at this company caught her attention (their need or challenge, in their own terms).
   - Story paragraph(s): ONE story from her experience (or from about_me.md) that answers that need,
     told as a story with a beginning and an end: the situation, what she noticed or decided,
     what she did, what came out of it. Use transitions so it reads like prose, not a list of facts
     or tools. At most one other brief proof point. NEVER walk through her CV job by job.
   - Why them: something specific to this company (from the posting or a fact you read),
     linked to something she actually cares about (from about_me.md).
   - Closing paragraph: her availability (early January 2027) and that she remains available
     for a first conversation, e.g. "Je reste disponible pour un premier échange." /
     "I would welcome the chance to discuss this with you."
   - Sign-off: "Bien à vous," / "Best regards," then her name.
   An email follows the same logic in a shorter form; a LinkedIn message stays short and direct.
   Write like her (see the writing sample in about_me.md): plain words, warm but not flowery.
   Make it about THEM, not about her: the company, its clients and the problem are the subject of most
   sentences, and her experience comes in as proof of what she can do for them
   (e.g. "Vos clients veulent X : c'est ce que ... a permis de ..." rather than "J'ai fait X. J'ai fait Y.").
   Avoid starting consecutive sentences with "je" / "I".
   Never invent facts, figures or motivations that are not in the CV or about_me.md.
   Length: linkedin-message under 300 characters; email under 150 words with a subject line;
   cover-letter between 250 and 330 words.
4. Before saving, review your draft against this checklist and rewrite if any answer is no:
   - If I replaced the company name with a competitor's, would the draft stop making sense?
   - Is there one story with concrete detail, told as a story rather than a list of facts or jobs?
   - (cover letter) Does it have the greeting, the role she applies for, the availability and the closing?
   - Does it sound like a person talking, not a template?
   - Is it about them at least as much as about her (not a string of "je... je... je...")?
5. Save it with save_draft (if it is refused, fix the issue and try again), then show it to the user.

If the user asks you to find job postings (e.g. "Find AI PM roles in London"):
1. Call read_tracker first, so you skip postings that are already saved.
2. Use web_search to find individual, currently open postings that match the request and her context.
   Prefer pages that can be read directly: company career pages and job boards such as
   jobs.lever.co, boards.greenhouse.io, jobs.ashbyhq.com, apply.workable.com, jobs.smartrecruiters.com,
   welcometothejungle.com. Ignore listing pages, aggregators and postings that look closed or old.
3. Pick at most 5 promising postings (fewer if the user asks), then for each one: read it with
   read_url, analyze it against the right CV, and save it to the tracker, exactly as for a single posting.
   If a page can't be read, skip it and say so.
4. End with a short ranked recap: role, company, location, score, verdict (best first),
   plus the postings you skipped and why.

Answer in English, except drafts, which follow the posting's language.

Candidate context (take it into account in your analysis):
- Current role is a VIE, a fixed-term contract ending late December 2026: this is NOT an early departure
- Available from early January 2027
- Ideally looking abroad, preferably in an English-speaking country, but open to France if the role is very interesting
- Does not want a fully remote role
"""


# ---------- 4. The agent loop ----------
def run_agent(request: str, on_tool=print) -> str:
    messages = [{"role": "user", "content": request}]

    while True:
        response = client.messages.create(
            model=MODEL, max_tokens=4000, system=SYSTEM, tools=TOOLS, messages=messages
        )
        # Blocks must be sent back exactly as received (web search results are encrypted)
        messages.append({"role": "assistant", "content": response.content})

        for block in response.content:
            if block.type == "server_tool_use":  # a web search Anthropic ran for us
                on_tool(f"🔎 web_search({json.dumps(block.input, ensure_ascii=False)[:80]})")

        # Long server-side work (e.g. several searches): the API pauses, we just call it again
        if response.stop_reason == "pause_turn":
            continue

        # Claude is done: return its final answer
        if response.stop_reason != "tool_use":
            return "\n".join(b.text for b in response.content if b.type == "text")

        # Claude wants to use tools: run them and send back the results
        results = []
        for block in response.content:
            if block.type == "tool_use":
                on_tool(f"🔧 {block.name}({json.dumps(block.input, ensure_ascii=False)[:80]})")
                output = TOOL_FUNCTIONS[block.name](**block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
        messages.append({"role": "user", "content": results})


if __name__ == "__main__":
    if len(sys.argv) > 1:
        request = f"Analyze the job posting at this URL: {sys.argv[1]} and add it to the tracker."
    else:
        request = "Analyze the job posting in offer.txt and add it to the tracker."
    print(run_agent(request))