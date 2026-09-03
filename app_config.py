"""
app_config.py — Load project config from a JSON file.

All output goes into one folder per config:

    output_loma_daily/
    ├── sync_folder/
    ├── data_folder/
    ├── datasets/
    ├── data.db
    ├── sfr_report.html
    └── db_viewer.html

Switch configs:
    python run_pipeline.py --config loma_daily --skip-sync
    python sfr_report.py --config pre_EVT2

Or via env var:
    export APP_CONFIG=pre_EVT2

Check active config:
    python app_config.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).parent
CONFIG_DIR = PROJECT_DIR / "config"


def _available_configs() -> list[Path]:
    """Return sorted list of .json files in the config/ directory."""
    if not CONFIG_DIR.is_dir():
        return []
    return sorted(CONFIG_DIR.glob("*.json"))


def _resolve_config_name(name: str) -> Path:
    """Resolve a config name (with or without .json) to a path inside config/."""
    if not name.endswith(".json"):
        name = name + ".json"
    p = CONFIG_DIR / name
    if not p.exists():
        print(f"Error: config file not found: {p}")
        sys.exit(1)
    return p


def _prompt_for_config(configs: list[Path]) -> Path:
    """Prompt the user to pick a config interactively."""
    print("Available configs:")
    for i, c in enumerate(configs, 1):
        print(f"  {i}) {c.stem}")
    print()

    while True:
        try:
            choice = input("Select config [1-{}]: ".format(len(configs))).strip()
            idx = int(choice) - 1
            if 0 <= idx < len(configs):
                return configs[idx]
        except (ValueError, EOFError, KeyboardInterrupt):
            pass
        print(f"  Please enter a number between 1 and {len(configs)}.")


def _find_config_file() -> Path:
    """Resolve config file from: --config flag > APP_CONFIG env > interactive prompt."""
    for i, arg in enumerate(sys.argv):
        if arg == "--config" and i + 1 < len(sys.argv):
            name = sys.argv[i + 1]
            sys.argv.pop(i)
            sys.argv.pop(i)
            return _resolve_config_name(name)

    env = os.environ.get("APP_CONFIG")
    if env:
        return _resolve_config_name(env)

    configs = _available_configs()
    if not configs:
        print(f"Error: no config files found in {CONFIG_DIR}")
        sys.exit(1)
    if len(configs) == 1:
        print(f"Auto-selected config: {configs[0].stem}")
        return configs[0]

    return _prompt_for_config(configs)


class AppConfig:
    def __init__(self, config_path: Path) -> None:
        self._path = config_path
        self._root = PROJECT_DIR
        self._data = json.loads(config_path.read_text())

        # Resolve output folder relative to the project root
        self._output = (self._root / self._data["output_folder"]).resolve()

    def _out(self, name: str) -> Path:
        return self._output / name

    @property
    def config_name(self) -> str:
        return self._path.stem

    @property
    def output_folder(self) -> Path:
        return self._output

    # --- Dashboard metadata ---
    @property
    def dashboard_title(self) -> str:
        dashboard = self._data.get("dashboard", {})
        return dashboard.get("title", "SFR Report — Loma CW_1_01")

    @property
    def dashboard_label(self) -> str:
        dashboard = self._data.get("dashboard", {})
        return dashboard.get("label", self.config_name)

    # --- GDrive ---
    @property
    def gdrive_remote(self) -> str:
        return self._data["gdrive"]["remote"]

    @property
    def gdrive_url(self) -> str:
        return self._data["gdrive"]["folder_url"]

    @property
    def gdrive_images_folder_id(self) -> str | None:
        return self._data["gdrive"].get("images_folder_id")

    # --- Cache (persistent GDrive storage for DB/datasets/reports) ---
    @property
    def cache_remote(self) -> str | None:
        cache = self._data.get("cache")
        return cache.get("remote") if cache else None

    @property
    def cache_folder_id(self) -> str | None:
        cache = self._data.get("cache")
        return cache.get("folder_id") if cache else None

    @property
    def has_cache(self) -> bool:
        return bool(self.cache_remote and self.cache_folder_id)

    # --- Paths (all inside output_folder) ---
    @property
    def sync_folder(self) -> Path:
        return self._out("sync_folder")

    @property
    def data_folder(self) -> Path:
        return self._out("data_folder")

    @property
    def datasets(self) -> Path:
        return self._out("datasets")

    @property
    def images_folder(self) -> Path:
        return self._out("images")

    @property
    def db_file(self) -> Path:
        return self._out("data.db")

    @property
    def report_file(self) -> Path:
        return self._out("sfr_report.html")

    @property
    def report_pdf(self) -> Path:
        return self._out("sfr_report.pdf")

    @property
    def viewer_file(self) -> Path:
        return self._out("db_viewer.html")

    @property
    def audit_datasets(self) -> Path:
        return self._out("audit_datasets")

    # --- Filters ---
    @property
    def dataset_keyword(self) -> str | list[str]:
        """Return keyword(s) for matching online dataset files. May be a string or list."""
        return self._data["filters"]["dataset_keyword"]

    @property
    def dataset_keywords(self) -> list[str]:
        """Always return a list of keywords for matching online dataset files."""
        kw = self._data["filters"]["dataset_keyword"]
        return kw if isinstance(kw, list) else [kw]

    @property
    def audit_keyword(self) -> str | list[str]:
        """Return keyword(s) for matching audit dataset files. May be a string or list."""
        return self._data["filters"].get("audit_keyword", [])

    @property
    def audit_keywords(self) -> list[str]:
        """Always return a list of keywords for matching audit dataset files."""
        kw = self._data["filters"].get("audit_keyword", [])
        return kw if isinstance(kw, list) else [kw]

    @property
    def data_extensions(self) -> set[str]:
        return set(self._data["filters"]["data_extensions"])

    @property
    def archive_extensions(self) -> set[str]:
        return set(self._data["filters"].get("archive_extensions", [".zip", ".rar"]))

    @property
    def excluded_path_keywords(self) -> list[str]:
        return list(self._data["filters"].get("exclude_path_keywords", []))

    @property
    def sync_extensions(self) -> set[str]:
        configured = self._data["filters"].get("sync_extensions")
        if configured:
            return set(configured)
        return self.data_extensions | self.archive_extensions

    # --- Slot map ---
    @property
    def slot_map(self) -> dict[str, str]:
        return self._data["slot_map"]

    def ensure_folders(self) -> None:
        """Create output folder structure if not exists."""
        for d in [
            self.sync_folder,
            self.data_folder,
            self.datasets,
            self.audit_datasets,
            self.images_folder,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def summary(self) -> str:
        return (
            f"Config: {self._path.name}\n"
            f"  Dashboard     : {self.dashboard_title}\n"
            f"  Output folder : {self._output}\n"
            f"  GDrive remote : {self.gdrive_remote}\n"
            f"  GDrive URL    : {self.gdrive_url}\n"
            f"  Cache remote  : {self.cache_remote}\n"
            f"  Cache folder  : {self.cache_folder_id}\n"
            f"  sync_folder   : {self.sync_folder}\n"
            f"  data_folder   : {self.data_folder}\n"
            f"  datasets      : {self.datasets}\n"
            f"  audit_datasets: {self.audit_datasets}\n"
            f"  images_folder : {self.images_folder}\n"
            f"  db_file       : {self.db_file}\n"
            f"  report_file   : {self.report_file}\n"
            f"  viewer_file   : {self.viewer_file}\n"
            f"  keyword       : {self.dataset_keyword}\n"
            f"  audit_keyword : {self.audit_keyword}\n"
            f"  exclusions    : {self.excluded_path_keywords}\n"
            f"  extensions    : {self.data_extensions}\n"
            f"  slot_map      : {self.slot_map}"
        )


cfg = AppConfig(_find_config_file())


if __name__ == "__main__":
    print(cfg.summary())
