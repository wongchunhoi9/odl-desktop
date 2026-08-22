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
│   ├── index.html
│   ├── style.css
│   └── app.js
├── requirements.txt
├── setup.py                # py2app config for building a double-clickable .app later
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

## Package as a .app (later)

Once the app works the way you want, package it with `py2app`:

```bash
pip install py2app
python setup.py py2app
```

The built app will land in `dist/ODL Desktop.app`. Since it isn't notarized, the first launch
needs a right-click → Open to get past Gatekeeper.

## Notes / things left intentionally simple for now

- Conversion runs synchronously in a background thread per batch; there's no persistent job queue.
- Hybrid backend lifecycle is manual (you click Start/Stop) rather than auto-managed, so you
  always know whether a background process is alive.
- Settings persistence is a flat JSON file, not a real settings UI.
- `backend/hybrid_server.py` launches the hybrid backend via the `opendataloader-pdf-hybrid`
  console script installed by the `opendataloader-pdf[hybrid]` extra. If a future version of the
  package renames or changes that entry point, update `HYBRID_SERVER_EXECUTABLE` there.
