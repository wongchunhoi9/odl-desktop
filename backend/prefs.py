"""Loads and saves last-used UI settings to a small JSON file.

Kept deliberately dumb: no schema migrations, no validation beyond a fallback
to defaults if the file is missing or corrupt. Good enough for a personal tool.
"""

import json
from pathlib import Path

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "ODL Desktop"
PREFS_PATH = APP_SUPPORT_DIR / "prefs.json"

DEFAULTS = {
    "output_dir": str(Path.home() / "Documents" / "OpenDataLoader Output"),
    "include_subfolders": False,
    "formats": ["markdown"],
    "include_header_footer": False,
    "table_method": "default",       # "default" | "cluster"
    "reading_order": "xycut",        # "xycut" | "off"
    "image_output": "off",           # "off" | "embedded" | "external"
    "image_format": "png",           # "png" | "jpeg"
    "sanitize": False,
    "page_range": "",
    "hybrid_enabled": False,
    "hybrid_mode": "auto",           # "auto" | "full"
    "force_ocr": False,
    "ocr_lang": "en",
    "enrich_formula": False,
    "enrich_picture_description": False,
    "hybrid_port": 5002,
}


def load() -> dict:
    if not PREFS_PATH.exists():
        return dict(DEFAULTS)
    try:
        with open(PREFS_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update(saved)
    return merged


def save(settings: dict) -> None:
    APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(PREFS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
