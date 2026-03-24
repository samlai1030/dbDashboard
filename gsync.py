"""
gsync.py — Safe pull-copy from Google Drive to a local folder.

• Never deletes local files (uses rclone copy, not sync).
• Builds a checklist comparing GDrive vs local so you see what's missing.
• Supports saved config profiles for one-command repeat syncs.

Usage:
    # Interactive — prompts for paths
    python gsync.py

    # Explicit paths
    python gsync.py --gdrive "Documents/reports" --local "./sync_folder"

    # Full Google Drive URL
    python gsync.py --gdrive "https://drive.google.com/drive/folders/1o9l..." --local "./sync_folder"

    # Check only — show what's missing without downloading
    python gsync.py --check

    # Save current paths as a named profile
    python gsync.py --gdrive "..." --local "..." --save myproject

    # Quick-sync a saved profile (no need to re-type paths)
    python gsync.py --profile myproject

    # List saved profiles
    python gsync.py --list-profiles
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from gdrive_ops import _run_rclone, GDrive
from app_config import cfg as app_cfg

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".gsync"
CONFIG_FILE = CONFIG_DIR / "profiles.json"
CHECKLIST_DIR = CONFIG_DIR / "checklists"

_GDRIVE_URL_RE = re.compile(
    r"https?://drive\.google\.com/drive(?:/u/\d+)?/folders/([A-Za-z0-9_-]+)"
)
_GDRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,}$")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RemoteFile:
    path: str
    size: int
    mod_time: str


@dataclass
class CheckResult:
    missing: List[RemoteFile] = field(default_factory=list)
    size_mismatch: List[tuple] = field(default_factory=list)
    ok: List[RemoteFile] = field(default_factory=list)

    @property
    def all_synced(self) -> bool:
        return not self.missing and not self.size_mismatch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_gdrive_input(raw: str) -> tuple[str | None, str]:
    """Return (folder_id | None, rclone_path)."""
    m = _GDRIVE_URL_RE.search(raw)
    if m:
        return m.group(1), ""
    if _GDRIVE_ID_RE.match(raw) and "/" not in raw and "." not in raw:
        return raw, ""
    return None, raw


def _rclone_remote_src(
    remote: str, folder_id: str | None, gdrive_path: str
) -> tuple[str, list[str]]:
    """Return (rclone_source_string, extra_flags)."""
    if folder_id:
        return f"{remote}:", ["--drive-root-folder-id", folder_id]
    return f"{remote}:{gdrive_path}", []


def _list_remote_files(
    remote: str, folder_id: str | None, gdrive_path: str
) -> List[RemoteFile]:
    """Get a flat list of all files on the remote side."""
    src, extra = _rclone_remote_src(remote, folder_id, gdrive_path)
    args = ["lsjson", src, "--recursive", "--files-only"]
    result = _run_rclone(args, extra_flags=extra or None)
    items = json.loads(result.stdout)
    return [
        RemoteFile(
            path=item.get("Path", ""),
            size=item.get("Size", 0),
            mod_time=item.get("ModTime", ""),
        )
        for item in items
    ]


def _scan_local_files(local_path: str) -> Dict[str, int]:
    """Return {relative_path: file_size} for every file under local_path."""
    local = {}
    root = Path(local_path)
    if not root.exists():
        return local
    for f in root.rglob("*"):
        if f.is_file():
            rel = str(f.relative_to(root))
            local[rel] = f.stat().st_size
    return local


def _compare(
    remote_files: List[RemoteFile], local_files: Dict[str, int]
) -> CheckResult:
    """Compare remote file list against local files."""
    result = CheckResult()
    for rf in remote_files:
        if rf.path not in local_files:
            result.missing.append(rf)
        elif local_files[rf.path] != rf.size:
            result.size_mismatch.append((rf, local_files[rf.path]))
        else:
            result.ok.append(rf)
    return result


def _print_check(cr: CheckResult) -> None:
    total = len(cr.ok) + len(cr.missing) + len(cr.size_mismatch)
    print(f"\n{'='*60}")
    print(f"  Checklist: {len(cr.ok)}/{total} files synced")
    print(f"{'='*60}")

    if cr.missing:
        print(f"\n  ✗ Missing locally ({len(cr.missing)}):")
        for rf in cr.missing:
            print(f"    - {rf.path}  ({_human(rf.size)})")

    if cr.size_mismatch:
        print(f"\n  ⚠ Size mismatch ({len(cr.size_mismatch)}):")
        for rf, local_sz in cr.size_mismatch:
            print(
                f"    - {rf.path}  remote={_human(rf.size)}  local={_human(local_sz)}"
            )

    if cr.all_synced:
        print("\n  ✓ All remote files are present locally.")
    print()


def _human(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


# ---------------------------------------------------------------------------
# Checklist persistence
# ---------------------------------------------------------------------------


def _checklist_path(profile: str) -> Path:
    return CHECKLIST_DIR / f"{profile}.json"


def _save_checklist(profile: str, remote_files: List[RemoteFile]) -> None:
    CHECKLIST_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files": [
            {"path": f.path, "size": f.size, "mod_time": f.mod_time}
            for f in remote_files
        ],
    }
    _checklist_path(profile).write_text(json.dumps(data, indent=2))


def _load_checklist(profile: str) -> Optional[List[RemoteFile]]:
    p = _checklist_path(profile)
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    return [RemoteFile(**f) for f in data["files"]]


# ---------------------------------------------------------------------------
# Config / profiles
# ---------------------------------------------------------------------------


def _load_profiles() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def _save_profiles(profiles: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(profiles, indent=2))


def _save_profile(name: str, gdrive: str, local: str, remote: str) -> None:
    profiles = _load_profiles()
    profiles[name] = {"gdrive": gdrive, "local": local, "remote": remote}
    _save_profiles(profiles)
    print(f"Profile '{name}' saved. Quick-sync with:  python gsync.py --profile {name}")


def _list_profiles() -> None:
    profiles = _load_profiles()
    if not profiles:
        print("No saved profiles. Use --save <name> to create one.")
        return
    print(f"\n{'Name':<20s} {'GDrive':<50s} {'Local'}")
    print("-" * 90)
    for name, cfg in profiles.items():
        print(f"{name:<20s} {cfg['gdrive']:<50s} {cfg['local']}")
    print()


# ---------------------------------------------------------------------------
# Core actions
# ---------------------------------------------------------------------------


def do_check(
    remote: str,
    folder_id: str | None,
    gdrive_path: str,
    local_path: str,
    profile: str = "default",
    use_cache: bool = False,
) -> CheckResult:
    """Compare GDrive file list vs local files."""
    remote_files = None

    if use_cache:
        remote_files = _load_checklist(profile)
        if remote_files:
            print(f"Using cached checklist for '{profile}'.")

    if remote_files is None:
        print("Listing remote files …")
        remote_files = _list_remote_files(remote, folder_id, gdrive_path)
        _save_checklist(profile, remote_files)
        print(f"Remote: {len(remote_files)} files  (checklist cached)")

    local_files = _scan_local_files(local_path)
    print(f"Local:  {len(local_files)} files")

    cr = _compare(remote_files, local_files)
    _print_check(cr)
    return cr


def do_copy(
    remote: str,
    folder_id: str | None,
    gdrive_path: str,
    local_path: str,
    dry_run: bool = False,
    progress: bool = True,
) -> None:
    """Copy missing/updated files from GDrive → local (never deletes)."""
    src, extra = _rclone_remote_src(remote, folder_id, gdrive_path)
    label = f"folder ID {folder_id}" if folder_id else src

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Copying (no delete):")
    print(f"  Source : {label}")
    print(f"  Dest   : {os.path.abspath(local_path)}\n")

    _run_rclone(
        ["copy", src, local_path],
        stream=progress,
        dry_run=dry_run,
        progress=progress,
        extra_flags=extra or None,
    )
    print("Copy complete — no local files were deleted.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safe pull-copy from Google Drive → local (never deletes local files)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--gdrive", type=str, default=None, help="GDrive folder path / URL / folder ID"
    )
    parser.add_argument(
        "--local", type=str, default=None, help="Local folder to receive files"
    )
    parser.add_argument(
        "--remote", type=str, default=app_cfg.gdrive_remote, help="rclone remote name"
    )

    parser.add_argument(
        "--check", action="store_true", help="Only check — don't download anything"
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Use cached remote checklist (skip GDrive listing)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview copy without downloading"
    )
    parser.add_argument(
        "--no-progress", action="store_true", help="Hide transfer progress"
    )

    parser.add_argument(
        "--save", type=str, metavar="NAME", help="Save current paths as a named profile"
    )
    parser.add_argument(
        "--profile",
        type=str,
        metavar="NAME",
        help="Load a saved profile for quick sync",
    )
    parser.add_argument(
        "--list-profiles", action="store_true", help="Show all saved profiles"
    )

    args = parser.parse_args()

    if args.list_profiles:
        _list_profiles()
        return

    # Resolve inputs — from profile or from args/interactive
    if args.profile:
        profiles = _load_profiles()
        if args.profile not in profiles:
            sys.exit(
                f"Error: profile '{args.profile}' not found. Use --list-profiles to see available."
            )
        cfg = profiles[args.profile]
        gdrive_raw = args.gdrive or cfg["gdrive"]
        local_path = args.local or cfg["local"]
        remote_name = (
            args.remote
            if args.remote != GDrive.DEFAULT_REMOTE
            else cfg.get("remote", GDrive.DEFAULT_REMOTE)
        )
        profile_name = args.profile
    else:
        gdrive_raw = (
            args.gdrive or input("Google Drive path / URL / folder-ID: ").strip()
        )
        local_path = (
            args.local or input("Local folder path (e.g. ./sync_folder): ").strip()
        )
        remote_name = args.remote
        profile_name = "default"

    if not gdrive_raw:
        sys.exit("Error: Google Drive path cannot be empty.")
    if not local_path:
        sys.exit("Error: Local folder path cannot be empty.")

    folder_id, gdrive_path = _parse_gdrive_input(gdrive_raw)
    os.makedirs(local_path, exist_ok=True)

    # Save profile if requested
    if args.save:
        _save_profile(args.save, gdrive_raw, local_path, remote_name)
        profile_name = args.save

    # Check mode — compare and exit
    if args.check:
        do_check(
            remote_name,
            folder_id,
            gdrive_path,
            local_path,
            profile_name,
            args.use_cache,
        )
        return

    # Normal mode — check first, then copy missing files
    cr = do_check(
        remote_name, folder_id, gdrive_path, local_path, profile_name, args.use_cache
    )

    if cr.all_synced:
        print("Nothing to do — everything is already synced.")
        return

    do_copy(
        remote_name,
        folder_id,
        gdrive_path,
        local_path,
        dry_run=args.dry_run,
        progress=not args.no_progress,
    )

    # Re-check after copy
    if not args.dry_run:
        print("\n--- Post-copy verification ---")
        do_check(
            remote_name,
            folder_id,
            gdrive_path,
            local_path,
            profile_name,
            use_cache=True,
        )


if __name__ == "__main__":
    main()
