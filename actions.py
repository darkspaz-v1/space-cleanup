import shutil
from datetime import date
from pathlib import Path

from send2trash import send2trash


def archive_file(fpath: Path, scan_root: str):
    """Move fpath into <scan_root>/_archive/<today>/<relative subpath>/, avoiding name collisions."""
    root = Path(scan_root)
    try:
        rel = fpath.relative_to(root)
    except ValueError:
        rel = Path(fpath.name)
    dest_dir = root / "_archive" / date.today().isoformat() / rel.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / fpath.name
    if dest.exists():
        stem, suffix = dest.stem, dest.suffix
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{stem} ({counter}){suffix}"
            counter += 1
    shutil.move(str(fpath), str(dest))
    return dest


def delete_file(fpath: Path):
    """Send to Recycle Bin (recoverable) rather than permanent delete."""
    send2trash(str(fpath))
