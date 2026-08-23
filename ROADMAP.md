# Roadmap

Planning notes for upcoming features — not implemented yet.

## Phase 2: file-list thumbnails

**Goal**: show a small cover-page thumbnail next to each file in the input chip list
(`ui/index.html`'s `#input-chip-list`, rendered by `renderChips()` in `ui/app.js`), so it's
obvious at a glance which files are queued up, especially for folder drops with many
similarly-named PDFs.

**Approach**: render server-side in Python, not client-side in the webview.

- Add [`pypdfium2`](https://pypdfium2.readthedocs.io/) to `requirements.txt`. It's pure-Python
  bindings to Chromium's PDF renderer (pdfium), ships prebuilt wheels per platform (no poppler/
  system dependency to install separately, unlike `pdf2image`), and its license (Apache-2.0 OR
  BSD-3-Clause for pdfium itself, MIT for the bindings) is compatible with bundling the way
  `opendataloader-pdf` already is — will need a `THIRD_PARTY_NOTICES.md` entry alongside it.
- New `backend/thumbnails.py`: render page 1 of a PDF to a small PNG (~120px wide) and return it
  as a base64 data URL. Cache in an in-memory dict keyed by `(resolved_path, mtime)` for the
  session, so re-adding the same files doesn't re-render. Handle encrypted/corrupted/0-page PDFs
  by falling back to a generic placeholder icon rather than failing the whole batch.
- New `Api.get_thumbnails(paths: list) -> dict` in `backend/api.py`, called once per batch of
  newly-added paths from `addInputPaths()` in `ui/app.js` (not one call per file — keep it one
  bridge round-trip per add action).
- `renderChips()` grows an `<img class="chip-thumb">` per chip; `ui/style.css` needs a small
  chip-card layout update (thumbnail + filename + remove button, instead of just text + button).
- **Packaging risk to verify before shipping**: same class of issue we already hit twice this
  session (the JAR not being bundled, then conda dylibs not being bundled) — `pypdfium2` ships a
  native shared library (`pdfium.dylib` or similar) that py2app's dependency scanner may or may not
  pick up automatically. Verify with the same technique used earlier: run a real thumbnail render
  through the packaged `.app`'s embedded interpreter (`Contents/MacOS/python` with
  `PYTHONHOME`/`PYTHONPATH` pointed at `Contents/Resources`) before considering this feature done,
  not just "the window opens without errors."

## Phase 3: one-page preview

**Goal**: let the user preview a single rendered page of a PDF before converting — default page 1,
user-specified page number, shown as an on-demand larger image (not just a thumbnail).

**Approach**: extends Phase 2's rendering path rather than being a separate mechanism.

- Design `backend/thumbnails.py`'s render function with `page: int = 0` and a `max_width`/`max_height`
  param from the start (even though Phase 2 only calls it with page 0 at thumbnail size), so Phase 3
  is "call the same function with different arguments" instead of a parallel code path.
- Add `Api.get_page_count(path) -> int` so the UI can clamp/validate the page-number input against
  the actual PDF (needed regardless of implementation, since users will type out-of-range numbers).
- UI: clicking a chip's thumbnail (or a dedicated "Preview" action) opens a lightweight overlay
  (plain `<dialog>` or an absolutely-positioned div — matching the app's existing no-framework,
  vanilla-JS style, not a new dependency) showing the larger rendered page, with a page-number
  input defaulting to 1 and re-rendering on change.
- Bound an in-memory LRU-ish cache of recently-previewed `(path, page, size)` renders so flipping
  back and forth between a few pages doesn't re-render every time, without growing unbounded over
  a long session with many large files opened.

## Cross-cutting notes for whoever picks this up

- Test against real sample PDFs, not hand-crafted ones — this session's bug fixes were only caught
  because testing used [opendataloader-pdf's own `samples/pdf/`](https://github.com/opendataloader-project/opendataloader-pdf/tree/main/samples/pdf)
  files (`lorem.pdf` and others) rather than synthetic ones; a hand-rolled minimal PDF earlier in
  this session turned out to be malformed and gave a false read on what was actually broken.
- Both features are read-only/local — no new external dependency beyond `pypdfium2`, no network
  calls, consistent with the app's "everything runs locally" positioning.
