"""
move_to_datasets.py — Scan data_folder for Summary_LanSi_Loma_CW_1_01_ONLINE files
and copy them to datasets/ if not already there.

Usage:
    python move_to_datasets.py              # run
    python move_to_datasets.py --dry-run    # preview only
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from app_config import cfg

DATA_FOLDER = cfg.data_folder
DATASETS_FOLDER = cfg.datasets

TARGET_KEYWORDS = cfg.dataset_keywords
DATA_EXTENSIONS = cfg.data_extensions


def scan_and_copy(src: Path, dst: Path, *, dry_run: bool = False) -> None:
    copied, skipped = 0, 0

    existing = {f.name for f in dst.iterdir() if f.is_file()} if dst.exists() else set()

    for filepath in sorted(src.rglob("*")):
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() not in DATA_EXTENSIONS:
            continue
        if not any(kw in filepath.name for kw in TARGET_KEYWORDS):
            continue

        if filepath.name in existing:
            skipped += 1
            continue

        if dry_run:
            print(
                f"  [DRY] COPY  {filepath.relative_to(src)}  →  datasets/{filepath.name}"
            )
        else:
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filepath, dst / filepath.name)
            print(f"  ✓ COPY  {filepath.relative_to(src)}  →  datasets/{filepath.name}")
            existing.add(filepath.name)
        copied += 1

    print(f"\nDone: {copied} copied, {skipped} already in datasets")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy Summary_LanSi_Loma_CW_1_01_ONLINE data files → datasets/"
    )
    parser.add_argument(
        "--src", type=str, default=str(DATA_FOLDER), help="Source folder to scan"
    )
    parser.add_argument(
        "--dst",
        type=str,
        default=str(DATASETS_FOLDER),
        help="Destination datasets folder",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without copying"
    )
    args = parser.parse_args()

    src = Path(args.src)
    dst = Path(args.dst)

    if not src.exists():
        print(f"Error: source folder not found: {src}")
        return

    print(f"Scanning: {src}")
    print(f"Keywords: {TARGET_KEYWORDS}")
    print(f"Dest:     {dst}")
    print(f"{'[DRY RUN]' if args.dry_run else ''}\n")

    scan_and_copy(src, dst, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
