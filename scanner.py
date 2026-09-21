import json
import os
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).parent
CONFIG_PATH = APP_DIR / "config.json"
KEEP_LIST_PATH = APP_DIR / "keep_list.json"

DEFAULT_CONFIG = {
    "folders": [
        "%USERPROFILE%\\Downloads",
        "%USERPROFILE%\\Desktop",
        "%USERPROFILE%\\Documents",
    ],
    "large_file_mb": 100,
    "stale_days": 60,
    "skip_dirs": ["_archive", "node_modules", "venv", ".git", "__pycache__"],
}


def load_config():
    config = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    except FileNotFoundError:
        pass
    config["folders"] = [os.path.expandvars(f) for f in config["folders"]]
    return config


def load_keep_list():
    try:
        with open(KEEP_LIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_keep_list(keep_list):
    with open(KEEP_LIST_PATH, "w", encoding="utf-8") as f:
        json.dump(keep_list, f, indent=2)


def mark_kept(keep_list, path, size, mtime, atime):
    keep_list[str(path)] = {
        "size": size,
        "mtime": mtime,
        "atime": atime,
        "kept_at": datetime.now(timezone.utc).isoformat(),
    }


def is_still_kept(keep_list, path, size, mtime, atime):
    rec = keep_list.get(str(path))
    if not rec:
        return False
    return rec["size"] == size and rec["mtime"] == mtime and rec["atime"] == atime


def scan(config, keep_list):
    """Walk configured folders and return candidate files (large and/or stale),
    skipping files whose size/mtime/atime are unchanged since they were kept."""
    large_bytes = config["large_file_mb"] * 1024 * 1024
    stale_seconds = config["stale_days"] * 86400
    now = datetime.now().timestamp()
    skip_dirs = set(d.lower() for d in config.get("skip_dirs", []))

    candidates = []
    seen_paths = set()

    for root_folder in config["folders"]:
        root_path = Path(root_folder)
        if not root_path.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if d.lower() not in skip_dirs]
            for name in filenames:
                fpath = Path(dirpath) / name
                if str(fpath) in seen_paths:
                    continue
                try:
                    st = fpath.stat()
                except OSError:
                    continue
                size = st.st_size
                mtime = st.st_mtime
                atime = st.st_atime
                age = now - max(mtime, atime)

                is_large = size >= large_bytes
                is_stale = age >= stale_seconds
                if not (is_large or is_stale):
                    continue

                if is_still_kept(keep_list, fpath, size, mtime, atime):
                    continue

                seen_paths.add(str(fpath))
                candidates.append(
                    {
                        "path": fpath,
                        "name": name,
                        "size": size,
                        "mtime": mtime,
                        "atime": atime,
                        "is_large": is_large,
                        "is_stale": is_stale,
                        "root": str(root_path),
                    }
                )

    candidates.sort(key=lambda c: c["size"], reverse=True)
    return candidates


def total_size(candidates):
    """Sum of candidate sizes in bytes (what the status bar reports)."""
    return sum(c["size"] for c in candidates)


def human_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
