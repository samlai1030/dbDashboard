"""Extract/copy selected data files from sync_folder into data_folder."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import zipfile
from pathlib import Path

from app_config import cfg
from dataset_selection import is_excluded_path

SYNC_FOLDER = cfg.sync_folder
DATA_FOLDER = cfg.data_folder
DATA_EXTENSIONS = cfg.data_extensions
ARCHIVE_EXTENSIONS = cfg.archive_extensions
EXCLUDED_PATH_KEYWORDS = cfg.excluded_path_keywords


def _extract_archive(filepath: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if filepath.suffix.lower() == ".zip":
        if not zipfile.is_zipfile(filepath):
            raise ValueError("not a valid zip file")
        with zipfile.ZipFile(filepath, "r") as archive:
            archive.extractall(target)
        return

    result = subprocess.run(
        ["unrar", "x", "-o+", "-y", str(filepath), str(target) + "/"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def _extract_nested_archives(root: Path) -> tuple[int, int]:
    """Extract archives found inside an extracted production archive."""
    extracted = 0
    errors = 0
    processed: set[Path] = set()

    while True:
        archives = [
            path
            for path in sorted(root.rglob("*"))
            if path.is_file()
            and path.suffix.lower() in ARCHIVE_EXTENSIONS
            and path not in processed
        ]
        if not archives:
            break

        for archive in archives:
            processed.add(archive)
            relative_path = archive.relative_to(root)
            if is_excluded_path(relative_path, EXCLUDED_PATH_KEYWORDS):
                continue
            target = archive.parent / archive.stem
            try:
                _extract_archive(archive, target)
                print(f"  EXTRACT NESTED  {relative_path}  ->  {target.relative_to(root)}/")
                extracted += 1
            except Exception as error:
                print(f"  EXTRACT FAILED  {relative_path}  ({error})")
                errors += 1

    return extracted, errors


def scan_and_move(src: Path, dst: Path, *, dry_run: bool = False) -> None:
    copied = 0
    extracted = 0
    skipped = 0
    errors = 0

    for filepath in sorted(src.rglob("*")):
        if not filepath.is_file():
            continue

        relative_path = filepath.relative_to(src)
        if is_excluded_path(relative_path, EXCLUDED_PATH_KEYWORDS):
            skipped += 1
            continue

        extension = filepath.suffix.lower()
        destination_dir = dst / relative_path.parent

        if extension in ARCHIVE_EXTENSIONS:
            target = destination_dir / filepath.stem
            if target.exists() and target.stat().st_mtime >= filepath.stat().st_mtime:
                skipped += 1
                continue
            if dry_run:
                print(f"  [DRY] EXTRACT  {relative_path}  ->  {target.relative_to(dst)}/")
                extracted += 1
                continue
            try:
                _extract_archive(filepath, target)
                print(f"  EXTRACT  {relative_path}  ->  {target.relative_to(dst)}/")
                extracted += 1
                nested_count, nested_errors = _extract_nested_archives(target)
                extracted += nested_count
                errors += nested_errors
            except Exception as error:
                print(f"  EXTRACT FAILED  {relative_path}  ({error})")
                errors += 1
            continue

        if extension not in DATA_EXTENSIONS:
            skipped += 1
            continue

        destination = destination_dir / filepath.name
        if destination.exists() and destination.stat().st_size == filepath.stat().st_size:
            skipped += 1
            continue
        if dry_run:
            print(f"  [DRY] COPY  {relative_path}  ->  {destination.relative_to(dst)}")
        else:
            destination_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filepath, destination)
            print(f"  COPY  {relative_path}  ->  {destination.relative_to(dst)}")
        copied += 1

    print(
        f"\nDone: {copied} copied, {extracted} archives extracted, "
        f"{skipped} skipped, {errors} errors"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract/copy selected data files from sync_folder to data_folder"
    )
    parser.add_argument("--src", default=str(SYNC_FOLDER), help="Source folder to scan")
    parser.add_argument("--dst", default=str(DATA_FOLDER), help="Destination data folder")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    src = Path(args.src)
    dst = Path(args.dst)
    if not src.exists():
        print(f"Error: source folder not found: {src}")
        return

    dst.mkdir(parents=True, exist_ok=True)
    print(f"Scanning: {src}")
    print(f"Dest:     {dst}")
    print(f"Excludes: {EXCLUDED_PATH_KEYWORDS}")
    print(f"{'[DRY RUN]' if args.dry_run else ''}\n")
    scan_and_move(src, dst, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
