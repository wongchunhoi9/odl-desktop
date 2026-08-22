"""Manages the lifecycle of the local hybrid/OCR backend process.

The hybrid extra (`pip install "opendataloader-pdf[hybrid]"`) installs a
console script, `opendataloader-pdf-hybrid`, which runs a local FastAPI
server (the "docling-fast" backend) that OpenDataLoader routes complex/scanned
pages to. We manage it as an explicit, user-controlled background process —
started/stopped from the "Hybrid/OCR Backend" panel — rather than
auto-spawning it, so it's always obvious whether something is running.

Confirmed invocation (from the package's own docs/README examples):
    opendataloader-pdf-hybrid --port 5002
    opendataloader-pdf-hybrid --port 5002 --force-ocr
    opendataloader-pdf-hybrid --port 5002 --force-ocr --ocr-lang ko,en
    opendataloader-pdf-hybrid --port 5002 --enrich-picture-description

Note: --force-ocr and --enrich-* are backend *startup* flags (they configure
what the running server will do), not per-request flags — which is why we
pass them here at start() time rather than in converter.py's convert() call.
"""

import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from typing import Optional

DEFAULT_PORT = 5002
STARTUP_TIMEOUT_SECONDS = 60  # first run downloads docling models; can be slow
POLL_INTERVAL_SECONDS = 0.5

HYBRID_SERVER_EXECUTABLE = "opendataloader-pdf-hybrid"


@dataclass
class HybridStatus:
    state: str  # "stopped" | "starting" | "running" | "error"
    port: int
    message: str = ""
    # Echoes back the startup config actually in effect for the running
    # process, so the UI can show it even after the page/app restarts.
    force_ocr: bool = False
    ocr_lang: str = "en"
    enrich_formula: bool = False
    enrich_picture_description: bool = False


class HybridServerManager:
    """One instance lives for the app's lifetime; owns at most one subprocess."""

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self._process: Optional[subprocess.Popen] = None
        self._state = "stopped"
        self._message = ""
        self._lock = threading.Lock()
        self._startup_opts = {
            "force_ocr": False,
            "ocr_lang": "en",
            "enrich_formula": False,
            "enrich_picture_description": False,
        }
        self._output_tail = deque(maxlen=40)

    def status(self) -> HybridStatus:
        with self._lock:
            # If we think it's running, double check the process hasn't died.
            if self._state == "running" and self._process and self._process.poll() is not None:
                self._state = "error"
                self._message = f"Backend process exited unexpectedly (code {self._process.returncode})."
            return HybridStatus(
                state=self._state,
                port=self.port,
                message=self._message,
                **self._startup_opts,
            )

    def _health_check(self) -> bool:
        # Try a couple of plausible readiness endpoints — FastAPI apps
        # commonly expose /health, but fall back to the root path in case
        # this build doesn't. Any HTTP response (not a connection error)
        # means the server is up and accepting requests.
        for path in ("/health", "/"):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=1) as resp:
                    if resp.status < 500:
                        return True
            except urllib.error.HTTPError as exc:
                # Server responded (even with an error status) — it's alive.
                if exc.code < 500:
                    return True
            except (urllib.error.URLError, ConnectionError, OSError):
                continue
        return False

    def start(
        self,
        port: Optional[int] = None,
        force_ocr: bool = False,
        ocr_lang: str = "en",
        enrich_formula: bool = False,
        enrich_picture_description: bool = False,
    ) -> HybridStatus:
        with self._lock:
            if self._state in ("running", "starting"):
                return HybridStatus(state=self._state, port=self.port, message="Already running or starting.")
            if port:
                self.port = port
            self._startup_opts = {
                "force_ocr": force_ocr,
                "ocr_lang": ocr_lang or "en",
                "enrich_formula": enrich_formula,
                "enrich_picture_description": enrich_picture_description,
            }
            self._state = "starting"
            self._message = "Launching hybrid backend..."

        if shutil.which(HYBRID_SERVER_EXECUTABLE) is None:
            with self._lock:
                self._state = "error"
                self._message = (
                    f"'{HYBRID_SERVER_EXECUTABLE}' isn't on PATH. Install the hybrid extra with: "
                    'pip install "opendataloader-pdf[hybrid]" (in the same venv the app runs from).'
                )
            return self.status()

        cmd = [HYBRID_SERVER_EXECUTABLE, "--port", str(self.port)]
        if force_ocr:
            cmd.append("--force-ocr")
            cmd += ["--ocr-lang", ocr_lang or "en"]
        if enrich_formula:
            cmd.append("--enrich-formula")
        if enrich_picture_description:
            cmd.append("--enrich-picture-description")

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as exc:
            with self._lock:
                self._state = "error"
                self._message = f"Couldn't launch hybrid backend: {exc}"
            return self.status()

        # One thread drains stdout continuously (so the pipe never fills and
        # blocks the child) and keeps a rolling tail for error messages.
        # Another polls for HTTP readiness. Both are daemons tied to this process.
        threading.Thread(target=self._drain_output, daemon=True).start()
        threading.Thread(target=self._wait_for_ready, daemon=True).start()
        return self.status()

    def _drain_output(self):
        proc = self._process
        if not proc or not proc.stdout:
            return
        for line in proc.stdout:
            self._output_tail.append(line.rstrip())

    def _wait_for_ready(self):
        deadline = time.time() + STARTUP_TIMEOUT_SECONDS
        while time.time() < deadline:
            if self._process and self._process.poll() is not None:
                with self._lock:
                    self._state = "error"
                    tail = "\n".join(self._output_tail)[-800:]
                    self._message = (
                        f"Backend process exited during startup (code {self._process.returncode})."
                        + (f"\n{tail}" if tail else "")
                    )
                return
            if self._health_check():
                with self._lock:
                    self._state = "running"
                    self._message = f"Hybrid backend running on port {self.port}."
                return
            time.sleep(POLL_INTERVAL_SECONDS)

        with self._lock:
            self._state = "error"
            tail = "\n".join(self._output_tail)[-800:]
            self._message = "Timed out waiting for hybrid backend to become ready." + (
                f"\n{tail}" if tail else ""
            )

    def stop(self) -> HybridStatus:
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
            self._process = None
            self._state = "stopped"
            self._message = ""
            self._output_tail = deque(maxlen=40)
            return HybridStatus(state=self._state, port=self.port, message=self._message)


# Module-level singleton — the whole app shares one backend process.
manager = HybridServerManager()
