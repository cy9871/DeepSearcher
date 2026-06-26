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

DeepSearcher resolves LLM settings through a **4-level priority chain**:

| Priority | Method | Notes |
|----------|--------|-------|
| 1 | `DEEPSEARCH_*` env vars | Direct override, highest priority |
| 2 | `local_config.json` | Project root, gitignored |
| 3 | `OPENAI_*` standard env vars | Compatible with OpenAI SDK conventions |
| 4 | Defaults | `https://api.openai.com/v1` / `gpt-4o` |

### Option A: OpenAI (zero config)

Just set the standard env var:

```bash
export OPENAI_API_KEY="sk-..."
```

To override base URL or model:

```bash
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_MODEL="gpt-4o"        # optional, default gpt-4o
```

### Option B: Your own gateway (local_config.json)

Copy the template and edit:

```bash
cp local_config.json.example local_config.json
# edit local_config.json with your endpoint
```

```json
{
  "base_url": "http://localhost:8080/v1",
  "api_key": "sk-***",
  "model": "gpt-4o"
}
```

`local_config.json` is in `.gitignore` — it won't leak to the repo.

### Environment Variables Reference

| Variable | Notes |
|----------|-------|
| `OPENAI_API_KEY` | API key |
| `OPENAI_BASE_URL` | Any OpenAI-compatible API endpoint |
| `DEEPSEARCH_API_KEY` | Overrides `OPENAI_API_KEY` |
| `DEEPSEARCH_BASE_URL` | Overrides `OPENAI_BASE_URL` |
| `DEEPSEARCH_MODEL` | Model name, default `gpt-4o` |
| `JINA_API_KEY` | Optional — enables Jina Search |
| `MAX_TURNS` | Max loop iterations, default 20 |
| `TOKEN_BUDGET` | Total token budget, default 100000 |

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
