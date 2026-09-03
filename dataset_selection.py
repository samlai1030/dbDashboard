"""Shared dataset selection and collision-safe staging helpers."""

from __future__ import annotations

import csv
import hashlib
import shutil
from pathlib import Path, PurePosixPath


def normalize_path(path: str | Path) -> str:
    """Return a stable, slash-separated relative path string."""
    return str(PurePosixPath(str(path).replace("\\", "/")))


def is_excluded_path(path: str | Path, excluded_keywords: list[str]) -> bool:
    """Return whether a relative path contains a configured exclusion keyword."""
    normalized = normalize_path(path).casefold()
    return any(keyword.casefold() in normalized for keyword in excluded_keywords)


def matches_filename(filename: str, keywords: list[str]) -> bool:
    """Return whether a filename contains at least one configured keyword."""
    return bool(keywords) and any(keyword in filename for keyword in keywords)


def collision_safe_name(
    source_path: str | Path,
    basename: str,
    destinations: dict[str, str],
) -> tuple[str, bool]:
    """Choose a deterministic destination name without dropping duplicate basenames."""
    source = normalize_path(source_path)
    if basename not in destinations or destinations[basename] == source:
        destinations[basename] = source
        return basename, False

    suffix = hashlib.sha256(source.encode("utf-8")).hexdigest()[:10]
    path = Path(basename)
    candidate = f"{path.stem}__{suffix}{path.suffix}"
    destinations[candidate] = source
    return candidate, True


def stage_matching_files(
    src: Path,
    dst: Path,
    *,
    keywords: list[str],
    extensions: set[str],
    excluded_keywords: list[str],
    manifest_path: Path,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Copy selected files into a flat directory and write a source manifest."""
    candidates: list[tuple[Path, Path]] = []
    for filepath in sorted(src.rglob("*")):
        if not filepath.is_file() or filepath.suffix.lower() not in extensions:
            continue
        relative_path = filepath.relative_to(src)
        if is_excluded_path(relative_path, excluded_keywords):
            continue
        if matches_filename(filepath.name, keywords):
            candidates.append((filepath, relative_path))

    destinations: dict[str, str] = {}
    rows: list[dict[str, str]] = []
    selected_names: set[str] = set()
    copied = 0
    skipped = 0

    for filepath, relative_path in candidates:
        destination_name, renamed = collision_safe_name(
            relative_path, filepath.name, destinations
        )
        selected_names.add(destination_name)
        destination = dst / destination_name
        unchanged = (
            destination.exists()
            and destination.stat().st_size == filepath.stat().st_size
            and destination.read_bytes() == filepath.read_bytes()
        )

        rows.append(
            {
                "source_path": normalize_path(relative_path),
                "destination_file": destination_name,
                "collision_renamed": "yes" if renamed else "no",
                "size_bytes": str(filepath.stat().st_size),
            }
        )

        if unchanged:
            skipped += 1
            continue

        if dry_run:
            print(f"  [DRY] COPY  {relative_path}  ->  {dst.name}/{destination_name}")
        else:
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filepath, destination)
            print(f"  COPY  {relative_path}  ->  {dst.name}/{destination_name}")
        copied += 1

    if not dry_run:
        dst.mkdir(parents=True, exist_ok=True)
        for stale_file in dst.iterdir():
            if stale_file.is_file() and stale_file.name not in selected_names:
                stale_file.unlink()
                print(f"  REMOVE STALE  {dst.name}/{stale_file.name}")

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("w", newline="", encoding="utf-8") as manifest:
            writer = csv.DictWriter(
                manifest,
                fieldnames=[
                    "source_path",
                    "destination_file",
                    "collision_renamed",
                    "size_bytes",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

    return copied, skipped
