"""
state.py

Centralized state file paths for cyberbrain.

All paths under ~/.claude/cyberbrain are defined here.
This module is a leaf: no imports from other cyberbrain modules.

All path values are computed lazily via functions so that Path.home() is not
evaluated at import time. This allows tests to patch the home directory after
import without stale values leaking through module-level constants.
"""

from pathlib import Path


def _base() -> Path:
    return Path.home() / ".claude" / "cyberbrain"


def config_path() -> Path:
    return _base() / "config.json"


def extract_log_path() -> Path:
    return _base() / "logs" / "cb-extract.log"


def runs_log_path() -> Path:
    return _base() / "logs" / "cb-runs.jsonl"


def search_db_path() -> Path:
    return _base() / "search-index.db"


def search_usearch_path() -> Path:
    return _base() / "search-index.usearch"


def search_manifest_path() -> Path:
    return _base() / "search-index-manifest.json"


def index_scan_marker_path() -> Path:
    return _base() / ".index-scan-ts"


def groups_cache_path() -> Path:
    return _base() / ".restructure-groups-cache.json"


def wm_recall_log_path() -> Path:
    return _base() / "wm-recall.jsonl"


def evaluations_dir() -> Path:
    return _base() / "evaluations"


def subprocess_cwd() -> Path:
    return _base()


def audit_report_path() -> Path:
    return _base() / "audit-report.json"


def prompts_dir_legacy() -> Path:
    return _base() / "prompts"
