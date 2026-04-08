# File Organization Agent

A terminal-based AI agent that accepts natural language instructions and autonomously organizes files on your local filesystem. Powered by a local LLM via [Ollama](https://ollama.com) — fully offline, zero API cost, no data leaves your machine.

---

## Table of Contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [CLI reference](#cli-reference)
- [Agent modes](#agent-modes)
- [Models](#models)
- [Tools](#tools)
- [Human-in-the-loop](#human-in-the-loop)
- [Error recovery](#error-recovery)
- [Run manifests](#run-manifests)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Tech stack](#tech-stack)

---

## How it works

The agent uses a **PLAN-AND-ACT** architecture implemented as a LangGraph state machine. Planning and execution are strictly separated so the LLM never plans and acts at the same time — this prevents goal drift on long-horizon tasks.

```
User instruction
      │
  ┌───▼────┐
  │Planner │  LLM call — reads folder contents, generates a JSON step plan
  └───┬────┘
      │ plan shown to user → human approves (y/n)
  ┌───▼────┐
  │Executor│  runs one step per graph invocation (loops itself via conditional edge)
  └───┬────┘
      │ on failure
  ┌───▼────────┐
  │ Reflector  │  lightweight LLM call → retry | skip | replan
  └───┬────────┘
      │ replan        retry / skip
      └──► Planner    └──► Executor
```

### Planner

Receives the goal and a listing of all files in the target folder. For small text files with generic/ambiguous names (e.g. `doc1.txt`, `stuff.txt`), it reads the first 400 characters of each file inline so it can classify by content rather than filename. Outputs a structured JSON plan — ordered steps with tool names and exact arguments.

### Executor

Runs one step per graph invocation. On success, advances to the next step and loops back. On failure, routes to the Reflector instead of proceeding. Supports dry-run (logs intent, touches nothing) and safe mode (confirms before each destructive operation).

### Reflector

Called only when a step fails. Makes a lightweight LLM call and returns one of three decisions:

| Decision | Meaning |
|----------|---------|
| `retry` | Try the same step again (e.g. a race condition or transient issue) |
| `skip` | Step is non-critical — advance past it |
| `replan` | Failure is significant enough to regenerate the entire plan from current state |

The Reflector also has deterministic overrides that bypass the LLM for unambiguous cases:
- **Auto-skip** if error contains "not found", "does not exist", "already exists", etc.
- **Force skip** if a step has been retried 3 or more times (configurable via `config.py`)
- **Force skip** if replan has been triggered more than 3 times (prevents loops)

---

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) running locally (`ollama serve`)
- At least one pulled model (default: `qwen2.5-coder:14b`)

```bash
ollama pull qwen2.5-coder:14b   # default model (~9 GB)
```

For image classification (vision features):
```bash
ollama pull qwen3-vl:8b
```

---

## Installation

```bash
# Navigate to the agent directory
cd file-agent

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate       # macOS/Linux
# .venv\Scripts\activate        # Windows

# Install dependencies
pip install -r requirements.txt
```

---

## Quick start

```bash
# Make sure Ollama is running
ollama serve

# Organize a specific folder
python agent.py "Organize my downloads by file type" --folder ~/Downloads

# Preview the plan without touching any files
python agent.py "Sort these into categories" --folder ~/Desktop --dry-run

# Run on the built-in sample folder (safe for testing)
python agent.py "Organize by content" --test-run --dry-run
```

Example output:

```
Test copy created: file-agent/test-output/run_2026-03-12_17-11-47

File Organization Agent
  Goal   : Organize by content
  Folder : .../test-output/run_2026-03-12_17-11-47
  Model  : qwen2.5-coder:14b
  Mode   : plan-and-act
  Run ID : 2026-03-12_17-11-47

[PLANNER] Analyzing folder and generating plan...
[PLANNER] Generated 18-step plan.

                         PLAN REVIEW
┏━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Step  ┃ Description                             ┃ Tool           ┃
┡━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│   1   │ Create Finance/                         │ create_folder  │
│   2   │ Rename invoice.txt → invoice_acme_q1    │ rename_file    │
│   3   │ Move invoice_acme_q1.txt → Finance/     │ move_file      │
│  ...  │ ...                                     │ ...            │
└───────┴─────────────────────────────────────────┴────────────────┘

Proceed with 18 steps? [y/n] (y): y

[EXECUTING]
  ✓ Create Finance/
  ✓ Rename invoice.txt → invoice_acme_q1.txt
  ✓ Move invoice_acme_q1.txt → Finance/
  ...

─── Summary ───────────────────────────────────
  Steps completed : 18
  Files moved     : 10
  Folders created : 4
  Files renamed   : 6
  Duration        : 31.2s
  Manifest        : ~/.file-agent/runs/2026-03-12_17-11-47/manifest.json
────────────────────────────────────────────────
```

---

## CLI reference

```
python agent.py <goal> [options]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `goal` | *(required)* | Natural language instruction for organizing files |
| `--folder PATH` | `~/Downloads` | Target folder to organize |
| `--safe` | off | Prompt before each destructive step (move, rename) |
| `--dry-run` | off | Generate and display the plan only — no files are modified |
| `--verbose` | off | Print full tool output for each executed step |
| `--mode` | `plan-and-act` | Agent mode: `plan-and-act`, `reactive`, or `direct` |
| `--model` | `qwen2.5-coder:14b` | Ollama model name |
| `--test-run` | off | Run against a fresh copy of `file-agent/folder/` — safe for testing |

### Examples

```bash
# Organize by semantic category (Finance, Work, Health, etc.)
python agent.py "Organize by content and rename files descriptively"

# Different target folder
python agent.py "Group by year" --folder ~/Documents/Receipts

# Safe mode — confirm every move and rename before it runs
python agent.py "Clean up" --folder ~/Desktop --safe

# Dry run — useful for reviewing what the agent would do
python agent.py "Organize downloads" --dry-run

# Combine test-run + dry-run to validate the plan without any side effects
python agent.py "Sort by content" --test-run --dry-run

# Use verbose output to see every tool result
python agent.py "Organize photos" --folder ~/Pictures --verbose

# Use a different model
python agent.py "Sort these files" --model qwen3:8b
```

---

## Agent modes

| Mode | Description |
|------|-------------|
| `plan-and-act` | Full plan generated upfront, reviewed by user, then executed step by step |
| `reactive` | Same graph as `plan-and-act` — executes without a separate preview/confirmation step |
| `direct` | Single LLM call, no tools — describes what it would do without taking any action |

`direct` mode is useful for benchmarking how well the model understands a goal before committing to it. You can run all three on the same folder to compare quality and approach.

---

## Models

The graph is model-agnostic. Any Ollama model can be used via `--model`. The default is optimized for JSON reliability and instruction-following on M-series Macs.

| Model | Size | JSON reliability | Speed (M4 Pro) | Notes |
|-------|------|-----------------|----------------|-------|
| `qwen2.5-coder:14b` | 9.0 GB | Excellent | ~25 tok/s | **Default** — strong structured output |
| `qwen3:14b` | ~9 GB | Excellent | ~25 tok/s | Better semantic reasoning; pull required |
| `qwen3:8b` | 5.2 GB | Good | ~40 tok/s | Faster; already pulled if you used an older version |
| `llama3.2:3b` | 2.0 GB | Fair | ~70 tok/s | Good for quick iterations on simple goals |

```bash
python agent.py "organize" --model llama3.2:3b          # fastest
python agent.py "organize" --model qwen3:8b             # good balance
python agent.py "organize" --model qwen2.5-coder:14b    # default
python agent.py "organize my photos" --model qwen3-vl:8b  # vision / image classification
```

`qwen2.5-coder:14b` is the default because the "coder" variants have particularly strong instruction-following for structured JSON output and precise tool arguments.

To use `qwen3:14b` (recommended for content-heavy classification tasks):
```bash
ollama pull qwen3:14b
python agent.py "organize by content" --model qwen3:14b
```

---

## Tools

The agent has five filesystem tools. All tools return `{ "success": bool, "message": str, ...data }`.

### `list_files`
Lists all non-hidden files in a folder (non-recursive).

```python
list_files(folder: str) -> {
    "success": bool,
    "files": [{"name", "extension", "size_bytes", "modified_timestamp", "full_path"}],
    "count": int,
}
```

### `read_file`
Format-aware reader that handles plain text, PDF, DOCX, and images.

```python
read_file(path: str, max_chars: int = 3000) -> {
    "success": bool,
    "file_type": "text" | "pdf" | "docx" | "image" | "binary",
    "content": str,
    "truncated": bool,
}
```

Image files (`.jpg`, `.png`, `.webp`, etc.) are described by the vision model if `--model` is a `-vl:` variant. PDF and DOCX text is extracted with `pdfplumber` and `python-docx` respectively.

### `create_folder`
Creates a folder and all intermediate directories (`mkdir -p`). Returns `created: false` if the folder already existed (not an error).

```python
create_folder(path: str) -> {
    "success": bool,
    "path": str,
    "created": bool,
}
```

### `move_file`
Moves a file to a destination folder. Never silently overwrites — appends `_1`, `_2`, etc. on collision.

```python
move_file(src: str, dest_folder: str) -> {
    "success": bool,
    "src": str,
    "dest": str,       # final path (may differ if collision)
    "dest_folder": str,
}
```

### `rename_file`
Renames a file in place, preserving the original extension if the new name has none. Collision-safe.

```python
rename_file(path: str, new_name: str) -> {
    "success": bool,
    "old_path": str,
    "new_path": str,
    "new_name": str,
}
```

---

## Human-in-the-loop

There are two confirmation levels:

**1. Plan confirmation (always on)**

The full plan is shown as a table before any execution begins. You can review every step, then approve or abort.

```
Proceed with 18 steps? [y/n] (y):
```

**2. Step confirmation (`--safe` flag)**

Prompts before each individual move or rename:

```
  Step 3: Move invoice_q1.txt → Finance/
  Tool: move_file  Args: {'src': '...', 'dest_folder': '...'}
  Execute this step? [y/n] (y):
```

Declining skips that step and records it in the manifest as `user_skipped`.

---

## Error recovery

When a step fails, the **Reflector** analyzes the error and returns one of three decisions:

```
  ✗ Move report.pdf → Finance/
    Source file not found: ...

[REFLECTOR] Auto-skip (unretryable error)
  ⊘ Move report.pdf → Finance/ (skipped)
```

**Deterministic overrides (no LLM call):**
- Errors matching "not found", "does not exist", "already exists" → immediate `skip`
- Step retried ≥ 3 times on the same index → force `skip`
- More than 3 replans in one run → force `skip`

**LLM-decided cases** (ambiguous errors):
- `retry` → re-attempt the same step
- `skip` → advance to the next step
- `replan` → regenerate the entire plan from current folder state

All thresholds are set in `config.py`.

---

## Run manifests

Every run produces a structured JSON manifest saved to:

```
~/.file-agent/runs/<run_id>/manifest.json
```

The manifest captures everything that happened in the run — the plan, every step's outcome, and summary statistics. This gives you a full audit trail of what the agent did.

### Schema

```json
{
  "version": "1.0",
  "run_id": "2026-03-12_17-11-47",
  "metadata": {
    "timestamp": "2026-03-12T17:11:47",
    "goal": "Organize by content",
    "folder": "/Users/you/Downloads",
    "model": "qwen2.5-coder:14b",
    "mode": "plan-and-act",
    "dry_run": false,
    "safe_mode": false
  },
  "plan": [
    {
      "step": 1,
      "description": "Create Finance folder",
      "tool": "create_folder",
      "args": { "path": "/Users/you/Downloads/Finance" }
    }
  ],
  "execution": [
    {
      "step_index": 0,
      "step_number": 1,
      "description": "Create Finance folder",
      "tool": "create_folder",
      "args": { "path": "/Users/you/Downloads/Finance" },
      "status": "success",
      "message": "Created '/Users/you/Downloads/Finance'",
      "duration_seconds": 0.003
    }
  ],
  "summary": {
    "plan_steps": 18,
    "steps_completed": 17,
    "steps_failed": 0,
    "steps_skipped": 1,
    "replans": 0,
    "files_moved": 10,
    "folders_created": 4,
    "files_renamed": 6,
    "duration_seconds": 31.2
  }
}
```

### Step statuses

| Status | Meaning |
|--------|---------|
| `success` | Tool executed and returned successfully |
| `skipped` | Reflector decided to skip after failure |
| `user_skipped` | User declined in `--safe` mode |
| `dry_run` | Logged but not executed (`--dry-run` flag) |

### Browsing past runs

```bash
ls ~/.file-agent/runs/                    # list all runs
cat ~/.file-agent/runs/<run_id>/manifest.json | python3 -m json.tool
```

---

## Configuration

All tunable constants are in `config.py`. Edit this file to change defaults without touching any other source file.

```python
# config.py

DEFAULT_MODEL = "qwen2.5-coder:14b"   # default --model
DEFAULT_FOLDER = "~/Downloads"         # default --folder
RUNS_DIR = Path.home() / ".file-agent" / "runs"

PLANNER_NUM_PREDICT = 8192    # max tokens for the planner LLM call
REFLECTOR_NUM_PREDICT = 50    # max tokens for the reflector LLM call

MAX_RETRIES_PER_STEP = 3      # force-skip after this many retries on one step
MAX_REPLANS = 3               # force-skip after this many replans in one run

CONTENT_PREVIEW_MAX_CHARS = 400   # chars of preview to include in planner prompt
CONTENT_PREVIEW_MAX_BYTES = 8192  # only preview files smaller than this

SKIP_ERROR_PATTERNS = (        # auto-skip without calling the LLM
    "not found",
    "no such file",
    "does not exist",
    "already exists",
    "already moved",
)
```

---

## Project structure

```
file-agent/
├── agent.py              # CLI entry point, Ollama health check, orchestration
├── graph.py              # LangGraph state machine (nodes + conditional edges)
├── planner.py            # Planner node: goal + file listing → JSON step plan
├── executor.py           # Executor node: runs one step per invocation, loops
├── reflector.py          # Reflector node: failure routing (retry/skip/replan)
├── state.py              # AgentState TypedDict — shape of all state passed through graph
├── config.py             # Centralized constants (model, paths, thresholds, patterns)
├── tools/
│   ├── __init__.py
│   ├── list_files.py     # List non-hidden files with metadata
│   ├── read_file.py      # Format-aware reader: text, PDF, DOCX, images
│   ├── create_folder.py  # mkdir -p equivalent
│   ├── move_file.py      # Move with collision detection
│   └── rename_file.py    # Rename with collision detection
├── utils/
│   ├── __init__.py
│   ├── confirm.py        # Human-in-the-loop: plan table + step prompts (rich)
│   ├── logger.py         # Terminal output: step status, summary, stats init
│   └── manifest.py       # Run manifest: build + save full per-run JSON record
├── folder/               # Built-in sample folder for --test-run
│   ├── doc1.txt
│   ├── stuff.txt
│   └── ...
├── test-output/          # Created by --test-run (gitignored)
└── requirements.txt
```

---

## Tech stack

| Component | Library |
|-----------|---------|
| LLM | `qwen2.5-coder:14b` (default) / any Ollama model |
| LangChain LLM | `langchain-ollama` (`ChatOllama`) |
| Agent framework | `langgraph` |
| PDF reading | `pdfplumber` |
| DOCX reading | `python-docx` |
| CLI / output | `rich`, `argparse` |
| HTTP | `requests` (Ollama health check) |

---

## Testing

A test folder with mixed dummy files is at `file-agent/folder/`. Always test there before pointing the agent at real folders.

```bash
# Safest: dry run on the sample folder — shows plan, touches nothing
python agent.py "organize by content" --test-run --dry-run

# Full run with per-step confirmation
python agent.py "organize by content" --test-run --safe

# Full run, no confirmation
python agent.py "organize by content" --test-run
```

Test output is written to `file-agent/test-output/run_<timestamp>/` (gitignored).
