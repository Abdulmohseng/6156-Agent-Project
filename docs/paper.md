# NeatAgent: A Local AI Agent for Autonomous File Organization

**Abdulmohsen Alghannam**
Columbia University
afa2165@columbia.edu

---

## Synopsis

NeatAgent is a fully local, privacy-preserving AI agent that autonomously organizes files on a user's filesystem. Given a target folder, the agent reads file contents, semantically classifies each file, generates a structured plan of filesystem operations, presents it to the user for approval, and executes it step by step — all without sending data to any cloud service. The system is built on a PLAN-AND-ACT architecture implemented with LangGraph, using Ollama to run quantized open-source LLMs locally. This paper describes the design, implementation, and evaluation of NeatAgent, including a comparison of three local models (qwen2.5-coder:14b, qwen3:8b, llama3.2:3b) across two labeled datasets using structural placement accuracy and an LLM-as-judge quality score.

---

## Abstract

AI agents are increasingly capable of performing complex, multi-step tasks in real environments. However, most deployed agent systems depend on proprietary cloud APIs, raising concerns around privacy, cost, and availability. This paper presents NeatAgent, a terminal-based file organization agent that runs entirely on consumer hardware using local LLMs served by Ollama. The agent implements a PLAN-AND-ACT loop with a Reflector node for error recovery, and a mapping-based planner design that structurally eliminates hallucinated file references. We evaluate the system across three models and two datasets, finding that all models achieve high file coverage but differ in semantic placement quality. We further show that the mapping-based planner eliminates hallucination compared to the prior step-based approach. Our results suggest that for constrained, well-scoped agentic tasks, small local models (7–14B parameters) can achieve practical performance without cloud dependency.

---

## 1. Introduction

File management is a universal but tedious task. Most users accumulate disorganized downloads, documents, and media that resist manual sorting. While rule-based tools (e.g., Hazel, Automator) exist, they require explicit user-defined rules and cannot generalize to new file types or semantically ambiguous filenames. AI agents offer a natural alternative: given a goal in plain language, an agent can inspect files, reason about their content, and take appropriate actions.

The dominant paradigm for capable AI agents relies on cloud-hosted LLMs such as GPT-4 or Claude. This creates barriers for users with privacy requirements, limited connectivity, or cost constraints. Recent advances in open-weight model quantization (via tools like Ollama) make it feasible to run capable LLMs locally on a MacBook or consumer PC. NeatAgent explores whether a locally-hosted LLM agent can perform meaningful file organization with practical accuracy.

The system is also a concrete instantiation of the PLAN-AND-ACT architectural pattern, which separates planning from execution to improve reliability on multi-step tasks. We implement the full loop: planner, executor, and reflector, connected through a LangGraph state machine. The planner uses a novel mapping-based output format that makes hallucination of non-existent files structurally impossible.

### 1.1 What the Reader Will Learn

Readers of this paper will understand:

- How to design a PLAN-AND-ACT agent loop using LangGraph for multi-step filesystem tasks
- Why mapping-based planner output eliminates hallucination compared to step-based output
- How to run and evaluate local LLMs for agentic tasks using Ollama
- How to build a structural evaluation pipeline (placement accuracy, LLM-as-judge) for file organization agents
- Practical tradeoffs between model size, inference speed, and semantic classification quality

### 1.2 Background

#### 1.2.1 AI Agents

AI agents are autonomous systems that perceive their environment, reason about it using an LLM, and take actions through tools. Unlike a simple chatbot, an agent operates in a loop: it observes state, selects a tool or action, executes it, and integrates the result into its next decision. Agents typically have access to memory (short-term context and long-term persistent storage), a set of tools, and a planning mechanism for decomposing goals into steps.

#### 1.2.2 PLAN-AND-ACT

The PLAN-AND-ACT framework separates the planning and execution phases of agentic tasks. Rather than generating and executing one action at a time, the agent first produces a complete plan, which is then executed step by step. This separation improves traceability (users can inspect the plan before execution) and reduces context drift during long execution sequences. NeatAgent implements a variant of this pattern where the plan is a deterministic list of filesystem operations generated from an LLM-produced mapping.

#### 1.2.3 LangGraph

LangGraph is a library for building stateful, graph-structured agent workflows. Nodes in the graph represent agent components (planner, executor, reflector), and edges define control flow between them including conditional branches. All nodes communicate through a shared `AgentState` TypedDict, making state transitions explicit and debuggable.

#### 1.2.4 Local LLM Inference with Ollama

Ollama is an open-source tool that serves quantized open-weight LLMs (LLaMA, Qwen, Mistral, etc.) locally via a REST API compatible with standard LLM client libraries. It enables agent development without cloud API keys or data egress, making it suitable for privacy-sensitive tasks like file organization.

#### 1.2.5 LLM Hallucination in Agentic Contexts

Hallucination — the generation of plausible but factually incorrect output — is a well-known failure mode in LLMs. In agentic settings, hallucination is particularly dangerous because the agent may take irreversible actions based on invented facts. For file organization, this manifests as the planner generating steps for files that do not exist in the target folder, leading to failed operations and wasted time.

---

## 2. Related Work

### 2.1 PLAN-AND-ACT for Long-Horizon Tasks

<!-- Discuss the PLAN-AND-ACT paper by Erdogan et al. (2025) and how it motivates the architecture -->

The challenge of long-horizon task completion in AI agents has driven research into explicit planning phases. PLAN-AND-ACT [CITATION] argues that interleaving planning and execution causes agents to lose track of the main goal, drifting into unnecessary sub-tasks. By separating phases, the agent produces a readable artifact (the plan) that both guides execution and enables human oversight.

NeatAgent adopts this pattern for filesystem operations: the planner produces a complete step list before any file is touched, and the user can review and approve or reject it. This human-in-the-loop checkpoint is particularly important for destructive operations (moves and renames) where mistakes are hard to undo.

### 2.2 Hallucination and Structural Constraints

<!-- Discuss how mapping-based output relates to grounding and constrained decoding research -->

Hallucination in structured output tasks can be mitigated by constraining the output format. Rather than allowing the LLM to freely generate action steps (which can reference invented filenames), NeatAgent's planner asks the model to output a mapping keyed by the exact filenames provided in the prompt. Python code then generates all steps from this mapping. Any hallucinated key is filtered out before step generation, making it structurally impossible for a fabricated filename to reach the executor.

### 2.3 Local LLMs for Agentic Tasks

<!-- Discuss related work on using smaller/local models for agents, efficiency tradeoffs -->

Most agentic benchmarks (SWE-bench, WebArena, etc.) use frontier models (GPT-4, Claude) as the backbone. Relatively little work evaluates local, quantized models for practical agent tasks. NeatAgent contributes an evaluation across three open-weight models of varying sizes (3B, 8B, 14B parameters) on a concrete, real-world task.

### 2.4 Evaluation of File Organization Agents

<!-- Discuss lack of prior work in this specific area and how we define ground truth -->

To our knowledge, no prior work has established a standardized evaluation benchmark for file organization agents. We introduce two labeled datasets (model_test: 10 files, sample_flat: 24 files) with ground truth folder assignments and alias sets that allow flexible matching of semantically equivalent folder names.

---

## 3. System Design

### 3.1 Architecture Overview

NeatAgent is implemented as a LangGraph state machine with three nodes connected by conditional edges:

```
Planner → [User Confirm] → Executor (loops) → Reflector (on failure) → retry / skip / replan
```

All nodes communicate through a shared `AgentState` TypedDict. The graph loops the executor node via a conditional edge (not a Python for-loop), advancing one step per graph invocation and enabling the reflector to intercept failures between steps.

<!-- Insert architecture diagram here -->

### 3.2 Planner Node

The planner lists all files in the target folder, collects content previews for ambiguous filenames (text files via direct read, PDFs/DOCX via pdfplumber/python-docx, images via vision LLM), and sends a single LLM prompt asking for a JSON mapping:

```json
{
  "<exact_filename>": {
    "folder": "<SemanticFolderName>",
    "rename": "<new_stem_or_null>"
  }
}
```

Python code converts this mapping to a deterministic step list (create folders → rename if needed → move). The `_validate_mapping` function strips hallucinated keys and fills missing files with `folder: "Other"` before any steps are generated.

### 3.3 Executor Node

The executor runs one step per invocation, calling the appropriate tool (`create_folder`, `move_file`, `rename_file`). It supports three modes: normal execution, dry-run (plan display only), and safe mode (per-step user confirmation). A wall-clock timeout (400 seconds) prevents indefinite runs on large folders.

### 3.4 Reflector Node

The reflector fires only on step failure. It auto-skips known unretryable errors (file not found, already exists) and asks the LLM to choose `retry | skip | replan` for recoverable failures. After three retries or three replans, it force-skips to prevent infinite loops.

### 3.5 Tools

| Tool | Description |
|------|-------------|
| `list_files` | Returns file metadata for all direct children of a folder |
| `read_file` | Format-aware reader: text, PDF (pdfplumber), DOCX (python-docx), images (Ollama vision) |
| `create_folder` | Creates a subdirectory; no-ops if it already exists |
| `move_file` | Moves a file; appends `_1`, `_2` on collision |
| `rename_file` | Renames a file in place; appends suffix on collision |

### 3.6 Hallucination Prevention

<!-- Describe the before/after comparison: step-based (63 steps, 40 failures) vs mapping-based (clean runs) -->

The original step-based planner asked the LLM to generate executable action steps directly. On a 10-file folder, this produced 63 steps with 40 failures — the model invented files like `file11.pdf` through `file52.kt` via context drift. The mapping-based redesign eliminates this: the LLM only outputs keys, and keys are validated against the real file listing before any steps are built.

---

## 4. Evaluation

### 4.1 Datasets

| Dataset | Files | Source | Ground Truth |
|---------|-------|--------|--------------|
| model_test | 10 | Manually created; generic filenames (file1.txt–file10.csv) | `eval/ground_truth/model_test.json` |
| sample_flat | 24 | Flattened from `tests/data/sample/`; mixed descriptive and generic names | `eval/ground_truth/sample_flat.json` |

Ground truth entries include `expected_folder`, `folder_aliases` (synonyms accepted as correct), `expected_name` (for rename evaluation), and `content_hint`.

### 4.2 Metrics

**Coverage** — fraction of files moved out of the root (any folder). Measures whether the agent completed the task at all.

**Placement Accuracy** — fraction of files placed in the correct folder (exact match or alias match, case-insensitive). Measures semantic correctness.

**LLM-as-Judge Score (1–10)** — a local Ollama model evaluates the agent's output structure against ground truth and assigns a holistic quality score with reasoning.

### 4.3 Experimental Setup

<!-- Describe runner.py, --yes flag, subprocess invocation, manifest loading -->

The evaluation runner (`eval/runner.py`) invokes the agent as a subprocess with `--test-run --yes` flags, finds the newest manifest in `~/.file-agent/runs/`, computes structural scores via `eval/compare.py`, and optionally calls the judge via `eval/judge.py`. All results are saved as JSON and rendered as a Rich terminal table via `eval/report.py`.

### 4.4 Results

| Model | Coverage | Placement Accuracy | Judge Score | Duration |
|-------|----------|--------------------|-------------|----------|
| qwen2.5-coder:14b | 100% | ~60% | ~5/10 | ~90s |
| qwen3:8b | 100% | ~50% | ~4/10 | ~70s |
| llama3.2:3b | 100% | ~40% | ~4/10 | ~40s |

<!-- Update with actual numbers from eval/results/ after re-running with PDF fix -->

**Hallucination fix impact:**

| Planner version | Steps generated | Step failures | Hallucinated files |
|-----------------|-----------------|---------------|--------------------|
| Step-based (original) | 63 | 40 | ~42 |
| Mapping-based (current) | 13 | 0 | 0 |

---

## 5. Discussion

### 5.1 Model Size vs. Accuracy

<!-- Discuss that 14B doesn't dominate 8B in all cases, and why -->

Larger models do not consistently outperform smaller ones on this task. qwen2.5-coder:14b achieves higher placement accuracy than qwen3:8b despite being a different model family, suggesting that instruction-following and JSON output quality matter more than raw parameter count for this task.

### 5.2 Persistent Misclassifications

<!-- Discuss PDFs, CSVs being sent to Data instead of correct folders, and how PDF fix addresses it -->

Before the PDF content preview fix, image-based PDFs with generic filenames (file4.pdf, file5.pdf) were consistently classified as "Data" because the planner had no content signal. After replacing the test PDFs with text-based versions and adding the document preview branch, the planner receives "INVOICE" and "Annual Health Report" content hints, enabling correct classification.

### 5.3 LLM-as-Judge Limitations

<!-- Discuss subjectivity of the judge score and inter-model agreement -->

The local LLM judge score is inherently subjective and dependent on the judge model's own classification preferences. Scores of 4–5/10 do not necessarily indicate poor performance — the judge may penalize folder names that differ from its own preferences (e.g., "Invoices" vs "Finance") even when both are semantically reasonable.

### 5.4 Human-in-the-Loop Value

<!-- Discuss the plan confirmation step and safe mode -->

The plan confirmation step proved to be one of the most practically valuable design decisions. Users can catch misclassifications before any file is moved, and safe mode allows step-by-step approval for high-stakes folders. This pattern aligns with findings from vertical AI agent research that human oversight checkpoints significantly improve user trust in autonomous systems.

---

## 6. Conclusion

NeatAgent demonstrates that a locally-hosted LLM agent can perform meaningful file organization without cloud dependency. The PLAN-AND-ACT architecture with a mapping-based planner eliminates hallucination as a failure class, and the human-in-the-loop confirmation step makes the system practical for real-world use. Smaller models (3B–14B) achieve full coverage but vary in semantic placement quality, suggesting that prompt engineering and output format constraints matter more than model size for this task.

Future work includes: PDF-to-image rendering for scanned PDFs, multi-run averaging for more reliable evaluation, user studies measuring satisfaction with folder naming choices, and extension to vision-only inputs (screenshot-based organization).

### 6.1 What I Learned

Building NeatAgent revealed how fragile step-based LLM output is for agentic tasks: the same model that correctly classifies 10 files can hallucinate 42 fictional ones in the same prompt if the output format is unconstrained. Switching to a mapping format — a small prompt engineering change — eliminated the problem entirely. This reinforced the principle that architectural constraints can substitute for model capability, and that simpler, well-scoped designs outperform complex ones that rely on the model to self-regulate.

Evaluating the agent also proved harder than building it. Defining ground truth for a subjective task (what is the "right" folder for a file?) requires alias sets and human judgment calls that a purely automated metric cannot capture. The LLM-as-judge approach helps but introduces its own biases.

---

## References

[1] Lutfi Eren Erdogan et al. "PLAN-AND-ACT: Improving Planning of Agents for Long-Horizon Tasks." arXiv:2503.09572, 2025.

[2] Anthropic. "Building Effective Agents." Engineering Blog, 2024. https://www.anthropic.com/engineering/building-effective-agents

[3] Taicheng Guo et al. "Large Language Model based Multi-Agents: A Survey of Progress and Challenges." arXiv:2402.01680, 2024.

[4] Xinyi Hou et al. "Model Context Protocol (MCP): Landscape, Security Threats, and Future Research Directions." arXiv:2503.23278, 2025.

[5] Fouad Bousetouane. "Agentic Systems: A Guide to Transforming Industries with Vertical AI Agents." arXiv:2501.00881, 2025.

[6] Akari Asai et al. "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection." arXiv:2310.11511, 2023.

[7] Darren Edge et al. "From Local to Global: A Graph RAG Approach to Query-Focused Summarization." arXiv:2404.16130, 2024.

[8] Hanchao Liu et al. "WorkTeam: Constructing Workflows from Natural Language with Multi-Agents." arXiv:2503.22473, 2025.

[9] Chaoyun Zhang et al. "API Agents vs. GUI Agents: Divergence and Convergence." arXiv:2503.11069, 2025.

---

## Appendix

### A. Reproducing the Evaluation

```bash
# 1. Install dependencies and pull models
pip install -r requirements.txt
ollama pull qwen2.5-coder:14b
ollama pull qwen3:8b
ollama pull llama3.2:3b

# 2. Run evaluation across all three models
cd eval
python runner.py --models qwen2.5-coder:14b qwen3:8b llama3.2:3b --dataset model_test

# 3. View comparison table
python report.py eval/results/run_*.json
```

### B. Project Repository Layout

```
6156-Agent-Project/
├── file-agent/          # Agent source (planner, executor, reflector, tools)
├── eval/                # Evaluation pipeline
│   ├── ground_truth/    # Labeled datasets (JSON)
│   ├── datasets/        # Physical test files
│   └── results/         # Run outputs (gitignored)
├── tests/data/          # Test input folders
├── docs/                # Reports and paper
├── setup/               # First-time setup wizard
├── run.py               # Universal entry point
└── requirements.txt
```

### C. Ground Truth Schema

```json
{
  "file4.pdf": {
    "expected_folder": "invoices",
    "folder_aliases": ["Finance", "Bills", "Receipts"],
    "expected_name": null,
    "content_hint": "Invoice from Acme Corp, March 2026"
  }
}
```
