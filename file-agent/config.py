"""
Central configuration for the File Organization Agent.

All tunable constants live here. Import from this module instead of
hard-coding values in individual files.
"""

from pathlib import Path

# ── Model ──────────────────────────────────────────────────────────────────────
DEFAULT_MODEL = "qwen2.5-coder:14b"

# ── Goal ───────────────────────────────────────────────────────────────────────
DEFAULT_GOAL = (
    "Organize files into meaningful semantic folders based on their content, "
    "and rename any file with a generic or unclear name to a short descriptive "
    "snake_case name that reflects what the file actually contains."
)

# ── Paths ──────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434"
RUNS_DIR = Path.home() / ".file-agent" / "runs"
TEST_FOLDER = "model_test"

# ── Planner ────────────────────────────────────────────────────────────────────
PLANNER_NUM_PREDICT = 2048  # mapping output is ~50 tokens/file, much shorter than step lists
CONTENT_PREVIEW_MAX_CHARS = 400
CONTENT_PREVIEW_MAX_BYTES = 8192

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".log", ".yaml", ".yml"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx"}  # content extracted via pdfplumber / python-docx

AMBIGUOUS_STEMS = {
    "doc", "file", "untitled", "temp", "misc", "stuff",
    "notes", "random", "old", "thing", "new", "data",
}
AMBIGUOUS_MAX_STEM_LEN = 6

# ── Reflector ──────────────────────────────────────────────────────────────────
REFLECTOR_NUM_PREDICT = 50
MAX_RETRIES_PER_STEP = 3
MAX_REPLANS = 3

# Errors where retrying will never help — auto-skip immediately
SKIP_ERROR_PATTERNS = (
    "not found",
    "no such file",
    "does not exist",
    "already exists",
    "already moved",
)

# ── Executor ───────────────────────────────────────────────────────────────────
DESTRUCTIVE_TOOLS = {"move_file", "rename_file"}
MAX_RUN_SECONDS = 400  # hard wall-clock timeout per run
