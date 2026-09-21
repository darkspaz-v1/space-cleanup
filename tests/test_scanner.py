import os
import time

import pytest

import scanner
from scanner import human_size, is_still_kept, mark_kept, scan, total_size

DAY = 86400
MB = 1024 * 1024


def make_file(folder, name, size=10, age_days=0):
    p = folder / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)
    if age_days:
        t = time.time() - age_days * DAY
        os.utime(p, (t, t))
    return p


def cfg(*folders, large_mb=1, stale_days=60, skip=("_archive", "node_modules")):
    return {
        "folders": [str(f) for f in folders],
        "large_file_mb": large_mb,
        "stale_days": stale_days,
        "skip_dirs": list(skip),
    }


def names(candidates):
    return [c["name"] for c in candidates]


def test_large_file_is_flagged_large_only(tmp_path):
    make_file(tmp_path, "big.bin", size=2 * MB)
    (c,) = scan(cfg(tmp_path), {})
    assert c["is_large"] and not c["is_stale"]


def test_stale_file_is_flagged_stale_only(tmp_path):
    make_file(tmp_path, "old.txt", age_days=90)
    (c,) = scan(cfg(tmp_path), {})
    assert c["is_stale"] and not c["is_large"]


def test_large_and_stale_flagged_both(tmp_path):
    make_file(tmp_path, "both.bin", size=2 * MB, age_days=90)
    (c,) = scan(cfg(tmp_path), {})
    assert c["is_large"] and c["is_stale"]


def test_small_recent_file_is_not_a_candidate(tmp_path):
    make_file(tmp_path, "fresh.txt")
    assert scan(cfg(tmp_path), {}) == []


def test_recently_accessed_old_file_is_not_stale(tmp_path):
    # Age is measured from max(mtime, atime): reading a file makes it non-stale.
    p = make_file(tmp_path, "read_recently.txt")
    old = time.time() - 90 * DAY
    os.utime(p, (time.time(), old))
    assert scan(cfg(tmp_path), {}) == []


def test_size_aggregation_sorted_largest_first_and_totalled(tmp_path):
    make_file(tmp_path, "a.bin", size=3 * MB)
    make_file(tmp_path / "sub", "b.bin", size=5 * MB)
    make_file(tmp_path / "sub" / "deeper", "c.bin", size=2 * MB)
    found = scan(cfg(tmp_path), {})
    assert names(found) == ["b.bin", "a.bin", "c.bin"]
    assert total_size(found) == 10 * MB
    assert total_size([]) == 0


def test_skip_dirs_are_pruned_case_insensitively(tmp_path):
    make_file(tmp_path / "node_modules" / "pkg", "huge.bin", size=2 * MB)
    make_file(tmp_path / "_ARCHIVE" / "2026-01-01", "old.bin", size=2 * MB)
    make_file(tmp_path, "kept_out.bin", size=2 * MB)
    assert names(scan(cfg(tmp_path), {})) == ["kept_out.bin"]


def test_missing_folder_is_ignored(tmp_path):
    make_file(tmp_path, "big.bin", size=2 * MB)
    found = scan(cfg(tmp_path / "does-not-exist", tmp_path), {})
    assert names(found) == ["big.bin"]


def test_overlapping_roots_do_not_double_count(tmp_path):
    make_file(tmp_path / "inner", "big.bin", size=2 * MB)
    found = scan(cfg(tmp_path, tmp_path / "inner"), {})
    assert len(found) == 1
    assert total_size(found) == 2 * MB


def test_candidate_records_its_scan_root(tmp_path):
    make_file(tmp_path / "sub", "big.bin", size=2 * MB)
    (c,) = scan(cfg(tmp_path), {})
    assert c["root"] == str(tmp_path)
    assert c["path"] == tmp_path / "sub" / "big.bin"


def test_kept_file_is_hidden_until_it_changes(tmp_path):
    p = make_file(tmp_path, "big.bin", size=2 * MB)
    (c,) = scan(cfg(tmp_path), {})
    keep = {}
    mark_kept(keep, c["path"], c["size"], c["mtime"], c["atime"])
    assert is_still_kept(keep, p, c["size"], c["mtime"], c["atime"])
    assert scan(cfg(tmp_path), keep) == []
    # Modify the file: the keep record no longer matches, so it is proposed again.
    t = time.time() + 5
    os.utime(p, (t, t))
    assert names(scan(cfg(tmp_path), keep)) == ["big.bin"]


def test_load_config_expands_env_vars(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner, "CONFIG_PATH", tmp_path / "missing.json")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    config = scanner.load_config()
    assert config["folders"][0] == os.path.join(str(tmp_path), "Downloads")


def test_keep_list_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner, "KEEP_LIST_PATH", tmp_path / "keep_list.json")
    assert scanner.load_keep_list() == {}
    scanner.save_keep_list({"a": {"size": 1}})
    assert scanner.load_keep_list() == {"a": {"size": 1}}


def test_corrupt_keep_list_starts_empty(tmp_path, monkeypatch):
    path = tmp_path / "keep_list.json"
    monkeypatch.setattr(scanner, "KEEP_LIST_PATH", path)
    path.write_text("{truncated", encoding="utf-8")
    assert scanner.load_keep_list() == {}


@pytest.mark.parametrize(
    "n, expected",
    [(0, "0 B"), (1023, "1023 B"), (1024, "1.0 KB"), (5 * MB, "5.0 MB"), (3 * 1024**3, "3.0 GB")],
)
def test_human_size(n, expected):
    assert human_size(n) == expected
