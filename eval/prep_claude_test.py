"""
Prepare a fresh copy of a dataset for an external organizer (e.g. Claude Code desktop).

Creates a flat folder with all the test files copied into it, then prints
the exact prompt to give Claude Code and the eval command to run afterward.

Usage:
  python eval/prep_claude_test.py --dataset model_test
  python eval/prep_claude_test.py --dataset sample_flat
"""

import argparse
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent

DATASET_SOURCES = {
    "model_test":  ROOT / "tests" / "data" / "model_test",
    "sample_flat": ROOT / "eval" / "datasets" / "sample_flat",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="model_test",
                        choices=list(DATASET_SOURCES.keys()))
    args = parser.parse_args()

    source = DATASET_SOURCES[args.dataset]
    if not source.exists():
        print(f"Error: source folder not found: {source}")
        raise SystemExit(1)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest = ROOT / "data" / "claude_code_test" / f"{args.dataset}_{ts}"
    dest.mkdir(parents=True, exist_ok=True)

    # Copy only flat files (no subfolders) from source
    copied = []
    for f in source.iterdir():
        if f.is_file():
            shutil.copy2(f, dest / f.name)
            copied.append(f.name)

    print(f"\n✓ Copied {len(copied)} files to:\n  {dest}\n")
    print("Files:")
    for name in sorted(copied):
        print(f"  {name}")

    print(f"""
─────────────────────────────────────────────────────────
STEP 1 — Give Claude Code (desktop) this prompt:
─────────────────────────────────────────────────────────

  Organize the files in this folder into meaningful semantic
  subfolders based on their content. Rename any file with a
  generic or unclear name to a short descriptive snake_case
  name that reflects what the file actually contains.

  Folder: {dest}

─────────────────────────────────────────────────────────
STEP 2 — After Claude Code finishes, run this to evaluate:
─────────────────────────────────────────────────────────

  cd {ROOT}
  python eval/eval_folder.py \\
      --folder "{dest}" \\
      --dataset {args.dataset} \\
      --organizer claude-code \\
      --save

─────────────────────────────────────────────────────────
""")


if __name__ == "__main__":
    main()
