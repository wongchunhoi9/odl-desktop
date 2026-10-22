"""Entry point. Run with: python app.py"""

from pathlib import Path

import webview

from backend import dragdrop
from backend.api import Api
from backend.hybrid_server import manager as hybrid_manager

UI_DIR = Path(__file__).parent / "ui"


def main():
    api = Api()

    window = webview.create_window(
        "ODL Desktop",
        str(UI_DIR / "index.html"),
        js_api=api,
        width=1040,
        height=760,
        min_size=(860, 620),
        background_color="#F5F4F1",
    )
    api.set_window(window)

    def on_closed():
        # Don't leave a stray JVM/hybrid backend process running after quit.
        hybrid_manager.stop()

    window.events.closed += on_closed

    webview.start(dragdrop.install, (window, api._emit), debug=False)


if __name__ == "__main__":
    main()
