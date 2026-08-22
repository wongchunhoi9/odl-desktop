"""Checks that a usable Java (11+) is on PATH before we let the user hit Convert.

The OpenDataLoader core engine is Java-based; the Python package is a thin
wrapper that shells out to it. Failing fast with a clear message here is much
friendlier than letting the first conversion blow up with a cryptic
"java: command not found" buried in a stack trace.
"""

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class JavaStatus:
    found: bool
    version: Optional[str] = None
    major_version: Optional[int] = None
    ok: bool = False
    message: str = ""


def check_java(min_major: int = 11) -> JavaStatus:
    java_path = shutil.which("java")
    if not java_path:
        return JavaStatus(
            found=False,
            ok=False,
            message=(
                "Java was not found on your PATH. OpenDataLoader PDF requires "
                "Java 11 or newer. Install a JDK (e.g. via Adoptium) and restart the app."
            ),
        )

    try:
        result = subprocess.run(
            [java_path, "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return JavaStatus(
            found=True,
            ok=False,
            message=f"Found Java at {java_path} but couldn't run it: {exc}",
        )

    # `java -version` prints to stderr, e.g.:
    #   openjdk version "17.0.9" 2023-10-17
    version_output = result.stderr or result.stdout
    match = re.search(r'version "(\d+)(?:\.(\d+))?', version_output)
    if not match:
        return JavaStatus(
            found=True,
            ok=False,
            message=f"Found Java at {java_path} but couldn't parse its version.",
        )

    major = int(match.group(1))
    # Old-style versioning (1.8.0_xxx) reports major "1" with a "1.8" pattern;
    # treat that historical case as Java 8 for the floor check.
    if major == 1:
        major = int(match.group(2) or 0)

    version_str = match.group(0).split('"')[-1] if '"' in match.group(0) else version_output.strip()

    ok = major >= min_major
    message = (
        f"Java {major} detected — OK."
        if ok
        else f"Java {major} found, but version {min_major}+ is required."
    )
    return JavaStatus(found=True, version=version_str, major_version=major, ok=ok, message=message)
