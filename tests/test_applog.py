import logging

import applog


def test_setup_logging_writes_rotating_file_once(tmp_path, monkeypatch):
    monkeypatch.setattr(applog, "LOG_DIR", tmp_path / "logs")
    root = logging.getLogger()
    before = list(root.handlers)
    old_level = root.level
    try:
        applog.setup_logging("demo")
        applog.setup_logging("demo")  # idempotent
        added = [h for h in root.handlers if h not in before]
        assert len(added) == 1
        logging.getLogger("t").warning("hello")
        added[0].flush()
        assert "hello" in (tmp_path / "logs" / "demo.log").read_text(encoding="utf-8")
    finally:
        for h in [h for h in root.handlers if h not in before]:
            root.removeHandler(h)
            h.close()
        root.setLevel(old_level)
