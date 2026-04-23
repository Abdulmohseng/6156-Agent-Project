"""
Multi-model evaluation runner for the file organization agent.

Usage:
  # Evaluate two models, 1 run each (structural scores only)
  python runner.py --models qwen2.5-coder:14b qwen3:8b --no-judge

  # Full eval with LLM judge, 3 runs per model
  python runner.py --models qwen2.5-coder:14b qwen3:8b --runs-per-model 3

  # Evaluate an existing manifest without re-running the agent
  python runner.py --existing-run 2026-04-21_12-33-47 --dataset model_test

  # Use sample_flat dataset
  python runner.py --models qwen2.5-coder:14b --dataset sample_flat
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
AGENT_DIR = PROJECT_ROOT / "file-agent"
RUNS_DIR = Path.home() / ".file-agent" / "runs"
RESULTS_DIR = Path(__file__).parent / "results"

DATASET_CONFIGS = {
    "model_test": {
        "agent_flag": "--test-run",
        "agent_extra_args": [],
    },
    "sample_flat": {
        "agent_flag": "--folder",
        "agent_extra_args": [str(PROJECT_ROOT / "eval" / "datasets" / "sample_flat")],
    },
}


def _find_newest_run_id(after_timestamp: float) -> str:
    candidates = []
    for p in RUNS_DIR.iterdir():
        if p.is_dir() and (p / "manifest.json").exists():
            mtime = (p / "manifest.json").stat().st_mtime
            if mtime >= after_timestamp:
                candidates.append((mtime, p.name))
    if not candidates:
        raise RuntimeError("No new manifest found after agent run. Did the agent complete successfully?")
    candidates.sort(reverse=True)
    return candidates[0][1]


def run_agent(model: str, dataset: str, goal: str, judge_model: str) -> str:
    """Run the agent as a subprocess and return the run_id of the saved manifest."""
    cfg = DATASET_CONFIGS[dataset]
    cmd = [
        sys.executable, "agent.py", goal,
        "--model", model,
        "--yes",
        "--mode", "plan-and-act",
    ]
    if cfg["agent_flag"] == "--test-run":
        cmd.append("--test-run")
    else:
        cmd += [cfg["agent_flag"]] + cfg["agent_extra_args"]

    print(f"  Running: {' '.join(cmd)}")
    run_start = time.time()

    result = subprocess.run(
        cmd,
        cwd=str(AGENT_DIR),
        capture_output=True,
        text=True,
        timeout=900,
    )

    if result.returncode != 0:
        print(f"  STDERR: {result.stderr[-1000:]}")
        raise RuntimeError(f"Agent exited with code {result.returncode}\n{result.stdout[-2000:]}")

    return _find_newest_run_id(run_start)


def load_manifest(run_id: str) -> dict:
    with open(RUNS_DIR / run_id / "manifest.json") as f:
        return json.load(f)


def evaluate_run(run_id: str, dataset: str, use_judge: bool, judge_model: str) -> dict:
    from compare import compute_structural_scores, build_original_to_final_map, load_ground_truth

    ground_truth = load_ground_truth(dataset)
    manifest = load_manifest(run_id)

    structural = compute_structural_scores(manifest, ground_truth)
    file_map = build_original_to_final_map(manifest)

    judge_result = {}
    if use_judge:
        from judge import judge_run as _judge
        original_files = list(ground_truth["files"].keys())
        print(f"  Judging with {judge_model}...")
        judge_result = _judge(
            original_files=original_files,
            file_map=file_map,
            ground_truth=ground_truth,
            structural_scores=structural,
            judge_model=judge_model,
        )

    return {
        "run_id": run_id,
        "dataset": dataset,
        "model": manifest["metadata"]["model"],
        "goal": manifest["metadata"]["goal"],
        "timestamp": manifest["metadata"]["timestamp"],
        "structural": structural,
        "judge": judge_result,
        "agent_summary": manifest["summary"],
    }


def save_result(result: dict) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    model_slug = result["model"].replace(":", "_").replace("/", "_")
    fname = f"run_{result['run_id']}_{model_slug}.json"
    path = RESULTS_DIR / fname
    with open(path, "w") as f:
        json.dump(result, f, indent=2)
    return path


def main():
    parser = argparse.ArgumentParser(description="Multi-model evaluation runner")
    parser.add_argument("--models", nargs="+", default=["qwen2.5-coder:14b"],
                        help="Ollama models to evaluate")
    parser.add_argument("--dataset", default="model_test",
                        choices=list(DATASET_CONFIGS.keys()))
    parser.add_argument("--goal", default="Organize files semantically by content and type")
    parser.add_argument("--no-judge", action="store_true",
                        help="Skip LLM judge (structural metrics only)")
    parser.add_argument("--judge-model", default=None,
                        help="Ollama model to use as judge (default: same as agent model)")
    parser.add_argument("--runs-per-model", type=int, default=1)
    parser.add_argument("--existing-run", metavar="RUN_ID",
                        help="Evaluate an existing run_id instead of running the agent")
    args = parser.parse_args()

    all_results = []

    if args.existing_run:
        judge_model = args.judge_model or args.models[0]
        result = evaluate_run(args.existing_run, args.dataset, not args.no_judge, judge_model)
        path = save_result(result)
        all_results.append(result)
        print(f"Evaluated existing run: {path}")
    else:
        for model in args.models:
            judge_model = args.judge_model or model
            for run_num in range(args.runs_per_model):
                label = f"{model} (run {run_num + 1}/{args.runs_per_model})"
                print(f"\n=== {label} ===")
                try:
                    run_id = run_agent(model, args.dataset, args.goal, judge_model)
                    print(f"  Agent completed. run_id={run_id}")
                    result = evaluate_run(run_id, args.dataset, not args.no_judge, judge_model)
                    path = save_result(result)
                    all_results.append(result)
                    print(f"  Result saved: {path}")
                    struct = result["structural"]
                    print(f"  Coverage: {struct['coverage']:.0%}  "
                          f"Placement: {struct['placement_accuracy']:.0%}  "
                          f"Judge: {result['judge'].get('score', 'N/A')}/10")
                except Exception as e:
                    print(f"  ERROR: {e}")
                    all_results.append({"model": model, "error": str(e)})

    from report import print_comparison_table, save_comparison
    print_comparison_table(all_results)
    comparison_path = save_comparison(all_results)
    print(f"\nComparison saved: {comparison_path}")


if __name__ == "__main__":
    main()
