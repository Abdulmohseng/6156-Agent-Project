# File Organization Agent

A terminal-based AI agent that accepts natural language instructions and autonomously organizes files on your local filesystem. Powered by a local LLM via Ollama — fully offline, zero API cost, zero data leaves your machine.

```
$ python agent.py "Organize my downloads folder by file type and date"

File Organization Agent
  Goal   : Organize my downloads folder by file type and date
  Folder : /Users/you/Downloads
  Model  : qwen2.5-coder:14b
  Mode   : plan-and-act

[PLANNER] Analyzing folder and generating plan...
[PLANNER] Generated 12-step plan.

                            PLAN REVIEW
┏━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Step  ┃ Description                            ┃ Tool           ┃
┡━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│   1   │ Create Documents/                      │ create_folder  │
│   2   │ Move report.pdf → Documents/           │ move_file      │
│  ...  │ ...                                    │ ...            │
└───────┴────────────────────────────────────────┴────────────────┘

Proceed with 12 steps? [y/n] (y): y

[EXECUTING]
  ✓ Created Documents/
  ✓ Moved report.pdf → Documents/
  ✓ Done in 12 steps

── Summary ──────────────────────────────────────
  Steps completed : 12
  Files moved     : 9
  Folders created : 3
  Duration        : 8.4s
  Log saved to    : ~/.file-agent/logs/2026-03-12_14-32-00.json
─────────────────────────────────────────────────
```

---

## How it works

The agent uses a **PLAN-AND-ACT** architecture implemented as a LangGraph state machine. Planning and execution are strictly separated so the LLM never plans and acts simultaneously — this prevents goal drift on long-horizon tasks.

```
User Instruction
      ↓
  [Planner node]     ← LLM call — generates a JSON step plan
      ↓
  Plan shown to user → Human approves (y/n)
      ↓
  [Executor node]    ← Runs each step using filesystem tools
      ↓
  [Reflector node]   ← Called only on failure; decides retry / skip / replan
        ↙      ↓      ↘
     retry   skip   replan → back to Planner
```

---

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) running locally (`ollama serve`)
- A pulled model (default: `qwen2.5-coder:14b`)

For vision features (image classification), pull the multimodal variant:
```bash
ollama pull qwen3-vl:8b
```

---

## Installation

```bash
# Clone or navigate to the project
cd file-agent

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate       # macOS/Linux
# .venv\Scripts\activate        # Windows

# Install dependencies
pip install -r requirements.txt
```

---

## Usage

```bash
# Basic — organize ~/Downloads by file type
python agent.py "Organize my downloads by file type"

# Specify a different folder
python agent.py "Sort these by date" --folder ~/Desktop/Projects

# Safe mode — confirm each move/rename individually before it runs
python agent.py "Clean up this folder" --safe

# Dry run — show the plan only, no files are touched
python agent.py "Organize downloads" --dry-run

# Verbose — print full tool output for every step
python agent.py "Organize downloads" --verbose

# Use the multimodal model for image classification
python agent.py "Organize my photos" --model qwen3-vl:8b
```

### All flags

| Flag | Default | Description |
|------|---------|-------------|
| `--folder PATH` | `~/Downloads` | Target folder to organize |
| `--safe` | off | Confirm each destructive step (move, rename) before executing |
| `--dry-run` | off | Show plan only — no files are moved or renamed |
| `--verbose` | off | Print full tool output for each step |
| `--mode` | `plan-and-act` | Agent mode: `plan-and-act`, `reactive`, or `direct` |
| `--model` | `qwen2.5-coder:14b` | Ollama model name |

---

## Agent modes

| Mode | Description |
|------|-------------|
| `plan-and-act` | Full plan generated upfront, shown for approval, then executed (default) |
| `reactive` | Same graph as plan-and-act — executes plan without a separate preview step |
| `direct` | Single LLM call with no tools — describes what it would do, takes no action |

The `direct` mode is useful for benchmarking how well the LLM understands the goal without tool access. Run all three on the same folder to compare approach quality and LLM call counts.

---

## Tools

The agent has five filesystem tools:

| Tool | Description |
|------|-------------|
| `list_files` | List all non-hidden files in a folder with name, extension, size, and modified time |
| `read_file` | Format-aware reader: text, PDF (pdfplumber), DOCX (python-docx), images (Ollama vision) |
| `create_folder` | Create a folder and all intermediate directories (`mkdir -p`) |
| `move_file` | Move a file with collision detection — never silently overwrites |
| `rename_file` | Rename a file, preserving extension, with collision detection |

All tools return `{ "success": bool, "message": str, ...data }`.

---

## Human-in-the-loop

Two confirmation levels:

**1. Plan confirmation (always on)** — the full plan is shown as a table before any execution begins. Type `y` to proceed or `n` to cancel.

**2. Step confirmation (`--safe` flag)** — prompts before each individual move or rename:
```
  Step 3: Move invoice_march.txt → Documents/
  Tool: move_file  Args: {'src': '...', 'dest_folder': '...'}
  Execute this step? [y/n] (y):
```

---

## Error recovery

When a step fails, the **Reflector** node makes a lightweight LLM call and returns one of three decisions:

- **retry** — re-attempt the same step (e.g. destination folder wasn't created yet)
- **skip** — step is non-critical, advance to the next one
- **replan** — failure is significant enough to regenerate the entire plan from current state (capped at 3 replans to prevent loops)

---

## Execution logs

After each run a JSON log is saved to `~/.file-agent/logs/YYYY-MM-DD_HH-MM-SS.json`:

```json
{
  "timestamp": "2026-03-12T14:32:00",
  "goal": "Organize downloads by file type",
  "model": "qwen2.5-coder:14b",
  "plan_steps": 12,
  "steps_completed": 12,
  "steps_failed": 0,
  "steps_skipped": 0,
  "replans": 0,
  "files_moved": 9,
  "folders_created": 3,
  "files_renamed": 0,
  "duration_seconds": 8.4
}
```

---

## Project structure

```
file-agent/
├── agent.py              # Entry point — CLI, Ollama health check
├── graph.py              # LangGraph state machine definition
├── planner.py            # Planner node: goal + file listing → JSON plan
├── executor.py           # Executor node: runs one step per invocation
├── reflector.py          # Reflector node: failure routing (retry/skip/replan)
├── state.py              # AgentState TypedDict
├── tools/
│   ├── list_files.py
│   ├── read_file.py
│   ├── rename_file.py
│   ├── create_folder.py
│   └── move_file.py
├── utils/
│   ├── confirm.py        # Human-in-the-loop prompts (rich)
│   └── logger.py         # Step logging and JSON run summary
└── requirements.txt
```

---

## Tech stack

| Component | Library |
|-----------|---------|
| LLM | `qwen2.5-coder:14b` (default) / `qwen3-vl:8b` (vision) via Ollama |
| LangChain LLM | `langchain-ollama` (`ChatOllama`) |
| Agent framework | `langgraph` |
| PDF reading | `pdfplumber` |
| DOCX reading | `python-docx` |
| CLI / output | `rich`, `argparse` |
| HTTP | `requests` (Ollama health check) |

---

## Testing

A test folder with mixed dummy files is provided at `~/file-agent-test/`. Always test there before pointing the agent at real folders.

```bash
# Safe first run — dry run on test folder
python agent.py "organize by file type" --folder ~/file-agent-test --dry-run

# Full run with per-step confirmation
python agent.py "organize by file type" --folder ~/file-agent-test --safe
```

---

## Swapping models

The LangGraph graph is model-agnostic. Any Ollama model can be swapped in via `--model`:

```bash
# Text-only alternatives
python agent.py "organize" --model llama3.2:3b        # fast, smaller
python agent.py "organize" --model qwen3:8b           # good balance
python agent.py "organize" --model qwen2.5-coder:14b  # default — best JSON reliability

# Multimodal (required for image classification)
python agent.py "organize my photos" --model qwen3-vl:8b
```

### Model comparison (M4 Pro 24GB)

| Model | Size | JSON reliability | Speed | Already pulled |
|-------|------|-----------------|-------|----------------|
| `qwen2.5-coder:14b` | 9.0 GB | Excellent | ~25 tok/s | **Yes (default)** |
| `qwen3:14b` | ~9 GB | Excellent | ~25 tok/s | No |
| `qwen3:8b` | 5.2 GB | Good | ~40 tok/s | Yes |
| `llama3.2:3b` | 2.0 GB | Fair | ~70 tok/s | Yes |

`qwen2.5-coder:14b` is the default — it's already pulled, and the "coder" variant has strong instruction-following for precise tool arguments and structured JSON output. Pull `qwen3:14b` if you want better semantic reasoning for content-based classification.
