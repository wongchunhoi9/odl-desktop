"""Native drag-and-drop of PDFs/folders onto the window.

WKWebView never exposes filesystem paths to page JavaScript (`File.path` is
Electron-only), so drops are handled on the Python side instead: pywebview's
DOM event bridge attaches the real path to each dropped file as
`pywebviewFullPath` (folders arrive with a trailing slash).
"""

from pathlib import Path
from typing import Callable

from webview.dom import DOMEventHandler


def extract_dropped_paths(event: dict) -> tuple[list, int]:
    """Returns (accepted PDF/folder paths, number of dropped items skipped)."""
    files = (event.get("dataTransfer") or {}).get("files") or []
    paths, skipped = [], 0
    for item in files:
        raw = item.get("pywebviewFullPath")
        if not raw:
            skipped += 1
            continue
        path = Path(raw)
        if path.is_dir() or path.suffix.lower() == ".pdf":
            paths.append(str(path))
        else:
            skipped += 1
    return paths, skipped


def install(window, emit: Callable[[str, dict], None]) -> None:
    """Listen for drops anywhere on the page and forward them to the UI.

    Must run after the page has loaded (e.g. as the `func` passed to
    `webview.start`). Listening on `document` rather than the dropzone alone
    also stops a stray drop from navigating the webview to the dropped file.
    """
    def on_drop(event):
        paths, skipped = extract_dropped_paths(event)
        emit("odl:dropped", {"paths": paths, "skipped": skipped})

    window.dom.document.events.drop += DOMEventHandler(
        on_drop, prevent_default=True, stop_propagation=True
    )
