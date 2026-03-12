import os
from pathlib import Path
from langchain_core.tools import tool


@tool
def list_files(folder: str) -> dict:
    """
    Lists all files in a folder (non-recursive).
    Returns name, extension, size_bytes, modified_timestamp, full_path for each file.
    Skips hidden files (starting with .).
    """
    folder = os.path.expanduser(folder)
    folder_path = Path(folder)

    if not folder_path.exists():
        return {"success": False, "message": f"Folder does not exist: {folder}", "files": []}

    if not folder_path.is_dir():
        return {"success": False, "message": f"Path is not a directory: {folder}", "files": []}

    files = []
    try:
        for entry in sorted(folder_path.iterdir()):
            if entry.name.startswith("."):
                continue
            if entry.is_file():
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "extension": entry.suffix.lower(),
                    "size_bytes": stat.st_size,
                    "modified_timestamp": stat.st_mtime,
                    "full_path": str(entry.resolve()),
                })
    except PermissionError as e:
        return {"success": False, "message": f"Permission denied: {e}", "files": []}

    return {
        "success": True,
        "message": f"Found {len(files)} files in {folder}",
        "files": files,
        "count": len(files),
    }
