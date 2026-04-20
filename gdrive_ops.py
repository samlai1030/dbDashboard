"""
gdrive_ops.py — Single-file module with all Google Drive operations via rclone.

Usage:
    from gdrive_ops import GDrive

    gd = GDrive()                          # uses default remote
    gd = GDrive(remote="samlai@meta.com")  # explicit remote

    # Status & info
    gd.status()
    gd.storage_info()

    # List & search
    gd.ls("Documents")
    gd.ls("Documents", recursive=True)
    gd.search("Documents", pattern="*.pdf")
    gd.search("/", min_size="10M", files_only=True)

    # Download
    gd.download("Documents/report.pdf", "./downloads")
    gd.download("Documents/", "./local_docs")
    gd.download("Photos/", "./pics", include=["*.jpg", "*.png"])

    # Upload
    gd.upload("./report.pdf", "Documents/")
    gd.upload("./project_folder", "Backups/project", exclude=["*.tmp", ".git/**"])

    # Sync (GDrive → Local, one-way pull)
    gd.sync("Documents/", "./local_docs")
    gd.sync("Documents/", "./local_docs", dry_run=True)

    # Watch for changes
    gd.watch("Documents", interval=15)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FileEntry:
    """Represents a file or directory on Google Drive."""

    path: str
    name: str
    size: int
    is_dir: bool
    mod_time: str
    mime_type: str = ""

    @property
    def display(self) -> str:
        kind = "DIR " if self.is_dir else "FILE"
        size_str = _human_size(self.size) if not self.is_dir else "-"
        return f"{kind}  {size_str:>10s}  {self.mod_time}  {self.path}"


@dataclass
class StorageInfo:
    """Google Drive storage quota information."""

    total: Optional[int]
    used: Optional[int]
    free: Optional[int]
    trashed: Optional[int]

    @property
    def summary(self) -> str:
        parts = []
        if self.used is not None:
            parts.append(f"Used: {_human_size(self.used)}")
        if self.total is not None:
            parts.append(f"Total: {_human_size(self.total)}")
        if self.free is not None:
            parts.append(f"Free: {_human_size(self.free)}")
        if self.trashed is not None:
            parts.append(f"Trashed: {_human_size(self.trashed)}")
        return ", ".join(parts) if parts else "No quota information available."


@dataclass
class ChangeEvent:
    """A detected change from the watch function."""

    kind: str  # "added", "modified", "deleted"
    entry: FileEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _human_size(nbytes: float) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


def _run_rclone(
    args: List[str],
    *,
    stream: bool = False,
    dry_run: bool = False,
    progress: bool = False,
    extra_flags: Optional[List[str]] = None,
) -> subprocess.CompletedProcess:
    """Execute an rclone command."""
    cmd = ["rclone"] + args
    if dry_run:
        cmd.append("--dry-run")
    if progress:
        cmd.append("--progress")
    if extra_flags:
        cmd.extend(extra_flags)

    if stream:
        return subprocess.run(cmd, check=True)

    return subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", errors="replace")


_GDRIVE_URL_RE = re.compile(
    r"https?://drive\.google\.com/drive(?:/u/\d+)?/folders/([A-Za-z0-9_-]+)"
)


def _extract_folder_id(url_or_id: str) -> str | None:
    """Extract a Google Drive folder ID from a URL or bare ID string."""
    m = _GDRIVE_URL_RE.search(url_or_id)
    if m:
        return m.group(1)
    if len(url_or_id) >= 20 and "/" not in url_or_id and "." not in url_or_id:
        return url_or_id
    return None


def _build_filter_flags(
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
) -> List[str]:
    """Build rclone --include/--exclude flags from pattern lists."""
    flags: List[str] = []
    for pat in include or []:
        flags.extend(["--include", pat])
    for pat in exclude or []:
        flags.extend(["--exclude", pat])
    return flags


def _parse_lsjson(stdout: str) -> List[FileEntry]:
    """Parse rclone lsjson output into FileEntry objects."""
    items = json.loads(stdout)
    return [
        FileEntry(
            path=item.get("Path", ""),
            name=item.get("Name", ""),
            size=item.get("Size", 0),
            is_dir=item.get("IsDir", False),
            mod_time=item.get("ModTime", ""),
            mime_type=item.get("MimeType", ""),
        )
        for item in items
    ]


# ---------------------------------------------------------------------------
# GDrive class — all operations in one place
# ---------------------------------------------------------------------------


class GDrive:
    """Google Drive operations via rclone.

    Parameters
    ----------
    remote : str
        rclone remote name (default: ``"samlai@meta.com"``).
    """

    DEFAULT_REMOTE = "samlai@meta.com"

    def __init__(self, remote: str = DEFAULT_REMOTE) -> None:
        self.remote = remote

    def _remote_path(self, path: str) -> str:
        return f"{self.remote}:{path}"

    # --- Status & Config ------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Check rclone installation, validate the remote, and print storage info.

        Returns a dict with keys: rclone_path, remote, storage.
        """
        rclone_path = shutil.which("rclone")
        if rclone_path is None:
            raise FileNotFoundError(
                "rclone is not installed or not on PATH. "
                "Install from https://rclone.org/install/"
            )
        print(f"rclone found: {rclone_path}")

        # Validate remote type
        result = _run_rclone(["config", "dump"])
        config = json.loads(result.stdout)
        entry = config.get(self.remote)
        if entry is None:
            raise ValueError(f"Remote '{self.remote}' not found in rclone config.")
        if entry.get("type") != "drive":
            raise ValueError(
                f"Remote '{self.remote}' is type '{entry.get('type')}', expected 'drive'."
            )
        print(f"Remote '{self.remote}' is a valid Google Drive remote.")

        info = self.storage_info()
        print(info.summary)

        return {"rclone_path": rclone_path, "remote": self.remote, "storage": info}

    def storage_info(self) -> StorageInfo:
        """Get storage quota/usage via ``rclone about``."""
        result = _run_rclone(["about", f"{self.remote}:", "--json"])
        data = json.loads(result.stdout)
        return StorageInfo(
            total=data.get("total"),
            used=data.get("used"),
            free=data.get("free"),
            trashed=data.get("trashed"),
        )

    def list_remotes(self) -> List[str]:
        """Return all configured rclone remote names."""
        result = _run_rclone(["listremotes"])
        return [r.rstrip(":") for r in result.stdout.strip().splitlines() if r.strip()]

    # --- List & Search --------------------------------------------------

    def ls(
        self,
        remote_path: str = "",
        *,
        recursive: bool = False,
        print_results: bool = True,
    ) -> List[FileEntry]:
        """List files/folders at *remote_path*.

        Parameters
        ----------
        remote_path : str
            Path on Google Drive (default: root).
        recursive : bool
            List recursively.
        print_results : bool
            Print each entry to stdout.
        """
        args = ["lsjson", self._remote_path(remote_path)]
        if recursive:
            args.append("--recursive")

        result = _run_rclone(args)
        entries = _parse_lsjson(result.stdout)

        if print_results:
            for e in entries:
                print(e.display)

        return entries

    def search(
        self,
        remote_path: str = "",
        *,
        pattern: Optional[str] = None,
        min_size: Optional[str] = None,
        max_size: Optional[str] = None,
        files_only: bool = False,
        dirs_only: bool = False,
        print_results: bool = True,
    ) -> List[FileEntry]:
        """Recursively search for files matching filters.

        Parameters
        ----------
        pattern : str | None
            Glob pattern for file name (e.g. ``"*.pdf"``).
        min_size / max_size : str | None
            Size filters (e.g. ``"1M"``, ``"500K"``).
        files_only / dirs_only : bool
            Restrict result type.
        """
        args = ["lsjson", self._remote_path(remote_path), "--recursive"]
        if pattern:
            args.extend(["--include", pattern])
        if min_size:
            args.extend(["--min-size", min_size])
        if max_size:
            args.extend(["--max-size", max_size])
        if files_only:
            args.append("--files-only")
        if dirs_only:
            args.append("--dirs-only")

        result = _run_rclone(args)
        entries = _parse_lsjson(result.stdout)

        if print_results:
            if not entries:
                print("No matches found.")
            else:
                for e in entries:
                    print(e.display)

        return entries

    # --- Download -------------------------------------------------------

    def download(
        self,
        remote_path: str,
        local_path: str,
        *,
        dry_run: bool = False,
        progress: bool = True,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
    ) -> None:
        """Download a file or folder from Google Drive.

        Parameters
        ----------
        remote_path : str
            Path on Google Drive (e.g. ``"Documents/report.pdf"``).
        local_path : str
            Local destination directory.
        include / exclude : list[str] | None
            Glob filter patterns (e.g. ``["*.pdf", "*.docx"]``).
        """
        src = self._remote_path(remote_path)
        print(f"Downloading {src} → {local_path}")
        _run_rclone(
            ["copy", src, local_path],
            stream=progress,
            dry_run=dry_run,
            progress=progress,
            extra_flags=_build_filter_flags(include, exclude) or None,
        )
        print("Download complete.")

    # --- Upload ---------------------------------------------------------

    def upload(
        self,
        local_path: str,
        remote_path: str,
        *,
        dry_run: bool = False,
        progress: bool = True,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        folder_id: Optional[str] = None,
    ) -> None:
        """Upload a file or folder to Google Drive.

        Parameters
        ----------
        local_path : str
            Local file or folder path.
        remote_path : str
            Destination folder on Google Drive (ignored when *folder_id* is set).
        folder_id : str | None
            Google Drive folder ID.  When provided the file is uploaded
            directly into that folder using ``--drive-root-folder-id``.
        """
        extra = _build_filter_flags(include, exclude)

        if folder_id:
            dst = f"{self.remote}:"
            extra.extend(["--drive-root-folder-id", folder_id])
            label = f"{self.remote}: (folder ID {folder_id})"
        else:
            dst = self._remote_path(remote_path)
            label = dst

        print(f"Uploading {local_path} → {label}")
        _run_rclone(
            ["copy", local_path, dst],
            stream=progress,
            dry_run=dry_run,
            progress=progress,
            extra_flags=extra or None,
        )
        print("Upload complete.")

    def upload_to_url(
        self,
        local_path: str,
        folder_url: str,
        *,
        dry_run: bool = False,
        progress: bool = True,
    ) -> None:
        """Upload a file/folder to a Google Drive folder given its URL.

        Parameters
        ----------
        local_path : str
            Local file or folder path.
        folder_url : str
            Full Google Drive folder URL
            (e.g. ``https://drive.google.com/drive/folders/1fYq...``).
        """
        fid = _extract_folder_id(folder_url)
        if fid is None:
            raise ValueError(f"Cannot extract folder ID from: {folder_url}")
        self.upload(local_path, "", folder_id=fid, dry_run=dry_run, progress=progress)

    # --- Sync -----------------------------------------------------------

    def sync(
        self,
        remote_path: str,
        local_path: str,
        *,
        dry_run: bool = False,
        progress: bool = True,
        exclude: Optional[List[str]] = None,
        delete_excluded: bool = False,
    ) -> None:
        """One-way sync from Google Drive → Local (pull).

        ⚠ Files present locally but not on the remote will be **deleted**.

        Parameters
        ----------
        remote_path : str
            Source path on Google Drive.
        local_path : str
            Local destination directory.
        delete_excluded : bool
            Also delete locally excluded files.
        """
        src = self._remote_path(remote_path)
        print(f"Syncing {src} → {local_path}")

        extra = _build_filter_flags(exclude=exclude)
        if delete_excluded:
            extra.append("--delete-excluded")

        _run_rclone(
            ["sync", src, local_path],
            stream=progress,
            dry_run=dry_run,
            progress=progress,
            extra_flags=extra or None,
        )
        print("Sync complete.")

    # --- Watch ----------------------------------------------------------

    def watch(
        self,
        remote_path: str = "",
        *,
        interval: int = 30,
        on_change: Optional[Callable[[List[ChangeEvent]], None]] = None,
    ) -> None:
        """Poll-based watcher that detects new/modified/deleted files.

        Press Ctrl-C to stop.

        Parameters
        ----------
        interval : int
            Poll interval in seconds (default: 30).
        on_change : callable | None
            Callback receiving a list of ChangeEvent. If None, changes are printed.
        """
        print(
            f"Watching {self.remote}:{remote_path} every {interval}s  (Ctrl-C to stop)"
        )

        def _snapshot() -> Dict[str, FileEntry]:
            entries = self.ls(remote_path, recursive=True, print_results=False)
            return {e.path: e for e in entries}

        prev = _snapshot()
        print(f"Initial snapshot: {len(prev)} items")

        try:
            while True:
                time.sleep(interval)
                curr = _snapshot()
                changes: List[ChangeEvent] = []

                for path, entry in curr.items():
                    if path not in prev:
                        changes.append(ChangeEvent(kind="added", entry=entry))
                    elif (
                        entry.mod_time != prev[path].mod_time
                        or entry.size != prev[path].size
                    ):
                        changes.append(ChangeEvent(kind="modified", entry=entry))

                for path in prev:
                    if path not in curr:
                        changes.append(ChangeEvent(kind="deleted", entry=prev[path]))

                if changes:
                    if on_change:
                        on_change(changes)
                    else:
                        for c in changes:
                            print(f"[{c.kind.upper()}] {c.entry.path}")

                prev = curr
        except KeyboardInterrupt:
            print("Watch stopped.")


# ---------------------------------------------------------------------------
# Quick test when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    gd = GDrive()
    gd.status()
    print()
    print("=== Root files ===")
    gd.ls("/")
