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

import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_PORT = 5002
STARTUP_TIMEOUT_SECONDS = 60  # first run downloads docling models; can be slow
POLL_INTERVAL_SECONDS = 0.5

HYBRID_SERVER_EXECUTABLE = "opendataloader-pdf-hybrid"

# Env vars the py2app launcher / our own interpreter set for *this* process.
# A child that's a venv's console script must not inherit them, or its Python
# would try to load its stdlib from inside the .app bundle.
_PYTHON_ENV_VARS = (
    "PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "PYTHONNOUSERSITE",
    "RESOURCEPATH", "ARGVZERO", "EXECUTABLEPATH", "__PYVENV_LAUNCHER__",
    "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
)

_CONDA_ROOTS = (
    "miniconda3", "miniconda", "anaconda3", "anaconda",
    "miniforge3", "mambaforge", "opt/anaconda3",
)


def _candidate_bin_dirs(home: Optional[Path] = None) -> list:
    """Directories where the hybrid extra's console script is commonly installed.

    A Finder-launched .app only sees launchd's minimal PATH (/usr/bin:/bin:...),
    not the user's shell PATH, so a plain `shutil.which` misses installs in
    conda, pipx, pyenv, venvs, etc. Order is lookup priority.
    """
    home = home or Path.home()
    dirs = [
        Path(sys.executable).parent,       # running from source in a venv that isn't activated
        home / "odl-hybrid" / "bin",       # location suggested in the README
        home / ".local" / "bin",           # pipx, pip --user (Linux-style)
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    ]
    dirs += sorted(home.glob("Library/Python/*/bin"), reverse=True)   # pip --user on macOS
    dirs += sorted(Path("/Library/Frameworks/Python.framework/Versions").glob("*/bin"), reverse=True)
    for root in _CONDA_ROOTS:
        dirs.append(home / root / "bin")
        dirs += sorted((home / root).glob("envs/*/bin"))
    dirs += sorted(home.glob(".pyenv/versions/*/bin"), reverse=True)
    for pattern in (".venvs/*/bin", ".virtualenvs/*/bin", "venv/bin", ".venv/bin"):
        dirs += sorted(home.glob(pattern))
    return dirs


def find_hybrid_executable(home: Optional[Path] = None) -> Optional[str]:
    """Absolute path to `opendataloader-pdf-hybrid`, or None if it isn't installed."""
    on_path = shutil.which(HYBRID_SERVER_EXECUTABLE)
    if on_path:
        return on_path
    for directory in _candidate_bin_dirs(home):
        candidate = directory / HYBRID_SERVER_EXECUTABLE
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _child_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _PYTHON_ENV_VARS}


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

        executable = find_hybrid_executable()
        if executable is None:
            with self._lock:
                self._state = "error"
                self._message = (
                    f"Couldn't find '{HYBRID_SERVER_EXECUTABLE}' on PATH or in common install "
                    "locations (~/odl-hybrid, pipx, conda, pyenv, ~/.venvs). Install it with: "
                    'python3 -m venv ~/odl-hybrid && ~/odl-hybrid/bin/pip install "opendataloader-pdf[hybrid]"'
                )
            return self.status()

        cmd = [executable, "--port", str(self.port)]
        if force_ocr:
            cmd.append("--force-ocr")
        # --ocr-lang applies whenever OCR runs at all, not only under
        # --force-ocr — the hybrid backend also OCRs scanned pages that lack
        # embedded text on its own. Passing it unconditionally is what makes
        # the language picker meaningful outside the force-OCR case.
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
                env=_child_env(),
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
