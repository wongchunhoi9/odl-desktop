"""
Build a double-clickable .app with:

    pip install py2app
    python setup.py py2app

Output lands in dist/ODL Desktop.app. Not notarized — first launch needs a
right-click -> Open to get past Gatekeeper. Java must still be installed
separately on the target machine; py2app bundles Python, not the JVM.
"""

from setuptools import setup

APP = ["app.py"]
DATA_FILES = [("ui", ["ui/index.html", "ui/style.css", "ui/app.js"])]
OPTIONS = {
    "argv_emulation": False,
    "packages": ["webview", "opendataloader_pdf"],
    "iconfile": None,  # point at a .icns file here once you have one
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
