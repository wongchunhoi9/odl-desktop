"""
Build a double-clickable .app with:

    pip install py2app
    python setup.py py2app

Output lands in dist/ODL Desktop.app. Not notarized — first launch needs a
right-click -> Open to get past Gatekeeper. Java must still be installed
separately on the target machine; py2app bundles Python, not the JVM.
"""

import sys
from pathlib import Path

from setuptools import setup


# py2app's dependency scanner misses these on conda-based Python builds (a
# known py2app/conda interaction) — without them the built .app fails to
# launch with e.g. "Library not loaded: @rpath/libffi.8.dylib". These are the
# @rpath dylibs the stdlib extension modules we actually use (ctypes, ssl,
# bz2, lzma, decimal, zlib — pulled in via pywebview/urllib/json/etc.) link
# against; tcl/tk are deliberately excluded since tkinter isn't used.
# Exact filenames, matching the @rpath entries `otool -L` reports for the
# stdlib extension modules — not globs, since e.g. libffi.7.dylib and
# libffi.8.dylib can coexist and only .8 is actually referenced.
_NEEDED_DYLIB_NAMES = [
    "libffi.8.dylib",
    "libssl.3.dylib",
    "libcrypto.3.dylib",
    "libbz2.dylib",
    "liblzma.5.dylib",
    "libmpdec.4.dylib",
    "libz.1.dylib",
]


def _find_conda_dylibs() -> list:
    base = Path(sys.base_prefix) / "lib"
    missing = [name for name in _NEEDED_DYLIB_NAMES if not (base / name).exists()]
    if missing:
        raise RuntimeError(
            f"Couldn't find {missing} under {base} — "
            "add their paths to OPTIONS['frameworks'] manually."
        )
    return [str(base / name) for name in _NEEDED_DYLIB_NAMES]


APP = ["app.py"]
DATA_FILES = [("ui", ["ui/index.html", "ui/style.css", "ui/app.js"])]
OPTIONS = {
    "argv_emulation": False,
    # NOTE: "opendataloader_pdf" is deliberately NOT in `packages`. That option
    # forces py2app to recursively bundle every submodule in the package,
    # including hybrid_server.py's docling/torch imports — but this app never
    # imports that module in-process (the hybrid backend runs as a separate
    # OS subprocess via its own `opendataloader-pdf-hybrid` console script).
    # Forcing it in blows past Python's import recursion limit during the
    # module scan and would bundle several GB of unused ML deps anyway.
    # Letting py2app follow the actual `import opendataloader_pdf` in
    # converter.py picks up only wrapper.py/convert_generated.py/etc.
    "packages": ["webview"],
    "includes": ["opendataloader_pdf"],
    "frameworks": _find_conda_dylibs(),
    "iconfile": "assets/AppIcon.icns",
    "plist": {
        "CFBundleName": "ODL Desktop",
        "CFBundleDisplayName": "ODL Desktop",
        "CFBundleIdentifier": "local.odl-desktop",
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
    },
}

setup(
    app=APP,
    name="ODL Desktop",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
