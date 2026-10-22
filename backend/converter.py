"""Thin wrapper around opendataloader_pdf.convert().

Two responsibilities:
  1. Translate the settings dict coming from the UI into the kwargs the
     library expects.
  2. Run one batched convert() call (never loop-and-call-per-file — each
     call spawns a JVM, ~1-2s overhead) and figure out, per input file,
     whether an output was produced.

NOTE: the exact shape of convert()'s return value isn't nailed down here —
rather than guess at a schema and have it silently drift from reality, we
verify success by checking for the expected output file(s) on disk after the
call returns. If you confirm the real return schema, prefer using it
directly (it likely already tells you success/failure without a filesystem
probe) and simplify `_collect_results` accordingly.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import opendataloader_pdf

# Filename the CLI actually writes for each format, given an input stem.
# NOTE: pdf/tagged-pdf do NOT write "<stem>.pdf" — verified against the real
# CLI output, which suffixes them ("<stem>_annotated.pdf" / "<stem>_tagged.pdf")
# to avoid colliding with the source file's own name.
FORMAT_FILENAME_TEMPLATES = {
    "markdown": "{stem}.md",
    "json": "{stem}.json",
    "html": "{stem}.html",
    "pdf": "{stem}_annotated.pdf",        # visual-debugging output (bounding boxes)
    "tagged-pdf": "{stem}_tagged.pdf",    # accessibility-tagged PDF
    "markdown-with-images": "{stem}.md",
}


@dataclass
class FileResult:
    input_path: str
    ok: bool
    outputs: list = field(default_factory=list)
    error: Optional[str] = None
    warning: Optional[str] = None  # produced a file, but it looks wrong (e.g. empty)


@dataclass
class ConversionResult:
    ok: bool
    files: list  # list[FileResult]
    error: Optional[str] = None


# Only Markdown can be checked for "no text" cheaply — JSON/HTML always carry
# structure/boilerplate even when a scanned page yields no text.
_EMPTY_CHECKABLE_FORMATS = ("markdown", "markdown-with-images")


def _empty_output_hint(settings: dict) -> str:
    """Advice for an empty Markdown result, based on how hybrid/OCR was set."""
    if not settings.get("hybrid_enabled"):
        return (
            "The Markdown output is empty. If this is a scanned PDF (page images, no text "
            "layer), start the Hybrid/OCR backend, tick \"Enable hybrid processing for this "
            "run\", and set Mode to Full."
        )
    if settings.get("hybrid_mode", "auto") != "full":
        return (
            "The Markdown output is empty. Auto mode only sends complex pages to OCR — for "
            "scanned PDFs set Mode to Full."
        )
    return (
        "The Markdown output is empty even with OCR on. Check the OCR language matches the "
        "document (restart the backend after changing it); a language's first use downloads "
        "its model, so one retry may be needed."
    )


def _is_blank_text_file(path: str) -> bool:
    try:
        return not Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return False


def _gather_input_files(input_paths: list, include_subfolders: bool) -> list:
    """Expand any directories in input_paths into a flat list of .pdf files."""
    files = []
    for raw in input_paths:
        p = Path(raw)
        if p.is_dir():
            pattern = "**/*.pdf" if include_subfolders else "*.pdf"
            files.extend(sorted(p.glob(pattern)))
        elif p.suffix.lower() == ".pdf":
            files.append(p)
    return files


def _find_duplicate_stems(input_files: list) -> dict:
    """Maps filename stem -> paths, for stems shared by more than one input.

    The CLI writes every input's output into one flat output_dir named only
    by its stem (e.g. "report.md") — inputs with the same stem from different
    folders (common with "Include subfolders") silently overwrite each
    other's output on disk. Caught here so run_conversion can refuse the
    batch instead of losing one input's output silently.
    """
    by_stem: dict = {}
    for f in input_files:
        by_stem.setdefault(f.stem, []).append(f)
    return {stem: paths for stem, paths in by_stem.items() if len(paths) > 1}


def build_convert_kwargs(settings: dict, input_files: list, output_dir: str) -> dict:
    """Translate UI settings into opendataloader_pdf.convert() kwargs."""
    kwargs = {
        "input_path": [str(f) for f in input_files],
        "output_dir": output_dir,
        "format": ",".join(settings.get("formats") or ["markdown"]),
        "include_header_footer": bool(settings.get("include_header_footer", False)),
        "table_method": settings.get("table_method", "default"),
        "reading_order": settings.get("reading_order", "xycut"),
        "image_output": settings.get("image_output", "off"),
        "sanitize": bool(settings.get("sanitize", False)),
    }

    if settings.get("image_output") in ("embedded", "external"):
        kwargs["image_format"] = settings.get("image_format", "png")

    page_range = (settings.get("page_range") or "").strip()
    if page_range and len(input_files) == 1:
        kwargs["pages"] = page_range

    if settings.get("hybrid_enabled"):
        # Only `hybrid` and `hybrid_mode` are per-request client flags.
        # OCR and enrichment are configured when the backend server itself is
        # started (see backend/hybrid_server.py) — they are not passed here.
        kwargs["hybrid"] = "docling-fast"
        kwargs["hybrid_mode"] = settings.get("hybrid_mode", "auto")
        hybrid_port = settings.get("hybrid_port")
        if hybrid_port:
            kwargs["hybrid_url"] = f"http://localhost:{hybrid_port}"

    return kwargs


def _collect_results(input_files: list, output_dir: str, formats: list,
                     empty_hint: str = "") -> list:
    out_dir = Path(output_dir)
    results = []
    for f in input_files:
        stem = f.stem
        outputs = []
        blank_text_outputs = []
        for fmt in formats:
            template = FORMAT_FILENAME_TEMPLATES.get(fmt, "{stem}")
            candidate = out_dir / template.format(stem=stem)
            if candidate.exists():
                outputs.append(str(candidate))
                if fmt in _EMPTY_CHECKABLE_FORMATS and _is_blank_text_file(str(candidate)):
                    blank_text_outputs.append(str(candidate))
        results.append(
            FileResult(input_path=str(f), ok=bool(outputs), outputs=outputs,
                       error=None if outputs else "No output file found after conversion.",
                       warning=empty_hint if blank_text_outputs else None)
        )
    return results


def run_conversion(
    settings: dict,
    input_paths: list,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> ConversionResult:
    """Runs one batched conversion. Safe to call from a background thread."""
    def report(msg: str):
        if progress_callback:
            progress_callback(msg)

    output_dir = settings.get("output_dir")
    if not output_dir:
        return ConversionResult(ok=False, files=[], error="No output folder selected.")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    input_files = _gather_input_files(input_paths, settings.get("include_subfolders", False))
    if not input_files:
        return ConversionResult(ok=False, files=[], error="No PDF files found in the selection.")

    duplicates = _find_duplicate_stems(input_files)
    if duplicates:
        lines = [
            f"• {stem}.pdf ({len(paths)}x): " + ", ".join(str(p) for p in paths)
            for stem, paths in duplicates.items()
        ]
        return ConversionResult(
            ok=False,
            files=[],
            error=(
                "These input files share the same name and would overwrite each "
                "other's output:\n" + "\n".join(lines) +
                "\nRename the files, or convert the affected folders separately."
            ),
        )

    report(f"Preparing to convert {len(input_files)} file(s)...")
    kwargs = build_convert_kwargs(settings, input_files, output_dir)

    try:
        report("Running OpenDataLoader (this spawns a local JVM process)...")
        opendataloader_pdf.convert(**kwargs)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        return ConversionResult(ok=False, files=[], error=f"Conversion failed: {exc}")

    report("Verifying outputs...")
    results = _collect_results(input_files, output_dir, settings.get("formats") or ["markdown"],
                               empty_hint=_empty_output_hint(settings))
    overall_ok = any(r.ok for r in results)
    return ConversionResult(ok=overall_ok, files=results)
