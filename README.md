# NeatAgent — File Organization Agent

An AI-powered tool that organizes files using a local LLM via Ollama. Uses a LangGraph PLAN-AND-ACT architecture: the agent generates a full plan, shows it to you for approval, then executes step by step. Everything runs locally — no API key, no data leaves your machine.

---

## Repository Layout

```
file-agent/            Agent source code
├── agent.py           Orchestration and argument parsing
├── graph.py           LangGraph state machine (nodes + conditional edges)
├── planner.py         Planner node: folder listing → JSON mapping → step plan
├── executor.py        Executor node: runs one step per graph invocation
├── reflector.py       Reflector node: failure routing (retry / skip / replan)
├── state.py           AgentState TypedDict — shared state across all nodes
├── config.py          All constants: model, paths, thresholds, patterns
├── config_vision.py   Vision model config (qwen3-vl:8b)
├── tools/             Filesystem tools: list_files, read_file, create_folder,
│                        move_file, rename_file
└── utils/             confirm.py (plan UI), logger.py, manifest.py

setup/                 Guided installer — detects hardware, installs Ollama,
└── setup.py             recommends and pulls a suitable model

tests/
├── data/
│   ├── model_test/    10-file evaluation dataset (generic names)
│   ├── sample/        24-file mixed dataset (organized subfolders)
│   └── folder/        12-file generic dataset for quick manual tests
└── output/            Created at runtime (gitignored)

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
├── eval_folder.py     Folder-based evaluator (no manifest required)
├── prep_claude_test.py  Prep a test folder for external organizers
└── results/           Saved per-run and comparison JSONs (gitignored)

docs/                  Reports, paper, and architecture diagrams
run.py                 Universal entry point — start here
requirements.txt       All Python dependencies
```

---

## Build

### Prerequisites

- Python 3.10 or later
- [Ollama](https://ollama.com) installed and running

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
ollama pull qwen2.5-coder:14b   # default (~9 GB, best results)
```

Lighter options for machines with less RAM:
```bash
ollama pull qwen3:8b            # 5.2 GB, good balance
ollama pull llama3.2:3b         # 2.0 GB, fastest
```

For image classification (vision mode):
```bash
ollama pull qwen3-vl:8b
```

### Step 3 — Run

```bash
python run.py
```

This handles everything on first run: creates a virtual environment, installs dependencies, and walks you through setup if Ollama isn't configured yet. On subsequent runs it goes straight to the folder picker.

---

## External Software

| Component | Library | Purpose |
|-----------|---------|---------|
| Agent framework | [LangGraph](https://github.com/langchain-ai/langgraph) | State machine wiring Planner → Executor → Reflector |
| LLM inference | [Ollama](https://ollama.com) | Local model serving via REST API |
| LLM client | [langchain-ollama](https://pypi.org/project/langchain-ollama/) | `ChatOllama` wrapper for LangGraph nodes |
| LangChain core | [langchain-core](https://pypi.org/project/langchain-core/) | Message types, tool protocol |
| PDF reading | [pdfplumber](https://github.com/jsvine/pdfplumber) | Text extraction from PDF files |
| DOCX reading | [python-docx](https://python-docx.readthedocs.io) | Text extraction from Word documents |
| Terminal UI | [rich](https://github.com/Textualize/rich) | Plan table display, colored output |
| HTTP client | [requests](https://docs.python-requests.org) | Ollama health check and API calls |

AI tools used during development: **Claude Code** (Anthropic) for code generation, debugging, and documentation.

---

## Evaluation

The `eval/` directory contains a full evaluation pipeline for measuring how accurately the agent organizes files.

### Metrics

| Metric | Definition |
|--------|-----------|
| Coverage | Fraction of files moved out of the root |
| Placement Accuracy | Fraction placed in the correct semantic folder (with alias matching) |
| Judge Score | 1–10 quality rating from a local LLM |

### Test datasets

| Dataset | Files | Location | Ground Truth |
|---------|-------|----------|--------------|
| `model_test` | 10 files (txt, pdf, csv, jpg) with generic names | `tests/data/model_test/` | `eval/ground_truth/model_test.json` |
| `sample_flat` | 24 files flattened from organized subfolders | `eval/datasets/sample_flat/` | `eval/ground_truth/sample_flat.json` |

### Run the evaluation

```bash
cd eval

# Compare multiple models (no judge, fast)
python runner.py --models qwen2.5-coder:14b qwen3:8b llama3.2:3b --no-judge

# Full evaluation with LLM-as-judge
python runner.py --models qwen2.5-coder:14b qwen3:8b --runs-per-model 1

# Evaluate an already-organized folder (e.g. organized by Claude Code or manually)
python eval_folder.py --folder /path/to/organized/ --dataset model_test --organizer claude-code

# Prep a fresh test folder for an external organizer
python prep_claude_test.py --dataset model_test
```

Results are saved to `eval/results/` as JSON and displayed as a terminal table.

---

## Milestone Documents

| Document | Location |
|----------|----------|
| Project proposal | `docs/project_proposal.pdf` |
| Progress report | `docs/NeatAgent.pdf` |
| Final report | `docs/final_report.md` |
| Paper | `docs/paper.tex` |
