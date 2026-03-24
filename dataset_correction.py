"""
dataset_correction.py — Fix column names in datasets/ files.

Rules:
    1. Replace '30cm' → '25cm' in all column names
    2. If column starts with 'IR_':
       - Remove the 'IR_' prefix
       - Replace '_VIS_' → '_IR_' in the remaining name

Examples:
    SFR_VIS_30cm_P0x          → SFR_VIS_25cm_P0x
    IR_SFR_VIS_30cm_P0x       → SFR_IR_25cm_P0x
    IR_sfr_30sfr_version      → sfr_25sfr_version
    IR_sfr_30modify_date      → sfr_25modify_date
    sfr_4sfr_version          → sfr_4sfr_version  (unchanged, no 30cm or IR_)

Usage:
    python dataset_correction.py --dry-run     # preview renames only
    python dataset_correction.py               # apply in-place
    python dataset_correction.py --backup      # apply + keep .bak copies
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd

from app_config import cfg

DATASETS_FOLDER = cfg.datasets
DATA_EXTENSIONS = cfg.data_extensions
SKIP_PREFIXES = ("Lower Limit", "Upper Limit", "Unit")


def fix_column_name(col: str) -> str:
    """Apply renaming rules to a single column name."""
    name = col

    # Rule 2: IR_ prefix columns
    if name.startswith("IR_"):
        name = name[3:]  # remove 'IR_' prefix
        name = name.replace("_VIS_", "_IR_")  # _VIS_ → _IR_

    # Rule 1: 30cm → 25cm
    name = name.replace("30cm", "25cm")
    name = name.replace("30sfr", "25sfr")
    name = name.replace("30modify", "25modify")

    return name


def process_file(
    filepath: Path, *, dry_run: bool = False, backup: bool = False
) -> dict:
    """Process a single file. Returns stats dict."""
    ext = filepath.suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(filepath, dtype=str)
    else:
        df = pd.read_excel(filepath, dtype=str)

    old_cols = list(df.columns)
    new_cols = [fix_column_name(c) for c in old_cols]

    changed = [(o, n) for o, n in zip(old_cols, new_cols) if o != n]

    if not changed:
        return {"file": filepath.name, "changed": 0, "status": "no changes"}

    if dry_run:
        return {
            "file": filepath.name,
            "changed": len(changed),
            "status": "dry-run",
            "renames": changed,
        }

    # Backup
    if backup:
        bak = filepath.with_suffix(filepath.suffix + ".bak")
        shutil.copy2(filepath, bak)

    # Apply rename
    df.columns = new_cols

    if ext == ".csv":
        df.to_csv(filepath, index=False)
    else:
        df.to_excel(filepath, index=False)

    return {
        "file": filepath.name,
        "changed": len(changed),
        "status": "applied",
        "renames": changed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix column names in datasets/ files")
    parser.add_argument(
        "--src", type=str, default=str(DATASETS_FOLDER), help="Datasets folder"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview renames without modifying files"
    )
    parser.add_argument(
        "--backup", action="store_true", help="Keep .bak copies of original files"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show every column rename"
    )
    args = parser.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"Error: folder not found: {src}")
        return

    files = sorted(
        f for f in src.iterdir() if f.is_file() and f.suffix.lower() in DATA_EXTENSIONS
    )

    if not files:
        print("No data files found.")
        return

    print(f"Scanning: {src}")
    print(f"Files:    {len(files)}")
    print(f"{'[DRY RUN]' if args.dry_run else ''}\n")

    total_files, total_changed = 0, 0

    for filepath in files:
        result = process_file(filepath, dry_run=args.dry_run, backup=args.backup)

        if result["changed"] == 0:
            continue

        total_files += 1
        total_changed += result["changed"]

        status = "[DRY]" if args.dry_run else "  ✓ "
        print(f"{status} {result['file']}  — {result['changed']} columns renamed")

        if args.verbose and "renames" in result:
            for old, new in result["renames"]:
                print(f"        {old}  →  {new}")

    print(f"\nDone: {total_files} files, {total_changed} total column renames")


if __name__ == "__main__":
    main()
