"""
run_pipeline.py — Chain: gsync → move_to_data_folder → move_to_datasets → move_audit_to_datasets → db_update → db_audit_update → copy_images → sfr_report → db_viewer → publish_reports (convert HTML→PDF + upload to GDrive)

Usage:
    python run_pipeline.py --config pre_EVT2          # full pipeline
    python run_pipeline.py --config pre_EVT2 --dry-run # preview all steps
    python run_pipeline.py --skip-sync                  # skip gdrive, run local steps only
    python run_pipeline.py --skip-publish               # skip uploading reports to GDrive
    python run_pipeline.py --from-cache                 # restore DB from GDrive cache, skip gsync
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from app_config import cfg
from gdrive_ops import GDrive

PROJECT_DIR = Path(__file__).parent

STEPS = [
    {"name": "gsync", "script": "gsync.py"},
    {"name": "move_to_data_folder", "script": "move_to_data_folder.py"},
    {"name": "move_to_datasets", "script": "move_to_datasets.py"},
    {"name": "move_audit_to_datasets", "script": "move_audit_to_datasets.py"},
    {"name": "db_update", "script": "db_update.py"},
    {"name": "db_audit_update", "script": "db_audit_update.py"},
    {"name": "copy_images", "script": "copy_images.py"},
    {"name": "sfr_report", "script": "sfr_report.py"},
    {"name": "db_viewer", "script": "db_viewer.py"},
]


def run_step(name: str, cmd: list[str]) -> bool:
    print(f"\n{'='*60}")
    print(f"  Step: {name}")
    print(f"  cmd:  {' '.join(cmd)}")
    print(f"{'='*60}\n")

    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"\n✗ {name} failed (exit {result.returncode})")
        return False

    print(f"\n✓ {name} done")
    return True


_CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def _find_chrome() -> str:
    """Return the path to a Chrome/Chromium binary, or raise if none found."""
    for candidate in _CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    for name in ("google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    raise FileNotFoundError(
        "Chrome/Chromium not found. Install Google Chrome or set it on your PATH."
    )


def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    """Convert an HTML file to PDF using headless Chrome.

    To avoid a slow/stalling CDN fetch for plotly-latest.min.js during
    headless rendering, this function inlines the Plotly JS from the
    locally-installed Python package before handing the file to Chrome.
    """
    import plotly

    chrome = _find_chrome()
    html = html_path.read_text(encoding="utf-8")

    # Replace CDN <script> with inline Plotly JS from the installed package
    plotly_js = plotly.offline.get_plotlyjs()
    cdn_tag = '<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>'
    html = html.replace(cdn_tag, f"<script>{plotly_js}</script>")

    # Write a self-contained temp HTML (no network needed)
    tmp_dir = tempfile.mkdtemp()
    tmp_html = Path(tmp_dir) / "report_for_pdf.html"
    tmp_html.write_text(html, encoding="utf-8")

    try:
        cmd = [
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=30000",
            f"--print-to-pdf={pdf_path}",
            f"file://{tmp_html.resolve()}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(
                f"html_to_pdf failed (exit {result.returncode}): {result.stderr.strip()}"
            )
    finally:
        tmp_html.unlink(missing_ok=True)
        Path(tmp_dir).rmdir()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full sync pipeline")
    parser.add_argument("--profile", type=str, default=None, help="gsync profile name")
    parser.add_argument(
        "--gdrive", type=str, default=None, help="GDrive path/URL/ID (if no profile)"
    )
    parser.add_argument(
        "--local", type=str, default=None, help="Local sync folder (if no profile)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Dry-run all steps")
    parser.add_argument(
        "--skip-sync", action="store_true", help="Skip gsync, run local steps only"
    )
    parser.add_argument(
        "--skip-publish", action="store_true", help="Skip uploading reports to GDrive"
    )
    parser.add_argument(
        "--check-only", action="store_true", help="Only check gsync, no download"
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="Restore DB + datasets from GDrive cache instead of full gsync. "
             "Automatically saves back to cache after pipeline completes.",
    )
    args = parser.parse_args()

    # --from-cache implies --skip-sync
    if args.from_cache:
        args.skip_sync = True

    # Propagate active config to child processes via env var
    os.environ["APP_CONFIG"] = cfg.config_name
    cfg.ensure_folders()
    print(f"Config: {cfg.config_name}")
    print(f"Output: {cfg.output_folder}")
    if cfg.has_cache:
        print(f"Cache:  {cfg.cache_remote} (folder {cfg.cache_folder_id})")
    print()

    python = sys.executable

    # ------------------------------------------------------------------
    # Step 0 (optional): Restore from GDrive cache
    # ------------------------------------------------------------------
    cache = None
    if args.from_cache:
        if not cfg.has_cache:
            print("Error: --from-cache requires a 'cache' section in config JSON.")
            sys.exit(1)

        from cache_ops import CacheOps
        cache = CacheOps(cfg)
        restored = cache.restore()
        if not restored:
            print("Error: cache restore failed — cache may be empty.")
            print("Run the full pipeline first (without --from-cache) to populate the cache.")
            sys.exit(1)

    # ------------------------------------------------------------------
    # Step 1: gsync
    # ------------------------------------------------------------------
    if not args.skip_sync:
        gsync_cmd = [python, str(PROJECT_DIR / "gsync.py")]
        if args.profile:
            gsync_cmd += ["--profile", args.profile]
        else:
            gdrive = args.gdrive or cfg.gdrive_url
            local = args.local or str(cfg.sync_folder)
            gsync_cmd += ["--gdrive", gdrive, "--local", local]
        if args.dry_run:
            gsync_cmd.append("--dry-run")
        if args.check_only:
            gsync_cmd.append("--check")

        if not run_step("gsync", gsync_cmd):
            sys.exit(1)

        if args.check_only:
            print("\n--check-only: stopping after gsync check.")
            return

    # Step 2: move_to_data_folder
    if not args.from_cache:
        move_data_cmd = [python, str(PROJECT_DIR / "move_to_data_folder.py")]
        if args.dry_run:
            move_data_cmd.append("--dry-run")

        if not run_step("move_to_data_folder", move_data_cmd):
            sys.exit(1)
    else:
        print("\n[CACHE] Skipping move_to_data_folder (restored from cache)")

    # Step 3: move_to_datasets
    if not args.from_cache:
        move_ds_cmd = [python, str(PROJECT_DIR / "move_to_datasets.py")]
        if args.dry_run:
            move_ds_cmd.append("--dry-run")

        if not run_step("move_to_datasets", move_ds_cmd):
            sys.exit(1)
    else:
        print("[CACHE] Skipping move_to_datasets (restored from cache)")

    # Step 4: move_audit_to_datasets
    if not args.from_cache:
        move_audit_cmd = [python, str(PROJECT_DIR / "move_audit_to_datasets.py")]
        if args.dry_run:
            move_audit_cmd.append("--dry-run")

        if not run_step("move_audit_to_datasets", move_audit_cmd):
            sys.exit(1)
    else:
        print("[CACHE] Skipping move_audit_to_datasets (restored from cache)")

    # Step 5: db_update
    db_cmd = [python, str(PROJECT_DIR / "db_update.py")]
    if args.dry_run:
        db_cmd.append("--dry-run")

    if not run_step("db_update", db_cmd):
        sys.exit(1)

    # Step 6: db_audit_update
    db_audit_cmd = [python, str(PROJECT_DIR / "db_audit_update.py")]
    if args.dry_run:
        db_audit_cmd.append("--dry-run")

    if not run_step("db_audit_update", db_audit_cmd):
        sys.exit(1)

    # Step 7: copy_images
    if not args.from_cache:
        copy_img_cmd = [python, str(PROJECT_DIR / "copy_images.py")]
        if args.dry_run:
            copy_img_cmd.append("--dry-run")

        if not run_step("copy_images", copy_img_cmd):
            sys.exit(1)
    else:
        print("[CACHE] Skipping copy_images (no local data_folder)")

    # Step 8: sfr_report (skip on dry-run — needs real data in db)
    if not args.dry_run:
        report_cmd = [python, str(PROJECT_DIR / "sfr_report.py")]
        if not run_step("sfr_report", report_cmd):
            sys.exit(1)
    else:
        print("\n[DRY RUN] Skipping sfr_report (needs data in db)")

    # Step 9: db_viewer (skip on dry-run — needs real data in db)
    if not args.dry_run:
        viewer_cmd = [python, str(PROJECT_DIR / "db_viewer.py")]
        if not run_step("db_viewer", viewer_cmd):
            sys.exit(1)
    else:
        print("[DRY RUN] Skipping db_viewer (needs data in db)")

    # ------------------------------------------------------------------
    # Step 10: publish — convert HTML reports to PDF and upload to GDrive
    # ------------------------------------------------------------------
    if not args.dry_run and not args.skip_publish:
        print(f"\n{'='*60}")
        print("  Step: publish_reports (HTML → PDF + upload)")
        print(f"{'='*60}\n")

        gd = GDrive(remote=cfg.gdrive_remote)
        try:
            html_path = cfg.report_file
            pdf_path = cfg.report_pdf
            if html_path.exists():
                print(f"  Converting {html_path.name} → {pdf_path.name} …")
                html_to_pdf(html_path, pdf_path)
                gd.upload_to_url(str(pdf_path), cfg.gdrive_url, progress=True)
                print(f"  ✓ Uploaded {pdf_path.name}")
            else:
                print(f"  ⚠ Skipping {html_path.name} — file not found")

            print("\n✓ publish_reports done")
        except Exception as e:
            print(f"\n✗ publish_reports failed: {e}")
            sys.exit(1)
    elif args.skip_publish:
        print("\n[SKIP] publish_reports (--skip-publish)")
    else:
        print("\n[DRY RUN] Skipping publish_reports")

    # ------------------------------------------------------------------
    # Step 11 (optional): Save back to GDrive cache
    # ------------------------------------------------------------------
    if args.from_cache and cache and not args.dry_run:
        cache.save()
    elif cfg.has_cache and not args.from_cache and not args.dry_run:
        # Even on full pipeline, save to cache for next --from-cache run
        from cache_ops import CacheOps
        cache = CacheOps(cfg)
        cache.save()

    print(f"\n{'='*60}")
    print("  ✓ Pipeline complete")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
