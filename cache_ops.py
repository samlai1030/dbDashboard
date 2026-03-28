"""
cache_ops.py — Persistent GDrive cache for DB, datasets, and reports.

Provides restore (download) and save (upload) operations so the pipeline
can skip the full gsync + move_to_data_folder steps on subsequent runs.

Cache folder structure on GDrive:
    <cache_folder_id>/
    ├── data.db              (SQLite database)
    ├── datasets.tar.gz      (compressed datasets + audit_datasets)
    ├── sfr_report.html      (latest report)
    └── db_viewer.html       (latest viewer)

Usage:
    from cache_ops import CacheOps
    cache = CacheOps(cfg)
    cache.restore()   # download DB + datasets from GDrive → local output
    cache.save()      # upload DB + reports from local output → GDrive
"""

from __future__ import annotations

import json
import os
import subprocess
import tarfile
from pathlib import Path
from typing import Optional


class CacheOps:
    """Download / upload persistent cache files between GDrive and local output."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.remote = cfg.cache_remote
        self.folder_id = cfg.cache_folder_id
        self._file_index: dict[str, str] | None = None  # name → fileId

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _list_cache_files(self) -> dict[str, str]:
        """List files in cache folder, return {name: fileId}."""
        if self._file_index is not None:
            return self._file_index

        result = subprocess.run(
            [
                "gws", "drive", "files", "list",
                "--params", json.dumps({
                    "q": f'"{self.folder_id}" in parents and trashed = false',
                    "fields": "files(id,name,mimeType,size)",
                    "pageSize": 100,
                }),
            ],
            capture_output=True, text=True,
        )
        data = json.loads(result.stdout)
        files = data.get("files", [])
        # If duplicates exist, keep the first (newest) one
        index: dict[str, str] = {}
        for f in files:
            name = f["name"]
            if name not in index:
                index[name] = f["id"]
        self._file_index = index
        return index

    def _download_file(self, file_id: str, dest_path: Path) -> None:
        """Download a file from GDrive by ID using gws."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "gws", "drive", "files", "get",
                "--params", json.dumps({
                    "fileId": file_id,
                    "alt": "media",
                }),
                "--output", str(dest_path),
            ],
            check=True,
        )

    def _upload_file(self, local_path: Path, name: str, mime: str) -> str:
        """Upload or update a file in the cache folder. Returns file ID."""
        index = self._list_cache_files()

        if name in index:
            # Update existing file
            file_id = index[name]
            result = subprocess.run(
                [
                    "gws", "drive", "files", "update",
                    "--params", json.dumps({
                        "fileId": file_id,
                        "uploadType": "multipart",
                    }),
                    "--upload", str(local_path),
                    "--upload-content-type", mime,
                ],
                capture_output=True, text=True,
                cwd=local_path.parent,  # gws requires upload path relative to cwd
            )
            data = json.loads(result.stdout)
            return data.get("id", file_id)
        else:
            # Create new file
            result = subprocess.run(
                [
                    "gws", "drive", "files", "create",
                    "--params", json.dumps({"uploadType": "multipart"}),
                    "--json", json.dumps({
                        "name": name,
                        "parents": [self.folder_id],
                    }),
                    "--upload", local_path.name,
                    "--upload-content-type", mime,
                ],
                capture_output=True, text=True,
                cwd=local_path.parent,
            )
            data = json.loads(result.stdout)
            fid = data.get("id", "")
            # Update index
            index[name] = fid
            return fid

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def restore(self) -> bool:
        """Download DB and datasets from GDrive cache to local output.

        Returns True if cache was found and restored, False if cache is empty.
        """
        print(f"\n{'='*60}")
        print("  Step: cache_restore (download DB + datasets from GDrive)")
        print(f"{'='*60}\n")

        index = self._list_cache_files()
        if not index:
            print("  ⚠ Cache is empty — nothing to restore")
            return False

        restored = False

        # 1. Restore data.db
        if "data.db" in index:
            dest = self.cfg.db_file
            print(f"  Downloading data.db → {dest}")
            self._download_file(index["data.db"], dest)
            print(f"  ✓ data.db restored ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
            restored = True
        else:
            print("  ⚠ data.db not found in cache")

        # 2. Restore datasets
        if "datasets.tar.gz" in index:
            tar_path = self.cfg.output_folder / "datasets.tar.gz"
            print(f"  Downloading datasets.tar.gz → {tar_path}")
            self._download_file(index["datasets.tar.gz"], tar_path)

            # Extract
            print("  Extracting datasets.tar.gz …")
            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(path=self.cfg.output_folder)
            tar_path.unlink()

            ds_count = len(list(self.cfg.datasets.glob("*"))) if self.cfg.datasets.exists() else 0
            ad_count = len(list(self.cfg.audit_datasets.glob("*"))) if self.cfg.audit_datasets.exists() else 0
            print(f"  ✓ datasets restored ({ds_count} files + {ad_count} audit files)")
            restored = True
        else:
            print("  ⚠ datasets.tar.gz not found in cache")

        if restored:
            print("\n✓ cache_restore done")
        return restored

    def save(self) -> None:
        """Upload DB, datasets, and reports from local output to GDrive cache."""
        print(f"\n{'='*60}")
        print("  Step: cache_save (upload DB + reports to GDrive)")
        print(f"{'='*60}\n")

        # 1. Upload data.db
        db = self.cfg.db_file
        if db.exists():
            print(f"  Uploading data.db ({db.stat().st_size / 1024 / 1024:.1f} MB) …")
            self._upload_file(db, "data.db", "application/x-sqlite3")
            print("  ✓ data.db saved")
        else:
            print("  ⚠ data.db not found — skipping")

        # 2. Upload datasets.tar.gz
        tar_path = self.cfg.output_folder / "datasets.tar.gz"
        has_datasets = (
            self.cfg.datasets.exists() and any(self.cfg.datasets.iterdir())
        )
        has_audit = (
            self.cfg.audit_datasets.exists() and any(self.cfg.audit_datasets.iterdir())
        )
        if has_datasets or has_audit:
            print("  Compressing datasets + audit_datasets …")
            with tarfile.open(tar_path, "w:gz") as tar:
                if has_datasets:
                    tar.add(self.cfg.datasets, arcname="datasets")
                if has_audit:
                    tar.add(self.cfg.audit_datasets, arcname="audit_datasets")
            print(f"  Uploading datasets.tar.gz ({tar_path.stat().st_size / 1024 / 1024:.1f} MB) …")
            self._upload_file(tar_path, "datasets.tar.gz", "application/gzip")
            tar_path.unlink()
            print("  ✓ datasets.tar.gz saved")

        # 3. Upload sfr_report.html
        report = self.cfg.report_file
        if report.exists():
            print(f"  Uploading sfr_report.html ({report.stat().st_size / 1024 / 1024:.1f} MB) …")
            self._upload_file(report, "sfr_report.html", "text/html")
            print("  ✓ sfr_report.html saved")

        # 4. Upload db_viewer.html
        viewer = self.cfg.viewer_file
        if viewer.exists():
            print(f"  Uploading db_viewer.html ({viewer.stat().st_size / 1024 / 1024:.1f} MB) …")
            self._upload_file(viewer, "db_viewer.html", "text/html")
            print("  ✓ db_viewer.html saved")

        print("\n✓ cache_save done")


if __name__ == "__main__":
    import sys
    from app_config import cfg

    if not cfg.has_cache:
        print(f"No cache configured for {cfg.config_name}")
        sys.exit(1)

    cache = CacheOps(cfg)

    action = sys.argv[1] if len(sys.argv) > 1 else "status"

    if action == "restore":
        cache.restore()
    elif action == "save":
        cache.save()
    elif action == "status":
        index = cache._list_cache_files()
        print(f"Cache folder: {cfg.cache_folder_id}")
        print(f"Remote: {cfg.cache_remote}")
        print(f"Files ({len(index)}):")
        for name, fid in index.items():
            print(f"  {name} → {fid}")
    else:
        print(f"Unknown action: {action}")
        print("Usage: python cache_ops.py [restore|save|status]")
