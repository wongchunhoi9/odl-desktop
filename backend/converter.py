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

FORMAT_EXTENSIONS = {
    "markdown": ".md",
    "json": ".json",
    "html": ".html",
    "pdf": ".pdf",              # annotated/tagged pdf output
    "markdown-with-images": ".md",
}


@dataclass
class FileResult:
    input_path: str
    ok: bool
    outputs: list = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class ConversionResult:
    ok: bool
    files: list  # list[FileResult]
    error: Optional[str] = None


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


def _collect_results(input_files: list, output_dir: str, formats: list) -> list:
    out_dir = Path(output_dir)
    results = []
    for f in input_files:
        stem = f.stem
        outputs = []
        for fmt in formats:
            ext = FORMAT_EXTENSIONS.get(fmt, "")
            candidate = out_dir / f"{stem}{ext}"
            if candidate.exists():
                outputs.append(str(candidate))
        results.append(
            FileResult(input_path=str(f), ok=bool(outputs), outputs=outputs,
                       error=None if outputs else "No output file found after conversion.")
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

    report(f"Preparing to convert {len(input_files)} file(s)...")
    kwargs = build_convert_kwargs(settings, input_files, output_dir)

    try:
        report("Running OpenDataLoader (this spawns a local JVM process)...")
        opendataloader_pdf.convert(**kwargs)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        return ConversionResult(ok=False, files=[], error=f"Conversion failed: {exc}")

    report("Verifying outputs...")
    results = _collect_results(input_files, output_dir, settings.get("formats") or ["markdown"])
    overall_ok = any(r.ok for r in results)
    return ConversionResult(ok=overall_ok, files=results)
