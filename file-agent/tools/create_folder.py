import os
from pathlib import Path
from langchain_core.tools import tool


@tool
def create_folder(path: str) -> dict:
    """
    Creates a folder and all intermediate directories (mkdir -p equivalent).
    Does nothing and returns success if the folder already exists.
    """
    path = os.path.expanduser(path)
    folder = Path(path)

    try:
        already_existed = folder.exists()
        folder.mkdir(parents=True, exist_ok=True)
        if already_existed:
            return {
                "success": True,
                "message": f"Folder already exists: {path}",
                "path": str(folder.resolve()),
                "created": False,
            }
        return {
            "success": True,
            "message": f"Created folder: {path}",
            "path": str(folder.resolve()),
            "created": True,
        }
    except PermissionError as e:
        return {"success": False, "message": f"Permission denied: {e}"}
    except Exception as e:
        return {"success": False, "message": f"Failed to create folder: {e}"}
