# Space Cleanup

[![CI](https://github.com/darkspaz-v1/space-cleanup/actions/workflows/ci.yml/badge.svg)](https://github.com/darkspaz-v1/space-cleanup/actions/workflows/ci.yml)

On-demand review of what is eating disk space, with reversible actions only.

## How it works

- **Not** a background watcher. You open it when you want to look.
- Scans configured folders (default Downloads, Desktop, Documents) for files that are large, stale
  (untouched for N days), or both.
- Each result gets one of three actions:
  - **Keep** — remembered, and not raised again unless the file changes.
  - **Archive** — moved to a dated `_archive` subfolder beside its original location.
  - **Delete** — sent to the **Recycle Bin** via `send2trash`, never unlinked.

## The design decision worth stating

Nothing here deletes permanently. A disk-cleanup tool is exactly the kind of program where one wrong
click is unrecoverable, so the destructive path is routed through the Recycle Bin and the Keep
decision is persisted so the same file is not re-proposed on every scan.

Two real bugs were fixed during review: a column sort that ordered display strings rather than
underlying values, and a race where a slow scan could finish after a newer one and overwrite its
results.

**Stack:** Python, Tkinter (`ttk.Treeview`), `send2trash`, Pillow.

## Part of a suite

One of seven small Windows tray utilities built as separate, self-contained apps: each has its own
folder, its own virtualenv and its own `run.bat`, with no shared runtime. They are deliberately not a
framework — the only thing they share is a set of conventions.

| Convention | Why |
|---|---|
| Single-instance guard via a `.singleton.lock` file | An earlier `.instance.lock` design could get stuck after a force-kill and leave the app permanently unlaunchable |
| Relaunch brings the existing window forward | Previously a second launch silently did nothing, which was indistinguishable from the app being broken |
| Config lives in `config.json`, read at startup | Edit it, then fully exit the tray icon and relaunch — a running process never re-reads it |
| Tray icon generated in code (`icon.py`) | No binary asset to keep in sync |

## Running it

```
py -m venv venv
venv\Scripts\pip install -r requirements.txt
run.bat
```

Create the virtualenv and install once; after that `run.bat` starts the app with `venv\Scripts\python.exe`.
Windows only — these use Win32 APIs and a system tray.

## Development

```
venv\Scripts\pip install -r requirements-dev.txt
venv\Scripts\python -m pytest
venv\Scripts\ruff check .
```

The tests cover the scanner (thresholds, size totals, skip folders, keep list) and the file actions. Every
test runs with `send2trash` replaced by a recorder and the permanent-delete calls (`os.remove`,
`os.unlink`, `shutil.rmtree`, `Path.unlink`) armed to fail, so the suite can never delete a real file or
touch your Recycle Bin. CI runs the same two commands on Windows with Python 3.12 and 3.13.

## Troubleshooting

Log file location: `logs/space-cleanup.log` next to `app.py` (rotating, 1 MB x 3). Set `APP_LOG_LEVEL=DEBUG`
before launching to also record errors the app deliberately ignores. A crash traceback goes to `app_error.log`.

## License

MIT — see [LICENSE](LICENSE).
