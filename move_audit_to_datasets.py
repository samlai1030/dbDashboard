"""
move_audit_to_datasets.py — Scan data_folder for AuditTest_AUDIT files
and copy them to audit_datasets/ if not already there.

Usage:
    python move_audit_to_datasets.py              # run
    python move_audit_to_datasets.py --dry-run    # preview only
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from app_config import cfg

DATA_FOLDER = cfg.data_folder
AUDIT_DATASETS_FOLDER = cfg.audit_datasets

TARGET_KEYWORD = cfg.audit_keyword
DATA_EXTENSIONS = cfg.data_extensions


def scan_and_copy(src: Path, dst: Path, *, dry_run: bool = False) -> None:
    copied, skipped = 0, 0

    existing = {f.name for f in dst.iterdir() if f.is_file()} if dst.exists() else set()

    for filepath in sorted(src.rglob("*")):
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() not in DATA_EXTENSIONS:
            continue
        if TARGET_KEYWORD not in filepath.name:
            continue

        if filepath.name in existing:
            skipped += 1
            continue

        if dry_run:
            print(
                f"  [DRY] COPY  {filepath.relative_to(src)}  →  audit_datasets/{filepath.name}"
            )
        else:
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filepath, dst / filepath.name)
            print(f"  ✓ COPY  {filepath.relative_to(src)}  →  audit_datasets/{filepath.name}")
            existing.add(filepath.name)
        copied += 1

    print(f"\nDone: {copied} copied, {skipped} already in audit_datasets")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy AuditTest_AUDIT data files → audit_datasets/"
    )
    parser.add_argument(
        "--src", type=str, default=str(DATA_FOLDER), help="Source folder to scan"
    )
    parser.add_argument(
        "--dst",
        type=str,
        default=str(AUDIT_DATASETS_FOLDER),
        help="Destination audit_datasets folder",
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
    print(f"Keyword:  {TARGET_KEYWORD}")
    print(f"Dest:     {dst}")
    print(f"{'[DRY RUN]' if args.dry_run else ''}\n")

    scan_and_copy(src, dst, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
