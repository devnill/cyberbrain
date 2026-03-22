"""
state.py

Centralized state file paths for cyberbrain.

All paths under ~/.claude/cyberbrain are defined here.
This module is a leaf: no imports from other cyberbrain modules.
"""

from pathlib import Path

_BASE = Path.home() / ".claude" / "cyberbrain"

CONFIG_PATH = _BASE / "config.json"
EXTRACT_LOG_PATH = _BASE / "logs" / "cb-extract.log"
RUNS_LOG_PATH = _BASE / "logs" / "cb-runs.jsonl"
SEARCH_DB_PATH = _BASE / "search-index.db"
SEARCH_USEARCH_PATH = _BASE / "search-index.usearch"
SEARCH_MANIFEST_PATH = _BASE / "search-index-manifest.json"
INDEX_SCAN_MARKER_PATH = _BASE / ".index-scan-ts"
GROUPS_CACHE_PATH = _BASE / ".restructure-groups-cache.json"
WM_RECALL_LOG_PATH = _BASE / "wm-recall.jsonl"
EVALUATIONS_DIR = _BASE / "evaluations"
SUBPROCESS_CWD = _BASE
PROMPTS_DIR_LEGACY = _BASE / "prompts"
