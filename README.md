# DeepSearcher

A multi-turn research agent that digs deeper into complex questions.

Most LLMs give shallow answers to hard questions.

English | [简体中文](./README.zh.md)

DeepSearcher tackles this by looping through search → read → reflect → refine — like a human researcher who reads one source, finds gaps, and searches again until the answer is solid.

---

## How It Works

```
Input Question
  │
  ▼
Planner — splits into sub-questions
  │
  ▼
Loop (up to N turns):
  Search → Read → Reflect → Rewrite query → Repeat
  │
  ▼
Quality Gates — check for coverage, timeliness, accuracy
  │
  ▼
Final Answer + traceable evidence
```

No fancy diagrams. Just a state machine with five tools and six exit checks.

---

## Quick Start

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# CLI
python -m deepsearcher "What are the latest breakthroughs in solid-state batteries?"

# Web UI
python -m deepsearcher.server
# → http://localhost:8080
```

Web UI requires building the frontend first:

```bash
cd vue && npm install && npm run build && cd ..
```

---

## Configuration

Copy and edit `deepsearcher/config.py`, or set environment variables:

| Variable | Default | Notes |
|----------|---------|-------|
| `DEEPSEARCH_BASE_URL` | `http://localhost:56685/v1` | Any OpenAI-compatible API |
| `DEEPSEARCH_API_KEY` | *(built-in)* | Replace with yours |
| `DEEPSEARCH_MODEL` | `openclaw` | Model name |
| `JINA_API_KEY` | *(empty)* | Optional — enables Jina Search |
| `MAX_TURNS` | 20 | Max research loop iterations |
| `TOKEN_BUDGET` | 100000 | Total token budget |

DeepSearcher defaults to a local LLM gateway. To use OpenAI directly:

```bash
export DEEPSEARCH_BASE_URL="https://api.openai.com/v1"
export DEEPSEARCH_API_KEY="sk-..."
export DEEPSEARCH_MODEL="gpt-4o"
```

---

## What's Inside

```
DeepSearcher/
├── requirements.txt
├── deepsearcher/         # Python package
│   ├── __main__.py      # `python -m deepsearcher "..."`
│   ├── cli.py           # CLI logic
│   ├── agent.py         # LangGraph research loop
│   ├── server.py        # Web API (FastAPI + SSE)
│   ├── config.py        # Settings
│   ├── models.py        # Pydantic schemas
│   └── tools/
│       ├── planner.py   # Question decomposition
│       ├── search.py    # DuckDuckGo / Jina
│       ├── read.py      # Content extraction
│       ├── evaluate.py  # Quality check
│       └── rewrite.py   # Query refinement
│   └── utils/
│       ├── text_tools.py
│       ├── token_tracker.py
│       └── url_tools.py
├── vue/                 # Vue 3 frontend
│   └── src/
└── results/             # (gitignored) cached runs
```

---

## Design Tradeoffs

- **Token budget is shared, not per-turn.** One expensive read can eat into later turns. Set `TOKEN_BUDGET` generously.
- **Beast Mode** reserves 15% budget for a final fallback. If the loop burns through the first 85%, Beast Mode produces the best answer it can with what remains.
- **DuckDuckGo is free but limited.** For deep research on technical topics, set up Jina Search or swap in your own search backend.
- **SSE streaming works, but frontend is a single-page Vue app.** If you need a different UI, hit the `/api/research` endpoint directly.

---

## License

Apache 2.0
