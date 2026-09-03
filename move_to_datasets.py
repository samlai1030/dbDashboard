"""Select online summary files and stage them in datasets/."""

from __future__ import annotations

import argparse
from pathlib import Path

from app_config import cfg
from dataset_selection import stage_matching_files

DATA_FOLDER = cfg.data_folder
DATASETS_FOLDER = cfg.datasets
TARGET_KEYWORDS = cfg.dataset_keywords
DATA_EXTENSIONS = cfg.data_extensions
EXCLUDED_PATH_KEYWORDS = cfg.excluded_path_keywords


def scan_and_copy(src: Path, dst: Path, *, dry_run: bool = False) -> None:
    copied, skipped = stage_matching_files(
        src,
        dst,
        keywords=TARGET_KEYWORDS,
        extensions=DATA_EXTENSIONS,
        excluded_keywords=EXCLUDED_PATH_KEYWORDS,
        manifest_path=cfg.output_folder / "online_import_manifest.csv",
        dry_run=dry_run,
    )
    print(f"\nDone: {copied} copied, {skipped} unchanged")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy configured online summary files into datasets/"
    )
    parser.add_argument("--src", default=str(DATA_FOLDER), help="Source folder to scan")
    parser.add_argument("--dst", default=str(DATASETS_FOLDER), help="Destination folder")
    parser.add_argument("--dry-run", action="store_true", help="Preview without copying")
    args = parser.parse_args()

    src = Path(args.src)
    dst = Path(args.dst)
    if not src.exists():
        print(f"Error: source folder not found: {src}")
        return

    print(f"Scanning: {src}")
    print(f"Keywords: {TARGET_KEYWORDS}")
    print(f"Excludes: {EXCLUDED_PATH_KEYWORDS}")
    print(f"Dest:     {dst}")
    print(f"{'[DRY RUN]' if args.dry_run else ''}\n")
    scan_and_copy(src, dst, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
