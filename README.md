# dbDashboard

SFR (Spatial Frequency Response) Dashboard for optical sensor testing data analysis.

## Overview

This pipeline automatically:
1. Syncs test data from Google Drive
2. Processes and imports CSV datasets into SQLite
3. Generates interactive HTML reports (SFR analysis & database viewer)
4. Publishes reports to Google Drive and GitHub Pages

## Quick Start

```bash
# Run the full pipeline
python run_pipeline.py --config pre_EVT2

# Skip Google Drive sync (use local data)
python run_pipeline.py --config pre_EVT2 --skip-sync

# Dry run (preview without making changes)
python run_pipeline.py --config pre_EVT2 --dry-run
```

## Requirements

- Python 3.10+
- rclone (for Google Drive sync)
- gh CLI (for GitHub Pages publishing)

### Python Dependencies
```bash
pip install pandas plotly openpyxl
```

## Configuration

Config files are in `config/` directory (e.g., `pre_EVT2.json`):

```json
{
  "gdrive": {
    "remote": "manus_google_drive",
    "folder_url": "https://drive.google.com/drive/folders/...",
    "images_folder_id": "..."
  },
  "output_folder": "./output_pre_EVT2",
  "slot_map": {
    "1": "DTC_R",
    "2": "DTC_L",
    "3": "STC"
  }
}
```

## Pipeline Steps

| Step | Script | Description |
|------|--------|-------------|
| 1 | `gsync.py` | Sync files from Google Drive |
| 2 | `move_to_data_folder.py` | Extract and organize downloaded files |
| 3 | `move_to_datasets.py` | Move ONLINE datasets |
| 4 | `move_audit_to_datasets.py` | Move AUDIT datasets |
| 5 | `db_update.py` | Import ONLINE data to SQLite |
| 6 | `db_audit_update.py` | Import AUDIT data to SQLite |
| 7 | `copy_images.py` | Copy ROI images |
| 8 | `sfr_report.py` | Generate SFR analysis report |
| 9 | `db_viewer.py` | Generate database viewer |
| 10 | Publish | Upload to GDrive & GitHub Pages |

## Scheduled Daily Updates

To set up automatic daily updates:

1. Run PowerShell as Administrator
2. Execute: `.\setup_scheduled_task.ps1`

This creates a Windows Scheduled Task that runs at 6:00 AM daily.

## GitHub Pages

Reports are published to: https://samlai1030.github.io/dbDashboard/

- [SFR Report](https://samlai1030.github.io/dbDashboard/sfr_report.html)
- [DB Viewer](https://samlai1030.github.io/dbDashboard/db_viewer.html)

## Recent Changes (2026-04-20)

### Bug Fixes
- **Fixed schema migration for CSV files with varying columns**: The `_add_missing_columns` function in `db_update.py` and `db_audit_update.py` now properly handles CSVs with different column sets by:
  - Checking if table exists before adding columns
  - Adding missing columns via ALTER TABLE
  - Only inserting columns that exist in both DataFrame and table

- **Fixed Unicode encoding issues on Windows**:
  - Added `encoding="utf-8"` to file write operations in `db_viewer.py`
  - Added `encoding="utf-8", errors="replace"` to subprocess calls in `gdrive_ops.py`
  - Handles `gws` CLI not being available gracefully

### New Features
- **Automated daily pipeline**: Added `run_daily_pipeline.bat` and `setup_scheduled_task.ps1` for Windows Task Scheduler integration

### Infrastructure
- Configured rclone for Google Drive sync
- Set up GitHub CLI for Pages publishing
- Added logs directory for pipeline execution logs

## File Structure

```
dbDashboard/
├── config/                  # Configuration files
│   └── pre_EVT2.json
├── logs/                    # Pipeline execution logs
├── output_pre_EVT2/         # Output directory
│   ├── data.db              # SQLite database
│   ├── sfr_report.html      # SFR analysis report
│   ├── db_viewer.html       # Database viewer
│   ├── datasets/            # Processed ONLINE CSVs
│   ├── audit_datasets/      # Processed AUDIT CSVs
│   └── sync_folder/         # Downloaded files from GDrive
├── run_pipeline.py          # Main pipeline orchestrator
├── run_daily_pipeline.bat   # Daily scheduled task script
└── setup_scheduled_task.ps1 # Task scheduler setup
```

## License

Internal use only.
