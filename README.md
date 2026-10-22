<img src="assets/icon_1024.png" width="96" alt="ODL Desktop icon" />

# ODL Desktop

A native macOS desktop app for [OpenDataLoader PDF](https://opendataloader.org) — pick files or a
folder, choose output formats, and convert, all from a window instead of a terminal. Built with
Python + [pywebview](https://pywebview.flowrl.com/), packaged as a double-clickable `.app` with
[py2app](https://py2app.readthedocs.io/).

## Features

- **Drag and drop** PDFs or folders onto the window, or use the file/folder pickers.
- **Convert** PDFs to Markdown, JSON, HTML, or a tagged/accessibility PDF — batch a whole folder
  (optionally recursive), pick a page range, strip headers/footers, control table detection and
  reading order, extract or embed images, sanitize emails/phones/IPs/URLs out of the text.
- **Optional hybrid OCR backend** for scanned or image-heavy PDFs, with a language picker covering
  the 86 languages EasyOCR supports and adjustable formula/picture-description enrichment.
- **Empty-result warnings** — if a conversion produces an empty Markdown file (typically a scanned
  PDF converted without OCR), the result row shows ⚠ with advice for your current settings.
- **Settings persist** across launches (`~/Library/Application Support/ODL Desktop/prefs.json`).
- **In-app Java check** — the one thing the packaged app doesn't bundle. If Java's missing, a
  banner offers a direct download link and a one-click re-check, no relaunch needed.

## Download

Grab the latest build from the
[Releases page](https://github.com/wongchunhoi9/odl-desktop/releases) — unzip, then **right-click →
Open** the first time (it isn't notarized, so a plain double-click gets blocked by Gatekeeper).
That's it for the core conversion features; see [Hybrid/OCR setup](#hybridocr-setup) below if you
need OCR on scanned PDFs.

Current builds are **Apple Silicon (arm64) only** — see [Building the .app](#building-the-app) if
you need an Intel build.

### Requirements

- **macOS**, Apple Silicon.
- **Java 11+** — not bundled; the app detects this on launch and offers to help you install it.
  Everything else (the OpenDataLoader engine itself, included) ships inside the `.app`.

### Hybrid/OCR setup

The hybrid backend is a separate, optional install, and it's large (~1.4GB — it pulls in
`docling`/`torch`/OCR engines). Skip it unless you're converting scanned PDFs. Easiest setup:

```bash
python3 -m venv ~/odl-hybrid && ~/odl-hybrid/bin/pip install "opendataloader-pdf[hybrid]"
```

Then start/stop it from the app's "Hybrid/OCR Backend" panel. The app finds
`opendataloader-pdf-hybrid` on your `PATH` and in the usual places a Finder-launched app can't see
through `PATH` — `~/odl-hybrid`, `~/.local/bin` (pipx / `pip --user`), `~/Library/Python/*/bin`,
Homebrew, conda/miniconda/miniforge (base and named envs), pyenv, and `~/.venvs`/`~/.virtualenvs`.
If it can't find one, the panel says where it looked and how to install it.

## User guide

### Quick start

1. Open the app. If a yellow banner says Java is missing, click **Download Java…**, install it,
   then click **Re-check**.
2. Add PDFs: **drag and drop** PDFs or a folder onto the window, or use **Choose Files…** /
   **Choose Folder…**. Tick **Include subfolders** if a dropped/chosen folder has PDFs in nested
   folders.
3. Pick an **Output folder** (defaults to `~/Documents/OpenDataLoader Output`).
4. Tick the **Output formats** you want and adjust options if needed (see below).
5. Click **Convert**. Each file gets a result row — ✓ done, ⚠ done but check it, ✕ failed. Use
   **Reveal in Finder** on a row or **Open Output Folder**.

Your settings are remembered between launches.

### Output formats

| Format | File written (for `report.pdf`) |
|---|---|
| Markdown | `report.md` |
| JSON (with bounding boxes) | `report.json` |
| HTML | `report.html` |
| PDF (tagged) — an accessibility-tagged copy | `report_tagged.pdf` |
| Markdown + images | `report.md` (legacy option — upstream deprecates it; use **Markdown** plus the **Images** setting instead) |

All files go into one flat output folder named after the PDF. If two inputs would produce the same
name (e.g. two `report.pdf` files from different subfolders), the app stops before converting and
tells you which ones, rather than letting one overwrite the other.

### Conversion options

| Option | What it does |
|---|---|
| Include headers & footers | Off by default — repeated page headers/footers are dropped from the output. |
| Table detection | *Default* finds tables by their borders; *Cluster* also uses spacing, for tables without ruling lines. |
| Reading order | *XY-Cut* reconstructs the natural reading order of multi-column pages; *Off* skips that step. |
| Images | *Off*, *Embedded* (base64 inside the file), or *External files* (written as separate image files). Then choose PNG or JPEG. |
| Sanitize sensitive data | Masks emails, phone numbers, IPs and URLs in the text. |
| Page range | e.g. `1,3,5-7`. Applies only when you convert **a single file**; it's ignored for batches. |

### Scanned PDFs and OCR

A PDF made from scanned pages contains pictures of text, not text. Converting it normally gives an
**empty file** — the app can't read the picture without OCR. To get the text:

1. **Install the OCR backend once** (it's separate and large — see [Hybrid/OCR setup](#hybridocr-setup)).
2. In the **Hybrid / OCR Backend** panel, select the **OCR languages** that match your document
   (⌘-click to pick several; default is English only). These are fixed when the backend starts —
   change them, then restart the backend.
3. Click **Start Backend** and wait for it to say *Running*. The first start with a new language
   downloads its model, so it needs internet and can take a minute or more.
4. Tick **Enable hybrid processing for this run** and set **Mode** to **Full**.
5. Click **Convert**.

**Use Full for scans.** *Auto* only sends "complex" pages to OCR, and a scanned page isn't one — on a
test scan, Auto returned nothing while Full returned the whole text. *Force OCR* is for something
different: re-reading pages that *already have* a text layer; a plain scan doesn't need it.

The same panel has two optional extras — **Formula recognition** (equations as LaTeX) and **Picture
descriptions** (alt text for images). Tick them *before* starting the backend, and use Mode **Full**
so their output reaches the file.

If a Markdown file comes out empty, the result row shows ⚠ with advice matching your settings.
OCR results can occasionally come back empty even with everything set correctly (we saw it a few
times in ~25 test runs, cause unknown) — **converting again normally fixes it**. The
app stops the backend when you quit.

### Troubleshooting

| You see | Do this |
|---|---|
| ⚠ "The Markdown output is empty…" | Almost always a scanned PDF — follow [Scanned PDFs and OCR](#scanned-pdfs-and-ocr). If you already used Full mode, check the languages and convert once more. |
| **Convert** is greyed out | It needs at least one PDF, an output folder, and Java (see the banner). |
| Banner: Java not found | Install Java 11+ (**Download Java…**), then **Re-check** — no relaunch needed. |
| "Couldn't find 'opendataloader-pdf-hybrid'…" | The OCR backend isn't installed where the app looks — run the install command in [Hybrid/OCR setup](#hybridocr-setup). |
| Backend stays on *Starting…* | The first start can take minutes (model downloads). If it errors, the panel shows the backend's last output. |
| Backend won't start: port in use | Change the **Port** field (default 5002) and start again. |
| "These input files share the same name…" | Rename them or convert the folders separately. |
| Dropped something and it was skipped | Only PDFs and folders are accepted; the log notes what was skipped. |
| macOS says the app can't be opened | Right-click the app → **Open** (once). It isn't notarized. |
| Want to reset all settings | Quit the app and delete `~/Library/Application Support/ODL Desktop/prefs.json`. |

## Project layout

```
odl-desktop/
├── app.py                    # entry point — creates the pywebview window, wires the JS↔Python bridge
├── backend/
│   ├── api.py                 # the Api class exposed to the frontend (window.pywebview.api.*)
│   ├── dragdrop.py            # native drag-and-drop of PDFs/folders onto the window (Python-side; see file docstring)
│   ├── converter.py           # wraps opendataloader_pdf.convert(); UI settings → CLI kwargs → results
│   ├── hybrid_server.py       # start/stop/health-check for the local hybrid/OCR backend process
│   ├── java_check.py          # verifies Java 11+ is on PATH before Convert is enabled
│   └── prefs.py               # persists last-used settings to ~/Library/Application Support
├── ui/
│   ├── index.html             # layout; titlebar links to the OpenDataLoader docs
│   ├── style.css
│   └── app.js                 # all frontend logic — no framework, no build step
├── assets/
│   ├── icon_1024.png          # source art for the app icon (original artwork, not OpenDataLoader's)
│   └── AppIcon.icns           # compiled icon, referenced by setup.py's OPTIONS["iconfile"]
├── requirements.txt
├── setup.py                  # py2app config for building the .app
├── LICENSE                   # MIT, this project's own code
├── THIRD_PARTY_NOTICES.md    # Apache-2.0 attribution for the bundled opendataloader-pdf dependency
├── THIRD_PARTY_LICENSE.txt   # full Apache 2.0 text, copied from opendataloader-pdf's own LICENSE
├── ROADMAP.md                # planned features, not yet implemented
└── README.md
```

## Development setup

```bash
git clone https://github.com/wongchunhoi9/odl-desktop.git
cd odl-desktop
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

`requirements.txt` installs `pywebview` and `opendataloader-pdf[hybrid]` — the hybrid extra pulls
in `docling`/`torch`/OCR engines, so the first install takes a while and a few hundred MB. If you
only want the core conversion (no OCR), `pip install pywebview opendataloader-pdf` is enough; the
hybrid panel will just tell you the extra isn't installed if you try to use it.

## Building the .app

```bash
pip install py2app
python setup.py py2app
```

Output lands in `dist/ODL Desktop.app`, matching whatever architecture you build on (arm64 on
Apple Silicon, x86_64 on Intel — py2app doesn't cross-compile or produce universal binaries by
default). Since it isn't notarized, first launch needs a right-click → Open to get past Gatekeeper.

A couple of things `setup.py` does that are easy to break by "cleaning up":

- **`opendataloader_pdf` is under `includes`, not `packages`.** `packages` forces py2app to
  recursively bundle a package's entire submodule tree — including `hybrid_server.py`'s
  `docling`/`torch` imports, which this app never touches in-process (the hybrid backend runs as a
  separate OS subprocess via its own console script). That blows past Python's import-scan
  recursion limit and would bundle several GB of unused ML dependencies. `includes` makes py2app
  follow only what's actually imported (`wrapper.py`, `convert_generated.py`, etc.) — which, via
  `importlib.resources`, still picks up the package's ~24MB bundled Java CLI jar as data, extracted
  transparently from the zip at runtime. Verified by running a real conversion through the packaged
  app's embedded interpreter directly (`Contents/MacOS/python`, with `PYTHONHOME`/`PYTHONPATH`
  pointed at `Contents/Resources` so it resolves the bundle instead of falling back to the system
  Python).
- **`_find_conda_dylibs()` only matters if you build from a conda-based Python.** py2app's
  dependency scanner misses several `@rpath`-linked dylibs (`libffi`, `libssl`, `libcrypto`, etc.)
  that conda Python's stdlib C extensions need — without them the built app fails to launch with
  `Library not loaded: @rpath/lib*.dylib`. This function locates and bundles them explicitly. If it
  raises, your conda env is missing one of those libs under `<sys.base_prefix>/lib`; on a
  non-conda Python this code path isn't exercised.

## Creating a GitHub Release

To publish a build for others to download from the repo's Releases page:

```bash
# 1. Build the .app (see above), then zip it — GitHub Releases wants a file, not a raw .app bundle
cd dist && zip -r "ODL-Desktop-macOS-arm64.zip" "ODL Desktop.app" && cd ..

# 2. Tag the commit you're releasing
git tag v0.1.0
git push origin v0.1.0

# 3. Create the release and attach the zip
gh release create v0.1.0 "dist/ODL-Desktop-macOS-arm64.zip" \
  --title "v0.1.0" \
  --notes "First public build. Apple Silicon only — see README for Intel."
```

`gh release create` also works without a pre-existing tag (pass `--target main` and it creates the
tag for you). Bump the version in two places when cutting a real release: `setup.py`'s
`CFBundleShortVersionString` and the git tag should match. Since current builds are arm64-only,
say so in the release notes/asset name (as above) rather than implying it's universal.

## Licensing

ODL Desktop's own code is [MIT licensed](LICENSE).

It depends on and bundles [`opendataloader-pdf`](https://pypi.org/project/opendataloader-pdf/)
(Apache License 2.0, © Hancom, Inc.). Apache-2.0 permits using, depending on, and redistributing
that package — including inside this app's `.app` bundle — but **§6 (Trademarks)** explicitly does
*not* grant rights to OpenDataLoader's name, logo, or other marks. Concretely:

- Calling `opendataloader_pdf.convert()` from [converter.py](backend/converter.py) and shipping the
  package inside the packaged app: fine, covered by the license.
- Reusing OpenDataLoader's own logo or name as this app's branding: **not** covered — this app's
  icon is original artwork for that reason.
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
  [THIRD_PARTY_LICENSE.txt](THIRD_PARTY_LICENSE.txt) carry the required §4 attribution forward —
  `setup.py` bundles both into the packaged `.app`.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for planned features (file-list thumbnails, single-page preview) —
not implemented yet.

## Notes / things left intentionally simple for now

- Conversion runs synchronously in a background thread per batch; there's no persistent job queue.
- Hybrid backend lifecycle is manual (you click Start/Stop) rather than auto-managed, so you
  always know whether a background process is alive.
- Settings persistence is a flat JSON file, not a real settings UI.
- `backend/hybrid_server.py` launches the hybrid backend via the `opendataloader-pdf-hybrid`
  console script installed by the `opendataloader-pdf[hybrid]` extra, located by
  `find_hybrid_executable()` (`PATH` first, then `_candidate_bin_dirs()`). The child process gets the
  app's environment minus the Python/dyld variables the py2app launcher sets (`_PYTHON_ENV_VARS`) —
  without that, a venv-installed backend inherits `PYTHONHOME` pointing into the `.app` bundle and
  crashes at startup. If a future version of the package renames or moves that entry point, update
  `HYBRID_SERVER_EXECUTABLE` there.
- The OCR language picker (`ui/app.js`'s `EASYOCR_LANGUAGES`) is a hand-copied snapshot of
  `easyocr.config.all_lang_list` with human-readable names — it assumes the hybrid backend's
  default `--ocr-engine` (easyocr). Tesseract/RapidOCR/ocrmac use different code systems entirely
  (see `--ocr-engine`/`--ocr-lang` help in the installed `opendataloader-pdf[hybrid]` package); this
  app doesn't expose an engine picker, so switching engines would need this list swapped out too.
  Regenerate the list from `easyocr.config.all_lang_list` if the bundled easyocr version's language
  coverage changes.
- Same-named PDFs converted together (e.g. two `report.pdf` files from different subfolders with
  "Include subfolders" on) would silently overwrite each other's output, since the underlying CLI
  writes every input into one flat output folder named only by its stem. `run_conversion` detects
  this before converting and refuses the batch with a clear message rather than losing data.
