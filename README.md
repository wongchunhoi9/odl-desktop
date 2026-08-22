# ODL Desktop

A minimal macOS desktop UI for [OpenDataLoader PDF](https://opendataloader.org), built with
Python + [pywebview](https://pywebview.flowrl.com/). Lets you pick files/folders, choose output
formats, toggle header/footer stripping, and manage the optional hybrid OCR backend — all from a
native window, without touching the command line.

## Project layout

```
odl-desktop/
├── app.py                 # entry point — creates the pywebview window, wires the JS<->Python bridge
├── backend/
│   ├── api.py              # the Api class exposed to the frontend (window.pywebview.api.*)
│   ├── converter.py        # wraps opendataloader_pdf.convert(), builds kwargs from UI options
│   ├── hybrid_server.py     # start/stop/health-check for the local docling-fast hybrid backend
│   ├── java_check.py        # verifies Java 11+ is on PATH before we let anyone hit Convert
│   └── prefs.py             # persists last-used settings to ~/Library/Application Support
├── ui/
│   ├── index.html           # includes a link to the OpenDataLoader docs in the titlebar
│   ├── style.css
│   └── app.js
├── assets/
│   ├── icon_1024.png        # source art for the app icon (original design — see licensing note below)
│   └── AppIcon.icns         # compiled icon, referenced by setup.py's OPTIONS["iconfile"]
├── requirements.txt
├── setup.py                # py2app config for building a double-clickable .app later
├── THIRD_PARTY_NOTICES.md  # Apache-2.0 attribution for the bundled opendataloader-pdf dependency
├── THIRD_PARTY_LICENSE.txt # full Apache 2.0 text, copied from opendataloader-pdf's own LICENSE
└── README.md
```

## Setup

```bash
cd odl-desktop
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

You also need:

- **Java 11+** on your PATH (the OpenDataLoader core engine is Java-based). The app checks this
  on launch and shows a setup banner if it's missing.
- **Hybrid/OCR extra**, if you want OCR: `pip install "opendataloader-pdf[hybrid]"`. The app
  starts/stops the local `docling-fast` backend process for you from the "Hybrid/OCR Backend" panel.

## Run (development)

```bash
python app.py
```

## Package as a .app

```bash
pip install py2app
python setup.py py2app
```

The built app lands in `dist/ODL Desktop.app`. Since it isn't notarized, the first launch needs a
right-click → Open to get past Gatekeeper.

`setup.py` deliberately does **not** put `opendataloader_pdf` in py2app's `packages` list — that
option bundles a package's entire submodule tree recursively, which would drag in
`hybrid_server.py`'s `docling`/`torch` imports (unused here; the hybrid backend runs as a separate
subprocess, not an in-process import) and blow past Python's import-scan recursion limit. It's
listed under `includes` instead, so py2app follows only what the app actually imports.

If you build from a **conda-based Python** (`sys.base_prefix` pointing at a conda env), py2app's
dependency scanner misses a handful of `@rpath`-linked dylibs (`libffi`, `libssl`, `libcrypto`,
`libbz2`, `liblzma`, `libmpdec`, `libz`) that the stdlib's C extensions need — the built app then
fails to launch with `Library not loaded: @rpath/lib*.dylib`. `setup.py`'s `_find_conda_dylibs()`
locates and bundles them explicitly via `OPTIONS["frameworks"]`; if it raises, your conda env is
missing one of those libs under `<sys.base_prefix>/lib`.

`assets/icon_1024.png` is original artwork (a document glyph + export arrow on a rounded off-white
square, with an "ODL Desktop" wordmark), compiled to `assets/AppIcon.icns` via `iconutil`. It does
**not** reuse OpenDataLoader's own logo — see [Licensing](#licensing) for why.

## Licensing

ODL Desktop's own code has no license file yet (add one before distributing it publicly — MIT or
Apache-2.0 are the usual choices for a thin wrapper like this).

It depends on and bundles [`opendataloader-pdf`](https://pypi.org/project/opendataloader-pdf/)
(Apache License 2.0, © Hancom, Inc.). Apache-2.0 permits using, depending on, and redistributing
that package — including inside this app's `.app` bundle — but **§6 (Trademarks)** explicitly does
*not* grant rights to OpenDataLoader's name, logo, or other marks. Concretely:

- Calling `opendataloader_pdf.convert()` from [converter.py](backend/converter.py) and shipping the
  package inside the packaged app: fine, covered by the license.
- Reusing OpenDataLoader's actual logo as this app's icon or branding: **not** covered — doing so
  earlier was a mistake, since fixed by swapping in the original artwork described above.
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [THIRD_PARTY_LICENSE.txt](THIRD_PARTY_LICENSE.txt)
  carry the required §4 attribution forward — `setup.py` bundles both into the packaged `.app`.

## Notes / things left intentionally simple for now

- Conversion runs synchronously in a background thread per batch; there's no persistent job queue.
- Hybrid backend lifecycle is manual (you click Start/Stop) rather than auto-managed, so you
  always know whether a background process is alive.
- Settings persistence is a flat JSON file, not a real settings UI.
- `backend/hybrid_server.py` launches the hybrid backend via the `opendataloader-pdf-hybrid`
  console script installed by the `opendataloader-pdf[hybrid]` extra. If a future version of the
  package renames or changes that entry point, update `HYBRID_SERVER_EXECUTABLE` there.
