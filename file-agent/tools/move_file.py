import os
import shutil
from pathlib import Path
from langchain_core.tools import tool


@tool
def move_file(src: str, dest_folder: str) -> dict:
    """
    Moves a file to dest_folder using shutil.move.
    Pre-flight checks: src must exist, dest_folder must exist.
    If filename collision at dest, appends _1, _2 etc. (never overwrites).
    """
    src = os.path.expanduser(src)
    dest_folder = os.path.expanduser(dest_folder)

    src_path = Path(src)
    dest_dir = Path(dest_folder)

    if not src_path.exists():
        return {"success": False, "message": f"Source file not found: {src}"}

    if not src_path.is_file():
        return {"success": False, "message": f"Source is not a file: {src}"}

    if not dest_dir.exists():
        return {
            "success": False,
            "message": f"Destination folder does not exist: {dest_folder}. Create it first with create_folder.",
        }

    if not dest_dir.is_dir():
        return {"success": False, "message": f"Destination is not a directory: {dest_folder}"}

    # Build destination path with collision detection
    dest_path = dest_dir / src_path.name
    if dest_path.exists():
        stem = src_path.stem
        suffix = src_path.suffix
        counter = 1
        while dest_path.exists():
            dest_path = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    try:
        shutil.move(str(src_path), str(dest_path))
        return {
            "success": True,
            "message": f"Moved '{src_path.name}' → '{dest_folder}/{dest_path.name}'",
            "src": str(src_path),
            "dest": str(dest_path),
            "dest_folder": str(dest_dir.resolve()),
        }
    except PermissionError as e:
        return {"success": False, "message": f"Permission denied: {e}"}
    except Exception as e:
        return {"success": False, "message": f"Move failed: {e}"}
