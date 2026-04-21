"""
Vision testing configuration.

Settings specific to the vision pipeline — image classification via
qwen3-vl:8b. Imported by read_file.py and agent.py for vision-related
behaviour. Does not override or depend on config.py.
"""

# ── Vision model ───────────────────────────────────────────────────────────────
VISION_MODEL = "qwen3-vl:8b"           # Ollama model used for all image reads

# ── Vision test folder ─────────────────────────────────────────────────────────
VISION_TEST_FOLDER = "sample"          # built-in sample folder with mixed file types

# ── Image prompt ──────────────────────────────────────────────────────────────
# Sent to the vision model alongside the image. Keep it concise — the model
# should return a short, factual description useful for classification.
VISION_PROMPT = (
    "Describe this image in 2-3 sentences for file organization purposes. "
    "State clearly: what is shown, what category it belongs to "
    "(e.g. Travel, Nature, Food, Animals, Work, Sports, Personal), "
    "and any relevant details that would help rename or sort this file."
)

# ── Supported image extensions ─────────────────────────────────────────────────
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
