import os
from pathlib import Path
from langchain_core.tools import tool


@tool
def rename_file(path: str, new_name: str) -> dict:
    """
    Renames a file. Performs collision detection — if new_name already exists in the
    same folder, appends _1, _2, etc. Never silently overwrites an existing file.
    Preserves the original file extension unless new_name explicitly includes one.
    """
    path = os.path.expanduser(path)
    src = Path(path)

    if not src.exists():
        return {"success": False, "message": f"Source file not found: {path}"}

    if not src.is_file():
        return {"success": False, "message": f"Not a file: {path}"}

    new_path = Path(new_name)

    # If new_name has no extension, preserve the original extension
    if not new_path.suffix:
        new_name_with_ext = new_name + src.suffix
    else:
        new_name_with_ext = new_name

    dest = src.parent / new_name_with_ext

    # Collision detection
    if dest.exists():
        stem = Path(new_name_with_ext).stem
        suffix = Path(new_name_with_ext).suffix
        counter = 1
        while dest.exists():
            dest = src.parent / f"{stem}_{counter}{suffix}"
            counter += 1

    try:
        src.rename(dest)
        return {
            "success": True,
            "message": f"Renamed '{src.name}' → '{dest.name}'",
            "old_path": str(src),
            "new_path": str(dest),
            "new_name": dest.name,
        }
    except Exception as e:
        return {"success": False, "message": f"Rename failed: {e}"}
