# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running

Always just:

```bash
python run.py
```

`run.py` handles everything:
- Creates `.venv/` and installs deps on first run (stdlib bootstrap, transparent)
- Detects first-time users (Ollama missing or no models pulled) → runs setup wizard
- Returning users → goes straight to interactive prompts (folder, goal, options)

The root `requirements.txt` covers both setup deps (`rich`, `requests`, `psutil`) and agent deps (`langgraph`, `langchain-*`, etc.).

## Architecture

**PLAN-AND-ACT** loop implemented with LangGraph:

```
Planner → [User Confirm] → Executor (loops) → [on failure] → Reflector → retry/skip/replan
```

- **`graph.py`** — LangGraph state machine wiring all nodes together. The executor loops itself via a conditional edge (not a Python for-loop), one step per graph invocation.
- **`planner.py`** — LLM call that generates a JSON step plan. Reads file contents for ambiguous filenames, validates plan against a simulated filesystem to catch hallucinated paths, and injects vision rename steps for images.
- **`executor.py`** — Runs one step, handles dry-run/safe mode, tracks stats. Checks `state["decision"] == "skip"` at the top to handle reflector skip decisions.
- **`reflector.py`** — Only fires on step failure. Auto-skips known-unretryable errors (patterns in `config.SKIP_ERROR_PATTERNS`); force-skips after 3 retries or 3 replans; otherwise asks LLM: retry | skip | replan.
- **`state.py`** — `AgentState` TypedDict: all graph nodes communicate exclusively through this shared state dict.
- **`config.py`** — All constants (model name, Ollama URL, token limits, retry limits, log paths). Edit here to tune behavior.
- **`config_vision.py`** — Vision-specific constants (`VISION_MODEL = "qwen3-vl:8b"`, image extensions, vision test folder).

**Tools** (`tools/`): `list_files`, `read_file` (text/PDF/DOCX/image-aware), `create_folder`, `move_file`, `rename_file`. All tools handle collision by appending `_1`, `_2` instead of overwriting.

**Utils** (`utils/`): `confirm.py` (rich table UI), `logger.py` (terminal output + stats), `manifest.py` (per-run JSON audit trail written to `~/.file-agent/runs/<run_id>/manifest.json`).

## Test Data

- `tests/data/folder/` — 12 generic-named text files (doc1.txt, stuff.txt, …)
- `tests/data/folder-vision/` — Mixed images + text for vision testing
- `--test-run` copies either sample to `tests/output/run_<timestamp>/` before running

## Key Behaviors

- `<think>` tags are stripped from LLM output (qwen3 variants emit them)
- Plan validation runs before execution; broken source paths trigger a targeted LLM correction call
- Stats (`files_moved`, `folders_created`, `files_renamed`) accumulate in `state["stats"]` and print at end
- Vision mode: images are described by `qwen3-vl:8b` and rename steps are auto-injected into the plan
