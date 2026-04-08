# File Organization Agent

An AI-powered CLI tool that organizes files using a local LLM via Ollama. Uses a LangGraph PLAN-AND-ACT architecture: the agent generates a full plan, shows it to you for approval, then executes step by step with optional per-step confirmation.

## Quick Start

```bash
python run.py
```

That's it — always the same command. `run.py` figures out what to do:

- **First time**: detects missing Ollama or models → walks you through setup (installs Ollama, recommends a model for your machine, pulls it)
- **Every run**: asks which folder to organize and what you want to do

No venv activation, no subcommands, no flags to remember.

See [`docs/README.md`](docs/README.md) for architecture details and advanced options.

## Repository Layout

```
file-agent/    Agent source code (LangGraph nodes, tools, utils)
setup/         Guided installer — installs Ollama and picks a model for your machine
tests/data/    Built-in sample folders used with --test-run
docs/          Detailed documentation
```

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) running locally (`ollama serve`)
- Default model: `qwen2.5-coder:14b` (~9 GB). See [`docs/README.md`](docs/README.md) for lighter alternatives.
