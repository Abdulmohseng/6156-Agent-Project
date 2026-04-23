# File Organization Agent

An AI-powered CLI tool that organizes files using a local LLM via Ollama. Uses a LangGraph PLAN-AND-ACT architecture: the agent generates a full plan, shows it to you for approval, then executes step by step with optional per-step confirmation. Everything runs locally — no API key, no data leaves your machine.

---

## Table of Contents

- [Repository Layout](#repository-layout)
- [Build](#build)
- [Run](#run)
- [External Software](#external-software)
- [Evaluation](#evaluation)

---

## Repository Layout

```
file-agent/            Agent source code
├── agent.py           CLI entry point and orchestration
├── graph.py           LangGraph state machine (nodes + conditional edges)
├── planner.py         Planner node: folder listing → JSON step plan
├── executor.py        Executor node: runs one step per graph invocation
├── reflector.py       Reflector node: failure routing (retry / skip / replan)
├── state.py           AgentState TypedDict — shared state across all nodes
├── config.py          All constants: model, paths, thresholds, patterns
├── config_vision.py   Vision model config (qwen3-vl:8b)
├── tools/             Filesystem tools: list_files, read_file, create_folder,
│                        move_file, rename_file
└── utils/             confirm.py (plan UI), logger.py, manifest.py

setup/                 Guided installer — detects hardware, installs Ollama,
│                        recommends and pulls a suitable model
└── setup.py

tests/
├── data/
│   ├── model_test/              10-file evaluation dataset (generic names)
│   │   └── organized_model_test/  Ground truth reference organization
│   ├── sample/                  24-file mixed dataset (organized subfolders)
│   └── folder/                  12-file generic dataset for quick manual tests
└── output/                      Created at runtime by --test-run (gitignored)

eval/                  Evaluation pipeline
├── ground_truth/      Labeled JSON datasets with expected folder placements
│   ├── model_test.json
│   └── sample_flat.json
├── datasets/
│   └── sample_flat/   Flattened copy of tests/data/sample/ for eval runs
├── compare.py         Structural scorer (placement accuracy, coverage)
├── judge.py           LLM-as-judge via Ollama (semantic quality, 1–10 score)
├── runner.py          Multi-model eval orchestrator
├── report.py          Rich terminal table + JSON aggregation
└── results/           Saved per-run and comparison JSONs (gitignored)

docs/                  Detailed architecture and CLI reference
run.py                 Universal entry point (handles first-time setup + runs)
requirements.txt       All Python dependencies
```

---

## Build

### Prerequisites

- Python 3.10 or later
- [Ollama](https://ollama.com) installed and running (`ollama serve`)
- At least one pulled model

### Step 1 — Install Ollama

**macOS / Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**macOS (Homebrew):**
```bash
brew install ollama
```

**Windows:** Download the installer from [ollama.com](https://ollama.com).

### Step 2 — Pull a model

```bash
ollama pull qwen2.5-coder:14b   # default (~9 GB, best JSON reliability)
```

Lighter alternatives for machines with less RAM:

```bash
ollama pull qwen3:8b            # 5.2 GB, good balance
ollama pull llama3.2:3b         # 2.0 GB, fastest
```

For image classification (vision mode):
```bash
ollama pull qwen3-vl:8b
```

### Step 3 — Install Python dependencies

```bash
cd file-agent
python3 -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows

pip install -r requirements.txt
```

Or use the guided installer which handles all of the above automatically:
```bash
python run.py    # detects first-time setup and runs the wizard
```

---

## Run

Make sure Ollama is running before any agent command:
```bash
ollama serve
```

### Simplest — interactive wizard

```bash
python run.py
```

Asks which folder and what goal, then runs the agent. Handles first-time setup automatically.

### Direct CLI

```bash
cd file-agent

# Organize a folder
python agent.py "Organize my downloads by content" --folder ~/Downloads

# Preview plan only — no files modified
python agent.py "Sort by category" --folder ~/Desktop --dry-run

# Run on built-in test data (safe for trying out)
python agent.py "Organize by content" --test-run

# Confirm each move/rename individually before it runs
python agent.py "Clean up" --folder ~/Documents --safe

# Use a different model
python agent.py "Organize" --model qwen3:8b --test-run

# Auto-approve plan (for scripted/evaluation runs)
python agent.py "Organize files semantically" --test-run --yes
```

### Full CLI reference

| Flag | Default | Description |
|------|---------|-------------|
| `goal` | *(required)* | Natural language instruction |
| `--folder PATH` | — | Target folder (omit to use `--test-run`) |
| `--test-run` | off | Copy built-in test data to `data/output/` and run there |
| `--dry-run` | off | Show plan only, touch nothing |
| `--safe` | off | Confirm each destructive step individually |
| `--verbose` | off | Print full tool output per step |
| `--mode` | `plan-and-act` | Agent mode: `plan-and-act`, `reactive`, or `direct` |
| `--model` | `qwen2.5-coder:14b` | Any Ollama model name |
| `--yes` / `-y` | off | Auto-approve plan (for non-interactive/scripted runs) |

Every run saves a full audit manifest to `~/.file-agent/runs/<run_id>/manifest.json`.

---

## External Software

This project is built on the following external frameworks and libraries:

| Component | Library / Project | Purpose |
|-----------|------------------|---------|
| Agent framework | [LangGraph](https://github.com/langchain-ai/langgraph) | State machine wiring Planner → Executor → Reflector nodes |
| LLM inference | [Ollama](https://ollama.com) | Local model serving via REST API |
| LLM client | [langchain-ollama](https://pypi.org/project/langchain-ollama/) | `ChatOllama` wrapper for LangGraph nodes |
| LangChain core | [langchain-core](https://pypi.org/project/langchain-core/) | Message types, tool protocol |
| PDF reading | [pdfplumber](https://github.com/jsvine/pdfplumber) | Text extraction from PDF files |
| DOCX reading | [python-docx](https://python-docx.readthedocs.io) | Text extraction from Word documents |
| Terminal UI | [rich](https://github.com/Textualize/rich) | Plan table display, colored output |
| HTTP client | [requests](https://docs.python-requests.org) | Ollama health check and generate API calls |

The agent architecture (PLAN-AND-ACT with separate Planner and Executor nodes, and a Reflector for failure recovery) is inspired by the ReAct and Reflexion agent patterns from the research literature, implemented from scratch using LangGraph's conditional edge routing.

---

## Evaluation

The `eval/` directory contains a full evaluation pipeline for measuring how accurately the agent organizes files. It scores runs on two dimensions: **structural accuracy** (did files land in the right folder?) and **semantic quality** (LLM-as-judge score 1–10).

### What is measured

| Metric | Definition |
|--------|-----------|
| Coverage | Fraction of files moved out of the root (not left behind) |
| Placement Accuracy | Fraction of files placed in the correct semantic folder (with synonym matching) |
| Judge Score | 1–10 quality rating from a local LLM evaluating folder structure, naming, and completeness |

### Test datasets

Two labeled datasets are included:

| Dataset | Files | Location | Ground Truth |
|---------|-------|----------|--------------|
| `model_test` | 10 files (txt, pdf, csv, jpg) with generic names | `tests/data/model_test/` | `eval/ground_truth/model_test.json` |
| `sample_flat` | 24 files flattened from organized subfolders | `eval/datasets/sample_flat/` | `eval/ground_truth/sample_flat.json` |

Each ground truth JSON maps every filename to its expected folder and a list of acceptable synonym folder names (e.g. `invoices`, `Finance`, `Bills` are all accepted for an invoice file). The reference organization for `model_test` is in `tests/data/model_test/organized_model_test/`.

### How to replicate the evaluation

**Evaluate an existing run** (no agent re-run needed):
```bash
cd eval

# Find a past run ID
ls ~/.file-agent/runs/

# Score it — structural metrics only (fast)
python3 runner.py --existing-run <run_id> --dataset model_test --no-judge

# Score with LLM judge
python3 runner.py --existing-run <run_id> --dataset model_test
```

**Run fresh agent evaluations and compare models:**
```bash
cd eval

# Quick comparison — no LLM judge
python3 runner.py --models qwen2.5-coder:14b qwen3:8b --no-judge

# Full evaluation with LLM-as-judge, 3 runs per model
python3 runner.py --models qwen2.5-coder:14b qwen3:8b --runs-per-model 3

# Evaluate on the larger sample_flat dataset
python3 runner.py --models qwen2.5-coder:14b --dataset sample_flat
```

Results are saved to `eval/results/` as JSON and displayed as a rich terminal table.

### Alternative systems compared

The evaluation framework is designed to compare multiple systems across the same datasets. The primary comparison is between two **model variants** running the same agent code:

| System | Model | Characteristics |
|--------|-------|----------------|
| **System A** (default) | `qwen2.5-coder:14b` | Strong structured JSON output, high instruction-following reliability |
| **System B** | `qwen3:8b` | Faster inference, better semantic reasoning, organizes by category rather than extension |

A second axis of comparison is **agent mode**:

| Mode | Description |
|------|-------------|
| `plan-and-act` | Full plan generated upfront, reviewed, then executed with error recovery |
| `direct` | Single LLM call with no tools — describes what it would do, no execution |

`direct` mode serves as a **no-tool baseline**: it shows what the LLM understands about the goal without any filesystem feedback loop. Comparing `plan-and-act` against `direct` on the same goal isolates the contribution of the tool-use loop and the Reflector's error recovery.

To run the baseline comparison:
```bash
cd file-agent

# Plan-and-act (full agent)
python agent.py "Organize files semantically" --test-run --yes

# Direct mode (baseline — no execution)
python agent.py "Organize files semantically" --test-run --mode direct
```

Then evaluate the `plan-and-act` run:
```bash
cd eval
python3 runner.py --existing-run <run_id> --dataset model_test
```

### Evaluation output format

Each run produces a JSON result in `eval/results/`:

```json
{
  "run_id": "2026-04-23_14-10-22",
  "model": "qwen2.5-coder:14b",
  "structural": {
    "total_files": 10,
    "coverage": 1.0,
    "placement_accuracy": 0.8,
    "per_file": [...]
  },
  "judge": {
    "score": 7,
    "reasoning": "...",
    "folder_quality": "good",
    "naming_quality": "fair"
  },
  "agent_summary": {
    "files_moved": 10,
    "folders_created": 5,
    "replans": 0,
    "duration_seconds": 142.3
  }
}
```

Multi-run comparisons are aggregated into `eval/results/comparison_<timestamp>.json` with per-model averages across all runs.

---

For full architecture details, CLI reference, and configuration options, see [`docs/README.md`](docs/README.md).
