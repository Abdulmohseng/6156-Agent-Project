# Final Report — Agentic File System Organizer

**Abdulmohsen Alghannam — afa2165**
**Course: COMS 6156 — Topics in Software Engineering**

---

## Table of Contents

1. [What Was Delivered and Where](#1-what-was-delivered-and-where)
2. [External Materials Built On and Compared To](#2-external-materials-built-on-and-compared-to)
3. [Novel, Innovative, Interesting](#3-novel-innovative-interesting)
4. [Value and Availability to Target User Community](#4-value-and-availability-to-target-user-community)
5. [Research Questions and Answers](#5-research-questions-and-answers)
6. [Methodology and Metrics](#6-methodology-and-metrics)
7. [Datasets and Benchmarks](#7-datasets-and-benchmarks)
8. [Results and Findings](#8-results-and-findings)
9. [Is This Work Reproducible](#9-is-this-work-reproducible)
10. [Who Did What](#10-who-did-what)
11. [What I Learned](#11-what-i-learned)
12. [Planned But Didn't Do / Problems Encountered](#12-planned-but-didnt-do--problems-encountered)

---

## 1. What Was Delivered and Where

**Repository:** [github.com/Abdulmohseng/6156-Agent-Project](https://github.com/Abdulmohseng/6156-Agent-Project)

### Deliverables

| Deliverable | Location |
|-------------|----------|
| Project proposal | `docs/project_proposal.pdf` |
| Progress report | `docs/NeatAgent.pdf` / `docs/NeatAgent.docx` |
| Final report (this document) | `docs/final_report.md` |
| Agent source code | `file-agent/` |
| Universal entry point | `run.py` |
| First-time setup wizard | `setup/` |
| Evaluation pipeline | `eval/` |
| Labeled test datasets | `tests/data/model_test/`, `eval/datasets/sample_flat/` |
| Ground truth labels | `eval/ground_truth/model_test.json`, `eval/ground_truth/sample_flat.json` |
| Ground truth reference | `tests/data/model_test/organized_model_test/` |
| Architecture documentation | `docs/README.md` |
| Build and run documentation | `README.md` |

### What the system does

The Agentic File System Organizer is a terminal-based AI agent that autonomously organizes files in a local folder. Given a folder path, it reads file contents, classifies each file semantically, generates a plan of filesystem operations, presents the plan to the user for approval, and executes it step by step. All inference runs locally via [Ollama](https://ollama.com) — no API key, no data sent to a cloud service.

---

## 2. External Materials Built On and Compared To

### Frameworks and Libraries

| Component | External Artifact | Purpose |
|-----------|-----------------|---------|
| Agent framework | [LangGraph](https://github.com/langchain-ai/langgraph) | State machine wiring Planner → Executor → Reflector nodes |
| LLM inference | [Ollama](https://ollama.com) | Local model serving via REST API |
| LLM client | [langchain-ollama](https://pypi.org/project/langchain-ollama/) | `ChatOllama` wrapper used in Planner and Reflector nodes |
| LangChain core | [langchain-core](https://pypi.org/project/langchain-core/) | Message types and tool protocol |
| PDF reading | [pdfplumber](https://github.com/jsvine/pdfplumber) | Text extraction from PDF files for content classification |
| DOCX reading | [python-docx](https://python-docx.readthedocs.io) | Text extraction from Word documents |
| Terminal UI | [rich](https://github.com/Textualize/rich) | Plan review table, colored step output, summary panel |
| HTTP | [requests](https://docs.python-requests.org) | Ollama health check and generate API calls |

### Related Work and Inspiration

- **Claude Computer Use / Claude Cowork (Anthropic):** Mentioned in the project proposal as a related commercial product. The key distinction is that this project is fully local — no Anthropic or OpenAI API is called, and no files are shared with any external service.
- **ReAct (Yao et al., 2022):** The PLAN-AND-ACT architecture separates planning from acting, inspired by the ReAct agent pattern in which reasoning and acting are interleaved.
- **Reflexion (Shinn et al., 2023):** The Reflector node's retry/skip/replan decision loop is inspired by the Reflexion pattern of verbal self-reflection after failure.

### Alternative Systems Compared

The evaluation compares three alternative systems running the same agent architecture:

| System | Model | Parameters |
|--------|-------|-----------|
| **System A** (primary) | `qwen2.5-coder:14b` | 14B, strong JSON reliability |
| **System B** | `qwen3:8b` | 8B, faster inference |
| **System C** (baseline) | `llama3.2:3b` | 3B, fastest, least capable |

---

## 3. Novel, Innovative, Interesting

### Fully Local and Private

Every competing product in this space (Claude Computer Use, ChatGPT file actions, Windows Recall) sends file contents to cloud APIs. This system runs entirely on-device. Files never leave the machine — a meaningful distinction for personal documents, medical records, financial files, or anything sensitive.

### PLAN-AND-ACT with Human-in-the-Loop

The architecture separates planning from execution so the LLM generates a complete, reviewable plan before touching any file. The user sees every proposed action in a formatted table and can abort before a single file moves. This is stronger than a chat-based assistant that acts while it talks.

### Mapping-Based Planner to Eliminate Hallucination

A key technical innovation developed during the project: the original step-based planner asked the LLM to output ~60 executable steps, which caused the model to hallucinate files that did not exist (e.g. `file11.pdf` through `file52.kt` for a 10-file folder). The root cause was context drift — the file listing appeared early in the prompt and the model lost track of it while generating a long step list.

The solution was to change what the LLM outputs entirely. Instead of steps, the planner now asks for a compact **mapping**:

```json
{
  "file1.txt": {"folder": "Finance", "rename": "invoice_acme_feb2026"},
  "file9.csv": {"folder": "Data",    "rename": null}
}
```

Step generation is then handled deterministically in Python. Any key not matching a real filename is dropped before a single step is built — hallucination is structurally impossible. This also reduced the planner's token budget from 8,192 to 2,048, making it noticeably faster.

### LLM-as-Judge Evaluation with Local Models

The evaluation pipeline uses a local Ollama model as a semantic quality judge, scoring organization quality 1–10 with structured reasoning. This enables automated qualitative evaluation without any cloud API calls, consistent with the project's offline design principle.

---

## 4. Value and Availability to Target User Community

### Target Users

Anyone who accumulates disorganized files — students, researchers, developers, office workers. The proposal was motivated by a personal problem: after work sessions, desktop and download folders fill with scattered, generically named files.

### Availability

- **Free:** No subscription, no API cost, no per-use fee.
- **Private:** No files leave the machine.
- **Local hardware:** Runs on Apple Silicon (M-series) Macs. Lighter models (`llama3.2:3b`) work on machines with 8 GB RAM; the default (`qwen2.5-coder:14b`) requires ~16 GB.
- **Open source:** Repository is public on GitHub.
- **Cross-platform:** Python + Ollama run on macOS, Linux, and Windows.

### Ease of Use

The `run.py` entry point handles first-time setup automatically (installs Ollama, recommends and pulls a model for your hardware) and then runs the agent interactively. A new user runs exactly one command: `python run.py`.

---

## 5. Research Questions and Answers

**RQ1: Can a fully local LLM agent reliably organize personal files by semantic content?**

*Partially yes.* Across all three tested models, 100% of files were moved out of the root (no files left behind). Placement accuracy into the correct semantic folder ranged from 50% to 60% on a 10-file benchmark. The primary failure mode was classifying PDFs — without reading their text content, models default to a generic "Data" folder rather than inferring "invoices" or "health." For text files with readable content, accuracy was high.

**RQ2: Does model size correlate with organization quality on this task?**

*Not strongly.* The 3B model (`llama3.2:3b`) tied the 14B model (`qwen2.5-coder:14b`) on placement accuracy (both 60%) while running approximately 3× faster. The 8B model (`qwen3:8b`) scored slightly lower (50%) despite being mid-range in size. This suggests that for short, structured JSON output like the mapping format, smaller models generalize adequately.

**RQ3: Does the mapping-based planning approach eliminate hallucinated file steps?**

*Yes.* Before the fix, a 10-file folder produced a 63-step plan with 40 step failures (hallucinated files like `file11.pdf` through `file52.kt`). After switching to mapping-based planning, the same folder produces a correctly-sized plan with 0 failures.

---

## 6. Methodology and Metrics

### Agent Architecture

The agent uses a **PLAN-AND-ACT** loop implemented as a LangGraph state machine:

```
list_files → Planner (LLM: mapping output)
           → human reviews plan
           → Executor (loops, one step per invocation)
           → on failure → Reflector (LLM: retry | skip | replan)
           → on replan → Planner
```

The Planner reads all file metadata and inline content previews for ambiguous text files, calls the LLM once to produce a `{filename → {folder, rename}}` mapping, then generates executable steps in Python. The Executor runs one step per graph invocation. The Reflector makes a lightweight LLM call (50 tokens max) to decide recovery strategy on failure.

### Evaluation Metrics

| Metric | Definition |
|--------|-----------|
| **Coverage** | Fraction of files moved out of the root folder (not left behind) |
| **Placement Accuracy** | Fraction of files placed in a folder matching the ground truth label or any accepted synonym |
| **Judge Score** | 1–10 semantic quality rating from a local LLM judge evaluating folder naming, file naming, and completeness |
| **Duration** | Wall-clock time for a complete run in seconds |
| **Steps Failed** | Number of executor steps that produced an error |

Placement accuracy uses a synonym list per file (e.g. `invoices`, `Finance`, `Bills` are all accepted for an invoice file) to avoid penalizing valid naming variations.

### AI Tools Used

| Tool | Usage | Configuration |
|------|-------|--------------|
| **Claude Code (Anthropic)** | Primary development assistant — code generation, debugging, architecture design, documentation writing, evaluation pipeline implementation | Default `claude-sonnet-4-6` model via Claude Code CLI |
| **Ollama + qwen2.5-coder:14b** | Agent's default planning and reflection model at runtime | Local inference, temperature=0 |
| **Ollama + qwen3-vl:8b** | Vision model for describing image files | Local inference |
| **Ollama + qwen2.5-coder:14b** | LLM-as-judge in evaluation pipeline | Local inference, temperature=0 |

Claude Code was used extensively throughout development for: implementing the LangGraph state machine, writing the mapping-based planner, designing the evaluation pipeline, fixing the hallucination bug, and writing documentation. All generated code was reviewed, tested, and modified as needed.

---

## 7. Datasets and Benchmarks

Two labeled datasets are included in the repository:

### `model_test` (primary benchmark)

- **Location:** `tests/data/model_test/` (input), `tests/data/model_test/organized_model_test/` (reference organization)
- **Ground truth:** `eval/ground_truth/model_test.json`
- **Size:** 10 files with generic names (`file1.txt` through `file10.csv`)
- **File types:** 3 text files (.txt), 2 PDFs (.pdf), 3 images (.jpg), 2 CSVs (.csv)
- **Content:** Invoice, book reading log, gym log, health report, sensor data, sales data, photographs

Each file entry in the ground truth JSON specifies an expected folder, accepted synonym folders, and a content hint:

```json
"file1.txt": {
  "expected_folder": "invoices",
  "folder_aliases": ["Finance", "finance", "Bills", "billing"],
  "content_hint": "Invoice #INV-2026-0341 from Abdul Design Studio to Acme Corp"
}
```

### `sample_flat` (secondary benchmark)

- **Location:** `eval/datasets/sample_flat/` (input, 24 files flattened from organized subfolders)
- **Ground truth:** `eval/ground_truth/sample_flat.json`
- **Size:** 24 files with a mix of generic and descriptive names
- **File types:** text, PDF, CSV, DOCX, images
- **Content:** Finance, Health, Medical, Work, Travel, Recipes, Study, Personal files

### Why these datasets

Both datasets are small enough to run end-to-end in under 2 minutes per model but diverse enough to test classification across the main semantic categories the agent targets. The `model_test` set is specifically designed with generic filenames (`file1.txt`) to test whether the agent reads content rather than inferring from filenames.

---

## 8. Results and Findings

### Quantitative Results — `model_test` dataset

| Model | Coverage | Placement Acc. | Judge Score | Duration | Steps Failed |
|-------|----------|---------------|-------------|----------|-------------|
| `qwen2.5-coder:14b` | **100%** | **60%** | 5/10 | ~62s | 0 |
| `qwen3:8b` | **100%** | 50% | 4/10 | ~38s | 0 |
| `llama3.2:3b` | **100%** | **60%** | 5/10 | **~22s** | 0 |

### Per-File Breakdown (qwen2.5-coder:14b)

| File | Content | Expected | Actual | Match |
|------|---------|----------|--------|-------|
| file1.txt | Invoice | invoices | Finance | ✓ |
| file2.txt | Book reading log | personal_logs | Personal | ✓ |
| file3.txt | Gym log | health | Health | ✓ |
| file4.pdf | Invoice PDF | invoices | Data | ✗ |
| file5.pdf | Health report PDF | health | Data | ✗ |
| file6.jpg | Smartphone photo | photos | Personal | ✗ |
| file7.jpg | Coffee photo | photos | Food | ✗ |
| file8.jpg | Landscape photo | photos | Nature | ✗ |
| file9.csv | Sensor data | datasets | Data | ✓ |
| file10.csv | Sales data | datasets | Data | ✓ |

### Key Findings

**1. Coverage is solved.** After the mapping-based planner rewrite, all models move 100% of files with 0 step failures. The previous hallucination bug caused up to 40 step failures per run on the same dataset.

**2. PDFs are the hardest.** `file4.pdf` (an invoice) and `file5.pdf` (a health report) both land in "Data" across all models. Without reading PDF text content, the model only knows the extension — and `.pdf` is ambiguous. Integrating PDF text extraction into the planner's content preview (already built in `read_file`) would likely fix this.

**3. Photos are consistently miscategorized.** Images without vision model descriptions go to personality-based folders ("Personal", "Food", "Nature") rather than a unified "Photos" folder. This is actually semantically reasonable — the model is classifying by content — but doesn't match the ground truth which expects a single "photos" folder.

**4. Model size doesn't predict accuracy.** `llama3.2:3b` matches `qwen2.5-coder:14b` at 60% while being 3× faster. For the compact mapping format, instruction-following on short structured JSON appears to be the deciding factor, not raw parameter count.

**5. Speed-accuracy tradeoff.** `llama3.2:3b` at ~22s vs `qwen2.5-coder:14b` at ~62s with identical accuracy suggests the smaller model is the better practical choice for most users.

### Before vs After Hallucination Fix

| Metric | Before (step-based planner) | After (mapping-based planner) |
|--------|---------------------------|------------------------------|
| Plan steps generated | 63 | 24 |
| Steps failed | 40 | 0 |
| Files successfully moved | 10 | 10 |
| Hallucinated filenames | ~43 | 0 |

---

## 9. Is This Work Reproducible

**Yes.** The repository includes everything needed to reproduce the evaluation from scratch on any machine with an Apple Silicon Mac (or any machine running Ollama).

### Steps to reproduce

```bash
# 1. Clone the repository
git clone https://github.com/Abdulmohseng/6156-Agent-Project.git
cd 6156-Agent-Project

# 2. Install Ollama and pull models
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5-coder:14b
ollama pull qwen3:8b
ollama pull llama3.2:3b

# 3. Install Python dependencies
cd file-agent && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && cd ..

# 4. Run evaluation (no judge — fast)
python3 eval/runner.py --models qwen2.5-coder:14b qwen3:8b llama3.2:3b --no-judge

# 5. Run with LLM judge
python3 eval/runner.py --models qwen2.5-coder:14b qwen3:8b llama3.2:3b
```

Results are saved to `eval/results/` as JSON. The ground truth labels are in `eval/ground_truth/`. All evaluation code is deterministic (Python filesystem comparison) except the LLM judge, which uses `temperature=0` to minimize variability.

**Hardware note:** The default model (`qwen2.5-coder:14b`) requires approximately 10 GB of RAM. `llama3.2:3b` runs on machines with 8 GB RAM. All results reported here were obtained on an Apple M-series Mac.

---

## 10. Who Did What

This is an individual project. All design, implementation, debugging, and evaluation was done by Abdulmohsen Alghannam (afa2165).

**Claude Code (Anthropic)** was used as a development assistant throughout the project. Specific uses:
- Implementing the LangGraph state machine boilerplate (`graph.py`, initial `state.py`)
- Writing the evaluation pipeline (`eval/compare.py`, `eval/judge.py`, `eval/runner.py`, `eval/report.py`)
- Diagnosing and fixing the hallucination bug (identifying that step-based output caused context drift, designing the mapping-based approach)
- Writing the README and this report (first draft)
- Code review and refactoring suggestions

All Claude Code outputs were reviewed, tested against the actual running system, and modified where needed. The core architecture decisions (PLAN-AND-ACT, LangGraph, local-only inference, mapping-based planning) were made by the student.

---

## 11. What I Learned

Building this project taught me several things I did not expect going in:

**Local LLMs are more capable than I assumed — and more fragile than I hoped.** `qwen2.5-coder:14b` produces excellent structured JSON output and understands semantic file categories well. But it hallucinates freely when given too much latitude in its output format. The key insight was that prompt engineering alone is insufficient — the output schema has to make hallucination structurally difficult. Switching from "write me a list of steps" to "fill in this mapping keyed by the exact filenames I gave you" was the single most impactful change in the project.

**Agent architecture matters as much as model choice.** The ReAct-style loop I started with (plan, act, reflect) works, but the separation of planning from execution is critical. When the LLM plans and acts in the same call, it drifts. Keeping the Planner as a pure "think first" node and the Executor as a pure "act" node made the system much more reliable.

**Evaluation is hard to design well.** My initial plan was to measure "organization accuracy" — but accuracy against what ground truth? The ground truth itself is subjective. A gym log going to "Health" vs "Fitness" vs "Personal" are all defensible. I ended up using a synonym-based matcher and an LLM judge to handle this ambiguity, but the results are still sensitive to how the ground truth is labeled.

**The smallest viable model is often the right choice.** I assumed the 14B model would substantially outperform the 3B model. It didn't — they tied on placement accuracy at 60%. The lesson is to measure before assuming, and to consider the user's hardware constraints as a first-class concern.

---

## 12. Planned But Didn't Do / Problems Encountered

### Planned but not completed

| Feature | Status | Notes |
|---------|--------|-------|
| User studies on participants' machines | Not done | Proposed in initial proposal; logistically difficult to arrange in the project timeline |
| Vision model evaluation | Partial | `qwen3-vl:8b` is integrated in the code but not evaluated quantitatively — image descriptions were unavailable during eval runs |
| PDF text extraction in planner | Not done | `read_file` extracts PDF text, but the planner currently only reads text files inline; integrating PDF content previews would likely fix the photo/invoice misclassification |
| Usability/satisfaction scoring | Not done | Proposed a usability dimension alongside accuracy and efficiency; dropped in favor of LLM-as-judge for the scope of this project |
| Multiple runs per model for averaging | Partial | Single runs reported; variability across runs is unquantified |

### Problems encountered

**Hallucination bug (resolved).** The most significant problem was the step-based planner hallucinating dozens of non-existent filenames. A 10-file folder produced 63 plan steps with 40 failures. Root cause: the LLM generated a long list of steps and lost track of the original file listing due to context drift. Resolved by rewriting the planner to output a compact mapping instead of steps, with Python generating all executable steps deterministically.

**Interactive confirmation in evaluation.** The agent's plan confirmation prompt (`Proceed with N steps? [y/n]`) blocked automated evaluation runs. Resolved by adding a `--yes` flag to `agent.py` that auto-approves the plan for scripted/eval use.

**Ground truth subjectivity.** Defining "correct" organization is inherently ambiguous. A file labeled as belonging to "invoices" might reasonably go to "Finance" or "Bills". The synonym-based matcher in `eval/compare.py` partially addresses this, but the ground truth itself is one person's judgment.

**Model consistency.** LLMs at `temperature=0` are not fully deterministic across runs (hardware, batching, and Ollama version all affect outputs). Single-run results should be interpreted with this caveat.
