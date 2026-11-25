# 🎯 Job Agent

An AI agent that runs my job search: it finds job postings, scores how well they fit my profile,
keeps a tracker up to date and drafts tailored cover letters, in French or English.

Built from scratch in Python with the Claude API and tool use. No agent framework, so every
step of the loop is visible and explained in the code.

> 🎥 **[Watch the demo on Loom](https://www.loom.com/share/423475e6c326449b843a87e9e47ae669)**

---

## Why I built it

I'm a Product Manager with a Data Science & AI engineering background, and I'm looking for my next
role. Job hunting is repetitive: read a posting, check if it fits, pick the right CV, log it somewhere,
write a message that doesn't sound generic. I wanted to learn how to build an AI agent properly,
so I built the tool I needed, and I use it for my own search.

## What it does

| Ask the agent | What happens |
|---|---|
| Paste a job posting URL | Reads the posting, picks my French or English CV based on its language, scores the fit (0-100), lists strengths, gaps and red flags, and logs it in the tracker |
| `Find AI Product Manager roles in London` | Searches the web, keeps up to 5 open postings it can read, analyzes and logs each one, then returns a ranked recap |
| `Write a cover letter for Acme` | Finds the posting in the tracker, rereads it with my CV and personal context, writes a letter in the posting's language, reviews it, then saves it |
| `I just applied to Acme` | Updates the application status in the tracker |

Everything is available from a small **Streamlit** interface: one input field, the agent's steps shown
live, an editable tracker (status dropdown, score bars, links) and the drafts with a copy button.

## How it works

```
User request ──▶ Claude (system prompt + tool descriptions)
                    │
                    ├─ wants a tool? ──▶ Python runs it ──▶ result sent back ──┐
                    │                                                          │
                    ◀──────────────────────────────────────────────────────────┘
                    │
                    └─ done ──▶ final answer
```

The core is a ~30-line **agent loop** (`run_agent` in `agent.py`): Claude decides which tool to call
and in what order; the code only executes tools and sends results back until Claude is done.
For example, Claude reads the posting *first*, detects its language, and only then chooses which CV to read.
Nothing in the code hard-codes that order.

### Tools

| Tool | Type | Role |
|---|---|---|
| `read_url` | client | Fetches a job posting and strips the HTML noise |
| `read_file` | client | Reads local files: CVs, personal context |
| `web_search` | server (Anthropic) | Finds job postings online |
| `read_tracker` | client | Gives the agent memory of what's already saved |
| `save_application` | client | Logs an analyzed posting to `tracker.csv` |
| `update_status` | client | Moves an application through to apply → applied → interview → offer |
| `save_draft` | client | Saves a message or cover letter |

## Design decisions

- **Context makes the agent useful.** The first version flagged my "short tenure" as a red flag:
  it didn't know my contract is fixed-term. A few lines of candidate context in the system prompt fixed
  the analysis. Cover letters were generic until the agent got an `about_me.md` file with my motivations,
  stories and writing style.
- **The prompt guides, the code guarantees.** Rules that must never be broken are enforced in code, not just
  in the prompt. Duplicates are rejected by URL. Drafts are refused (and the agent must rewrite) if they
  contain clichés, exceed a length limit, or if more than 35% of sentences start with "I / je".
- **Self-review before saving.** The agent checks its own cover letter against a checklist
  ("would this letter still make sense if I swapped the company name?") and rewrites it if needed.
- **Tools return errors instead of crashing.** If a page is blocked or a file is missing, the tool says so
  and the agent adapts (skips it, tells the user).
- **Personal data stays local.** CVs, personal context, tracker and drafts are git-ignored.

## Run it

Requires Python 3.9+ and an [Anthropic API key](https://console.anthropic.com).

```bash
git clone <this repo> && cd job-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

Add your own files (all git-ignored):
- `cv_en.md` and `cv_fr.md`: your CV as plain text
- `about_me.md`: your motivations, stories and writing style (copy `about_me.example.md`)
- Edit the **Candidate context** block in `SYSTEM` (`agent.py`) with your own criteria

Then:
```bash
streamlit run app.py                          # web interface
python agent.py "https://job-posting-url"     # or from the terminal
```

Cost: a few cents per analyzed posting; a full job search is the most expensive request
(web search is $10 per 1,000 searches, plus tokens). Set a spend limit in the Anthropic Console.

## What's next

- **Better search recall**: the search often returns only a few readable postings. Next: more targeted
  queries per job board, and support for JavaScript-rendered pages.
- Tracker in Google Sheets instead of a local CSV
- Online version (Streamlit Community Cloud) with CV upload and password protection

## Stack

Python · Claude API (tool use, web search) · Streamlit · pandas · Requests · BeautifulSoup
