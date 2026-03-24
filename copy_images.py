"""
copy_images.py — Copy SFR ROI images from data_folder/ to images/ and link to DB.

Scans data_folder recursively for *_roi.jpg files inside MetaData/SFR and
MetaData/SubSFR folders.  Copies them into a flat images/ folder with
TSRID-based naming, then updates sfr_data with relative image paths.

Usage:
    python copy_images.py              # copy images and update DB
    python copy_images.py --dry-run    # preview without copying or writing DB
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
from pathlib import Path

from app_config import cfg

TABLE_NAME = "sfr_data"
UNIQUE_KEY = "TSRID"

# Image category → (DB column name, flat filename suffix)
IMG_CATEGORIES: dict[str, str] = {
    "SFR_25cm": "img_SFR_25cm",
    "IR_SFR_25cm": "img_IR_SFR_25cm",
    "SubSFR": "img_SubSFR",
    "IR_SubSFR": "img_IR_SubSFR",
}

# Regex to identify the TSRID folder (all-digit folder name)
TSRID_FOLDER_RE = re.compile(r"^\d{10,}$")


def _classify_image(img_path: Path) -> str | None:
    """Return the category key (e.g. 'SFR_25cm') for a *_roi.jpg image."""
    parent_folder = img_path.parent.name  # 'SFR' or 'SubSFR'
    fname = img_path.name
    is_ir = "_IR_" in fname

    if parent_folder == "SFR":
        return "IR_SFR_25cm" if is_ir else "SFR_25cm"
    elif parent_folder == "SubSFR":
        return "IR_SubSFR" if is_ir else "SubSFR"
    return None


def _extract_tsrid_folder(img_path: Path) -> str | None:
    """Walk up the path to find the numeric TSRID folder name."""
    # Expected: .../TSRID_folder/MetaData/SFR(or SubSFR)/image.jpg
    # So TSRID folder is grandparent of parent → img.parent.parent.parent
    candidate = img_path.parent.parent.parent
    if TSRID_FOLDER_RE.match(candidate.name):
        return candidate.name
    # Fallback: walk up to find any matching ancestor
    for p in img_path.parents:
        if TSRID_FOLDER_RE.match(p.name):
            return p.name
    return None


def _flat_filename(tsrid_folder: str, category: str) -> str:
    """Build the flat destination filename."""
    return f"{tsrid_folder}_{category}_roi.jpg"


def scan_images(data_folder: Path) -> list[dict]:
    """Find all *_roi.jpg files and classify them.

    Returns list of dicts with keys:
        src, tsrid_folder, db_tsrid, category, col_name, dest_name, rel_path
    """
    results = []
    for img in sorted(data_folder.rglob("*_roi.jpg")):
        category = _classify_image(img)
        if category is None:
            continue

        tsrid_folder = _extract_tsrid_folder(img)
        if tsrid_folder is None:
            continue

        dest_name = _flat_filename(tsrid_folder, category)
        results.append(
            {
                "src": img,
                "tsrid_folder": tsrid_folder,
                "db_tsrid": f"_{tsrid_folder}",
                "category": category,
                "col_name": IMG_CATEGORIES[category],
                "dest_name": dest_name,
                "rel_path": f"images/{dest_name}",
            }
        )
    return results


def _ensure_img_columns(conn: sqlite3.Connection) -> None:
    """Add img_ columns to sfr_data if they don't exist."""
    existing = set()
    try:
        cur = conn.execute(f'PRAGMA table_info("{TABLE_NAME}")')
        existing = {row[1] for row in cur.fetchall()}
    except sqlite3.OperationalError:
        return

    for col_name in IMG_CATEGORIES.values():
        if col_name not in existing:
            conn.execute(
                f'ALTER TABLE "{TABLE_NAME}" ADD COLUMN "{col_name}" TEXT'
            )
    conn.commit()


def copy_images(
    data_folder: Path,
    images_folder: Path,
    db_path: Path,
    *,
    dry_run: bool = False,
) -> None:
    images = scan_images(data_folder)

    if not images:
        print("No *_roi.jpg images found in data_folder.")
        return

    # Group by TSRID for summary
    tsrids = sorted({img["tsrid_folder"] for img in images})
    print(f"Found {len(images)} images across {len(tsrids)} TSRIDs\n")

    # --- Copy files ---
    copied, skipped = 0, 0
    for img in images:
        dest = images_folder / img["dest_name"]
        if dest.exists():
            skipped += 1
            continue

        if dry_run:
            print(f"  [DRY] {img['src'].name}  →  {img['dest_name']}")
        else:
            shutil.copy2(img["src"], dest)
        copied += 1

    action = "Would copy" if dry_run else "Copied"
    print(f"\n{action} {copied} images, skipped {skipped} (already exist)")

    # --- Update DB ---
    if not db_path.exists():
        print(f"\nWarning: database not found: {db_path} — skipping DB update")
        return

    conn = sqlite3.connect(str(db_path))

    if not dry_run:
        _ensure_img_columns(conn)
    else:
        print("\n[DRY] Would add columns:", list(IMG_CATEGORIES.values()))

    # Build update map:  db_tsrid → {col_name: rel_path, ...}
    update_map: dict[str, dict[str, str]] = {}
    for img in images:
        tsrid = img["db_tsrid"]
        update_map.setdefault(tsrid, {})[img["col_name"]] = img["rel_path"]

    updated, not_found = 0, 0
    for db_tsrid, col_vals in sorted(update_map.items()):
        # Check if TSRID exists in DB
        row = conn.execute(
            f'SELECT 1 FROM "{TABLE_NAME}" WHERE "{UNIQUE_KEY}" = ? LIMIT 1',
            (db_tsrid,),
        ).fetchone()

        if row is None:
            not_found += 1
            if dry_run:
                print(f"  [DRY] TSRID {db_tsrid} not found in DB")
            continue

        if dry_run:
            for col, path in col_vals.items():
                print(f"  [DRY] UPDATE {db_tsrid}: {col} = {path}")
        else:
            set_clause = ", ".join(f'"{c}" = ?' for c in col_vals)
            values = list(col_vals.values()) + [db_tsrid]
            conn.execute(
                f'UPDATE "{TABLE_NAME}" SET {set_clause} WHERE "{UNIQUE_KEY}" = ?',
                values,
            )
        updated += 1

    if not dry_run:
        conn.commit()

    conn.close()

    action = "Would update" if dry_run else "Updated"
    print(f"\n{action} {updated} rows in sfr_data, {not_found} TSRIDs not in DB")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy SFR ROI images and link to DB"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without copying or writing DB"
    )
    args = parser.parse_args()

    data_folder = cfg.data_folder
    images_folder = cfg.images_folder
    db_path = cfg.db_file

    if not data_folder.exists():
        print(f"Error: data_folder not found: {data_folder}")
        return

    images_folder.mkdir(parents=True, exist_ok=True)

    print(f"Data folder : {data_folder}")
    print(f"Images dest : {images_folder}")
    print(f"Database    : {db_path}")
    if args.dry_run:
        print("[DRY RUN]\n")
    else:
        print()

    copy_images(data_folder, images_folder, db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
