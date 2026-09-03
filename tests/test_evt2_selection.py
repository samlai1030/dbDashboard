from __future__ import annotations

import csv
import os
import zipfile
from pathlib import Path

os.environ.setdefault("APP_CONFIG", "LENS_EVT2")

from app_config import AppConfig
from dataset_selection import (
    collision_safe_name,
    is_excluded_path,
    matches_filename,
    stage_matching_files,
)
from db_update import _read_file, _source_part
from gsync import _is_selected_remote_path
from move_to_data_folder import scan_and_move


LENS_KEYWORD = "Summary_LanSi_Loma_CW_DTC-L_1_01_ONLINE"
GSEO_KEYWORD = "Summary_GSEO_Loma_CW_DTC_DTC-L_1_01_ONLINE"
EXCLUSIONS = ["DoE/", "Cavity Qual", "点检", "IQC", "retest", "重测"]


def test_production_filename_and_path_selection() -> None:
    assert matches_filename(
        "Summary_LanSi_Loma_CW_DTC-L_1_01_ONLINE_20260612.csv",
        [LENS_KEYWORD],
    )
    assert matches_filename(
        "Summary_GSEO_Loma_CW_DTC_DTC-L_1_01_ONLINE_20260612.csv",
        [GSEO_KEYWORD],
    )
    assert not is_excluded_path("20260628_LBU2/Summary.csv", EXCLUSIONS)


def test_non_production_paths_are_excluded_case_insensitively() -> None:
    excluded = [
        "DoE/20260703/Summary.csv",
        "Cavity Qual/20260622/Summary.csv",
        "build/20260617 点检/Summary.csv",
        "Lens_IQC_at_GTK.zip",
        "run/RETEST/Summary.csv",
        "20260609 -3 重测SFR.zip",
    ]
    for path in excluded:
        assert is_excluded_path(path, EXCLUSIONS), path


def test_collision_names_are_stable_and_unique() -> None:
    destinations: dict[str, str] = {}
    first, first_renamed = collision_safe_name(
        "batch-a/Summary.csv", "Summary.csv", destinations
    )
    second, second_renamed = collision_safe_name(
        "batch-b/Summary.csv", "Summary.csv", destinations
    )
    repeat, repeat_renamed = collision_safe_name(
        "batch-b/Summary.csv", "Summary.csv", destinations
    )

    assert first == "Summary.csv"
    assert not first_renamed
    assert second.startswith("Summary__") and second.endswith(".csv")
    assert second_renamed
    assert repeat == second
    assert repeat_renamed


def test_staging_preserves_duplicate_basenames_and_removes_stale_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "data"
    destination = tmp_path / "datasets"
    (source / "batch-a").mkdir(parents=True)
    (source / "batch-b").mkdir(parents=True)
    destination.mkdir()

    filename = f"{LENS_KEYWORD}_20260615.csv"
    (source / "batch-a" / filename).write_text("TSRID\nA\n", encoding="utf-8")
    (source / "batch-b" / filename).write_text("TSRID\nB\n", encoding="utf-8")
    (destination / "stale.csv").write_text("old", encoding="utf-8")
    manifest = tmp_path / "online_import_manifest.csv"

    copied, skipped = stage_matching_files(
        source,
        destination,
        keywords=[LENS_KEYWORD],
        extensions={".csv"},
        excluded_keywords=EXCLUSIONS,
        manifest_path=manifest,
    )

    assert copied == 2
    assert skipped == 0
    selected = sorted(path.name for path in destination.iterdir())
    assert len(selected) == 2
    assert filename in selected
    assert any(name.startswith(Path(filename).stem + "__") for name in selected)
    assert "stale.csv" not in selected

    with manifest.open(newline="", encoding="utf-8") as source_file:
        rows = list(csv.DictReader(source_file))
    assert len(rows) == 2
    assert {row["collision_renamed"] for row in rows} == {"no", "yes"}


def test_staging_excludes_matching_doe_summary(tmp_path: Path) -> None:
    source = tmp_path / "data"
    production = source / "20260628_LBU2"
    doe = source / "DoE" / "study"
    production.mkdir(parents=True)
    doe.mkdir(parents=True)
    filename = f"{GSEO_KEYWORD}_20260612.csv"
    (production / filename).write_text("TSRID\nPROD\n", encoding="utf-8")
    (doe / filename).write_text("TSRID\nDOE\n", encoding="utf-8")

    destination = tmp_path / "datasets"
    manifest = tmp_path / "manifest.csv"
    copied, _ = stage_matching_files(
        source,
        destination,
        keywords=[GSEO_KEYWORD],
        extensions={".csv"},
        excluded_keywords=EXCLUSIONS,
        manifest_path=manifest,
    )

    assert copied == 1
    assert (destination / filename).read_text(encoding="utf-8") == "TSRID\nPROD\n"
    assert "DoE" not in manifest.read_text(encoding="utf-8")


def test_nested_zip_is_extracted_but_excluded_archive_is_skipped(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sync"
    destination = tmp_path / "data"
    source.mkdir()

    nested_zip = tmp_path / "nested.zip"
    with zipfile.ZipFile(nested_zip, "w") as archive:
        archive.writestr(f"nested/{LENS_KEYWORD}_20260714.csv", "TSRID\n1\n")

    with zipfile.ZipFile(source / "production.zip", "w") as archive:
        archive.write(nested_zip, arcname="inner.zip")

    excluded_dir = source / "DoE"
    excluded_dir.mkdir()
    with zipfile.ZipFile(excluded_dir / "study.zip", "w") as archive:
        archive.writestr(f"{LENS_KEYWORD}_20260801.csv", "TSRID\n2\n")

    scan_and_move(source, destination)

    extracted = list(destination.rglob(f"{LENS_KEYWORD}_20260714.csv"))
    assert len(extracted) == 1
    assert not list(destination.rglob(f"{LENS_KEYWORD}_20260801.csv"))


def test_sync_selection_uses_extensions_and_exclusions() -> None:
    assert _is_selected_remote_path("batch/Summary.csv")
    assert _is_selected_remote_path("batch/raw.zip")
    assert not _is_selected_remote_path("batch/image.jpg")
    assert not _is_selected_remote_path("DoE/study/Summary.csv")


def test_vendor_csv_encoding_fallback_and_source_part(tmp_path: Path) -> None:
    csv_path = tmp_path / "Summary_GSEO_Loma_CW_DTC_DTC-L_1_01_ONLINE.csv"
    csv_path.write_bytes("TSRID,Note\n1,温度\n".encode("gb18030"))

    frame = _read_file(csv_path)

    assert frame.loc[0, "Note"] == "温度"
    assert set(frame["SourcePart"]) == {"DTC_L"}
    assert _source_part(Path("Summary_LanSi_Loma_CW_DTC-R_1_01_ONLINE.csv")) == "DTC_R"
    assert _source_part(Path("unrelated.csv")) is None


def test_optional_cache_images_and_audits(tmp_path: Path) -> None:
    config_path = tmp_path / "minimal.json"
    config_path.write_text(
        """
        {
          "gdrive": {"remote": "remote", "folder_url": "folder"},
          "output_folder": "./output_minimal",
          "filters": {
            "dataset_keyword": "Summary",
            "data_extensions": [".csv"]
          },
          "slot_map": {"1": "DTC_R"}
        }
        """,
        encoding="utf-8",
    )

    config = AppConfig(config_path)
    assert config.audit_keywords == []
    assert config.gdrive_images_folder_id is None
    assert not config.has_cache
    assert config.dashboard_title == "SFR Report — Loma CW_1_01"
