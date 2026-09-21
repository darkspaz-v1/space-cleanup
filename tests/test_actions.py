import os
import re
from datetime import date
from pathlib import Path

import pytest

import actions

SRC = Path(actions.__file__).parent


def test_delete_goes_to_recycle_bin_only(tmp_path, trash_calls):
    f = tmp_path / "doomed.txt"
    f.write_text("data")
    actions.delete_file(f)
    # send2trash received exactly this path, as a str...
    assert trash_calls == [str(f)]
    # ...and nothing removed it directly (the recorder does not delete, so it survives).
    assert f.exists()


def test_delete_never_uses_permanent_delete_primitives(tmp_path, trash_calls):
    # conftest arms os.remove/unlink/rmdir, shutil.rmtree and Path.unlink to raise;
    # if delete_file used any of them this would fail.
    f = tmp_path / "a.txt"
    f.write_text("x")
    actions.delete_file(f)
    assert len(trash_calls) == 1


def test_delete_propagates_send2trash_failure_without_fallback(tmp_path, monkeypatch):
    f = tmp_path / "locked.txt"
    f.write_text("x")

    def fail(path):
        raise OSError("recycle bin unavailable")

    monkeypatch.setattr(actions, "send2trash", fail)
    with pytest.raises(OSError):
        actions.delete_file(f)  # must NOT fall back to unlinking (armed to fail the test)
    assert f.exists()


@pytest.mark.parametrize("module", ["actions.py", "scanner.py", "app.py"])
def test_source_has_no_permanent_delete_calls(module):
    code = (SRC / module).read_text(encoding="utf-8")
    forbidden = re.findall(r"os\.remove|os\.unlink|os\.rmdir|shutil\.rmtree|\.unlink\(|\.rmdir\(", code)
    assert forbidden == []


def test_archive_moves_into_dated_folder_preserving_subpath(tmp_path):
    root = tmp_path / "Downloads"
    src = root / "sub" / "old.zip"
    src.parent.mkdir(parents=True)
    src.write_text("payload")
    dest = actions.archive_file(src, str(root))
    assert dest == root / "_archive" / date.today().isoformat() / "sub" / "old.zip"
    assert dest.read_text() == "payload"
    assert not src.exists()


def test_archive_avoids_name_collisions(tmp_path):
    root = tmp_path
    first = root / "a" / "f.txt"
    first.parent.mkdir()
    first.write_text("one")
    d1 = actions.archive_file(first, str(root))
    again = root / "a" / "f.txt"
    again.write_text("two")
    d2 = actions.archive_file(again, str(root))
    assert d1.name == "f.txt" and d2.name == "f (1).txt"
    assert d1.read_text() == "one" and d2.read_text() == "two"


def test_archive_file_outside_root_falls_back_to_flat_name(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "elsewhere" / "x.txt"
    outside.parent.mkdir()
    outside.write_text("x")
    dest = actions.archive_file(outside, str(root))
    assert dest == root / "_archive" / date.today().isoformat() / "x.txt"
    assert os.path.exists(dest)
