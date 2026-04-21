import os
import base64
from pathlib import Path
from langchain_core.tools import tool
import config_vision
from config_vision import VISION_PROMPT

TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".py", ".js", ".ts", ".html",
                   ".htm", ".css", ".log", ".yaml", ".yml", ".toml", ".xml",
                   ".sh", ".bash", ".zsh", ".env", ".ini", ".cfg", ".conf",
                   ".rs", ".go", ".java", ".c", ".cpp", ".h", ".rb", ".php"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}


def _describe_image(path: str, model: str) -> str:
    try:
        from langchain_ollama import ChatOllama
        from langchain_core.messages import HumanMessage

        with open(path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()

        ext = Path(path).suffix.lower().lstrip(".")
        mime = "jpeg" if ext in ("jpg", "jpeg") else ext

        llm = ChatOllama(model=model, temperature=0, think=False)
        msg = HumanMessage(content=[
            {"type": "text", "text": VISION_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{image_data}"}},
        ])
        return llm.invoke([msg]).content
    except Exception as e:
        return f"[vision error: {e}]"


@tool
def read_file(path: str, max_chars: int = 3000, model: str = "qwen3:8b") -> dict:
    """
    Format-aware file reader. Reads text files (txt, md, json, csv, py, etc.),
    PDFs (via pdfplumber), DOCX files (via python-docx), and images (via Ollama vision).
    Binary files return metadata only. Output is truncated to max_chars.
    """
    path = os.path.expanduser(path)
    file_path = Path(path)

    if not file_path.exists():
        return {"success": False, "message": f"File not found: {path}", "content": ""}

    if not file_path.is_file():
        return {"success": False, "message": f"Not a file: {path}", "content": ""}

    ext = file_path.suffix.lower()
    content = ""
    truncated = False
    file_type = "unknown"

    try:
        if ext in TEXT_EXTENSIONS:
            file_type = "text"
            raw = file_path.read_text(encoding="utf-8", errors="ignore")
            if len(raw) > max_chars:
                content = raw[:max_chars]
                truncated = True
            else:
                content = raw

        elif ext == ".pdf":
            file_type = "pdf"
            try:
                import pdfplumber
                with pdfplumber.open(path) as pdf:
                    pages_text = []
                    for page in pdf.pages:
                        t = page.extract_text()
                        if t:
                            pages_text.append(t)
                    raw = "\n".join(pages_text)
                if len(raw) < 50:
                    # Scanned PDF — try vision model
                    content = _describe_image(path, config_vision.VISION_MODEL)
                    file_type = "pdf-vision"
                else:
                    if len(raw) > max_chars:
                        content = raw[:max_chars]
                        truncated = True
                    else:
                        content = raw
            except ImportError:
                return {"success": False, "message": "pdfplumber not installed", "content": ""}

        elif ext == ".docx":
            file_type = "docx"
            try:
                import docx
                doc = docx.Document(path)
                raw = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                if len(raw) > max_chars:
                    content = raw[:max_chars]
                    truncated = True
                else:
                    content = raw
            except ImportError:
                return {"success": False, "message": "python-docx not installed", "content": ""}

        elif ext in IMAGE_EXTENSIONS:
            file_type = "image"
            # Always use the dedicated vision model for image files
            content = _describe_image(path, config_vision.VISION_MODEL)

        else:
            # Binary or unknown — return metadata only
            stat = file_path.stat()
            return {
                "success": True,
                "message": "Binary/unknown file — metadata only",
                "file_type": "binary",
                "content": "",
                "size_bytes": stat.st_size,
                "extension": ext,
                "truncated": False,
            }

    except Exception as e:
        return {"success": False, "message": f"Error reading file: {e}", "content": ""}

    return {
        "success": True,
        "message": f"Read {file_type} file: {file_path.name}",
        "file_type": file_type,
        "content": content,
        "truncated": truncated,
        "path": path,
    }
