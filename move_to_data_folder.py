"""
move_to_data_folder.py — Scan sync_folder and extract/copy data files to data_folder.

Rules:
    .zip          → unzip into data_folder (preserving subfolder structure)
    .rar          → unrar into data_folder (preserving subfolder structure)
    .csv/.xls/.xlsx → copy to data_folder  (preserving subfolder structure)

Usage:
    python move_to_data_folder.py                  # run with defaults
    python move_to_data_folder.py --dry-run         # preview only
    python move_to_data_folder.py --src ./other_sync --dst ./other_data
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from app_config import cfg

SYNC_FOLDER = cfg.sync_folder
DATA_FOLDER = cfg.data_folder

DATA_EXTENSIONS = cfg.data_extensions


def scan_and_move(src: Path, dst: Path, *, dry_run: bool = False) -> None:
    copied, unzipped, skipped, errors = 0, 0, 0, 0

    for filepath in sorted(src.rglob("*")):
        if not filepath.is_file():
            continue

        rel = filepath.relative_to(src)
        ext = filepath.suffix.lower()
        dest_dir = dst / rel.parent

        # --- ZIP ---
        if ext == ".zip":
            if not zipfile.is_zipfile(filepath):
                print(f"  ⚠ Not a valid zip: {rel}")
                skipped += 1
                continue

            unzip_target = dest_dir / filepath.stem

            # Skip if already extracted and zip hasn't been updated since
            if unzip_target.exists() and unzip_target.stat().st_mtime >= filepath.stat().st_mtime:
                skipped += 1
                continue

            if dry_run:
                print(f"  [DRY] UNZIP  {rel}  →  {unzip_target.relative_to(dst)}/")
            else:
                unzip_target.mkdir(parents=True, exist_ok=True)
                try:
                    with zipfile.ZipFile(filepath, "r") as zf:
                        zf.extractall(unzip_target)
                    print(f"  ✓ UNZIP  {rel}  →  {unzip_target.relative_to(dst)}/")
                except Exception as e:
                    print(f"  ✗ UNZIP FAILED  {rel}  ({e})")
                    errors += 1
                    continue
            unzipped += 1

        # --- RAR ---
        elif ext == ".rar":
            unrar_target = dest_dir / filepath.stem

            # Skip if already extracted and rar hasn't been updated since
            if unrar_target.exists() and unrar_target.stat().st_mtime >= filepath.stat().st_mtime:
                skipped += 1
                continue

            if dry_run:
                print(f"  [DRY] UNRAR  {rel}  \u2192  {unrar_target.relative_to(dst)}/")
            else:
                unrar_target.mkdir(parents=True, exist_ok=True)
                try:
                    result = subprocess.run(
                        ["unrar", "x", "-o+", "-y", str(filepath), str(unrar_target) + "/"],
                        capture_output=True, text=True, timeout=300,
                    )
                    if result.returncode != 0:
                        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
                    print(f"  \u2713 UNRAR  {rel}  \u2192  {unrar_target.relative_to(dst)}/")
                except Exception as e:
                    print(f"  \u2717 UNRAR FAILED  {rel}  ({e})")
                    errors += 1
                    continue
            unzipped += 1

        # --- CSV / XLS / XLSX ---
        elif ext in DATA_EXTENSIONS:
            dest_file = dest_dir / filepath.name
            if (
                dest_file.exists()
                and dest_file.stat().st_size == filepath.stat().st_size
            ):
                skipped += 1
                continue

            if dry_run:
                print(f"  [DRY] COPY   {rel}  →  {dest_file.relative_to(dst)}")
            else:
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(filepath, dest_file)
                print(f"  ✓ COPY   {rel}  →  {dest_file.relative_to(dst)}")
            copied += 1

        else:
            skipped += 1

    print(
        f"\nDone: {copied} copied, {unzipped} unzipped, {skipped} skipped, {errors} errors"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract/copy data files from sync_folder → data_folder"
    )
    parser.add_argument(
        "--src", type=str, default=str(SYNC_FOLDER), help="Source folder to scan"
    )
    parser.add_argument(
        "--dst", type=str, default=str(DATA_FOLDER), help="Destination data folder"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without copying/extracting"
    )
    args = parser.parse_args()

    src = Path(args.src)
    dst = Path(args.dst)

    if not src.exists():
        print(f"Error: source folder not found: {src}")
        return

    dst.mkdir(parents=True, exist_ok=True)

    print(f"Scanning: {src}")
    print(f"Dest:     {dst}")
    print(f"{'[DRY RUN]' if args.dry_run else ''}\n")

    scan_and_move(src, dst, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
