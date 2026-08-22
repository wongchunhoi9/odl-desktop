"""The bridge between the HTML/JS frontend and Python.

Every public method on Api becomes callable from JS as
`window.pywebview.api.<method_name>(...)`, returning a Promise.

Long-running work (conversion) runs on a background thread and pushes
progress back into the page via `window.dispatchEvent`, since pywebview API
calls are request/response — they can't stream partial results on their own.
"""

import json
import subprocess
import threading
from pathlib import Path

import webview

from backend import prefs
from backend.converter import run_conversion
from backend.hybrid_server import manager as hybrid_manager
from backend.java_check import check_java


class Api:
    def __init__(self):
        self._window: webview.Window | None = None

    def set_window(self, window: webview.Window):
        self._window = window

    # ---- helpers -----------------------------------------------------

    def _emit(self, event_name: str, payload: dict):
        """Fire a CustomEvent on `window` in the page, carrying `payload` as detail."""
        if not self._window:
            return
        safe_json = json.dumps(payload)
        self._window.evaluate_js(
            f"window.dispatchEvent(new CustomEvent('{event_name}', "
            f"{{ detail: {safe_json} }}))"
        )

    # ---- settings ------------------------------------------------------

    def get_settings(self) -> dict:
        return prefs.load()

    def save_settings(self, settings: dict) -> dict:
        prefs.save(settings)
        return {"ok": True}

    # ---- environment checks --------------------------------------------

    def check_environment(self) -> dict:
        java_status = check_java()
        return {
            "java_found": java_status.found,
            "java_ok": java_status.ok,
            "java_version": java_status.version,
            "java_message": java_status.message,
        }

    # ---- file/folder pickers -------------------------------------------

    def choose_input_files(self) -> list:
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=("PDF files (*.pdf)",),
        )
        return list(result) if result else []

    def choose_input_folder(self) -> list:
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return list(result) if result else []

    def choose_output_folder(self) -> str | None:
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None

    def reveal_in_finder(self, path: str) -> dict:
        target = Path(path)
        if not target.exists():
            return {"ok": False, "error": "Path does not exist."}
        subprocess.run(["open", "-R", str(target)])
        return {"ok": True}

    def open_folder(self, path: str) -> dict:
        target = Path(path)
        if not target.exists():
            return {"ok": False, "error": "Path does not exist."}
        subprocess.run(["open", str(target)])
        return {"ok": True}

    # ---- hybrid backend --------------------------------------------------

    def _status_dict(self, status) -> dict:
        return {
            "state": status.state,
            "port": status.port,
            "message": status.message,
            "force_ocr": status.force_ocr,
            "ocr_lang": status.ocr_lang,
            "enrich_formula": status.enrich_formula,
            "enrich_picture_description": status.enrich_picture_description,
        }

    def hybrid_status(self) -> dict:
        return self._status_dict(hybrid_manager.status())

    def hybrid_start(self, options: dict) -> dict:
        """`options` carries the backend's *startup* config — port, OCR, and
        enrichment flags — since those are baked in when the server process
        launches, not sent per conversion request."""
        status = hybrid_manager.start(
            port=options.get("port"),
            force_ocr=bool(options.get("force_ocr", False)),
            ocr_lang=options.get("ocr_lang", "en"),
            enrich_formula=bool(options.get("enrich_formula", False)),
            enrich_picture_description=bool(options.get("enrich_picture_description", False)),
        )
        return self._status_dict(status)

    def hybrid_stop(self) -> dict:
        return self._status_dict(hybrid_manager.stop())

    # ---- conversion --------------------------------------------------------

    def start_conversion(self, input_paths: list, settings: dict) -> dict:
        """Kicks off conversion on a background thread; progress/result come
        back via 'odl:progress' and 'odl:complete' events on window."""
        prefs.save(settings)

        def worker():
            def on_progress(message: str):
                self._emit("odl:progress", {"message": message})

            self._emit("odl:progress", {"message": "Starting..."})
            result = run_conversion(settings, input_paths, progress_callback=on_progress)
            payload = {
                "ok": result.ok,
                "error": result.error,
                "files": [
                    {
                        "input_path": f.input_path,
                        "ok": f.ok,
                        "outputs": f.outputs,
                        "error": f.error,
                    }
                    for f in result.files
                ],
            }
            self._emit("odl:complete", payload)

        threading.Thread(target=worker, daemon=True).start()
        return {"started": True}
