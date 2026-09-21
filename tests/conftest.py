"""Safety net for a tool whose job is deleting files.

Every test runs with send2trash replaced by a recorder and with every permanent
delete primitive (os.remove/unlink/rmdir, shutil.rmtree, Path.unlink) armed to
fail the test. Nothing in this suite can touch the real Recycle Bin or unlink a file.
"""
import os
import shutil
from pathlib import Path

import pytest

import actions


@pytest.fixture(autouse=True)
def forbid_permanent_delete(tmp_path, monkeypatch):
    # tmp_path is requested first so pytest's own temp-dir bookkeeping runs unpatched.
    def forbidden(*args, **kwargs):
        raise AssertionError("permanent deletion attempted: %r" % (args,))

    for owner, name in [
        (os, "remove"),
        (os, "unlink"),
        (os, "rmdir"),
        (os, "removedirs"),
        (shutil, "rmtree"),
        (Path, "unlink"),
        (Path, "rmdir"),
    ]:
        monkeypatch.setattr(owner, name, forbidden)


@pytest.fixture(autouse=True)
def trash_calls(monkeypatch):
    """Replace actions.send2trash with a recorder; the real one is never called."""
    calls = []
    monkeypatch.setattr(actions, "send2trash", calls.append)
    return calls
