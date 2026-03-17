"""cb_configure and cb_status tools — configuration and system status."""

from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from cyberbrain.mcp.shared import _load_config, RUNS_LOG_PATH
from cyberbrain.mcp.tools.recall import _DEFAULT_DB_PATH, _DEFAULT_MANIFEST_PATH


def _read_index_stats(config: dict) -> dict:
    """Query SQLite index for note counts, relation count, and stale path count."""
    import sqlite3
    db_path = config.get("search_db_path", _DEFAULT_DB_PATH)
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        by_type = {}
        for row in conn.execute("SELECT type, COUNT(*) AS cnt FROM notes GROUP BY type ORDER BY cnt DESC"):
            by_type[row["type"] or "(none)"] = row["cnt"]
        total = sum(by_type.values())
        relations_count = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        all_paths = [r[0] for r in conn.execute("SELECT path FROM notes").fetchall()]
        stale_count = sum(1 for p in all_paths if not Path(p).exists())
        conn.close()
        return {"total": total, "by_type": by_type, "relations_count": relations_count, "stale_count": stale_count}
    except Exception:
        return {}


_DEFAULT_PREFS = """\
## Cyberbrain Preferences

### Extraction
- Only capture `problem` beats if they encode a reusable pattern, not just that a bug was fixed
- Prefer fewer, richer beats over many specific ones
- Avoid session-specific operational details that won't be meaningful in 6 months

### Consolidation
- Merge notes that cover the same concept or closely related sub-topics
- Use hub-and-spoke structure (index page + subpages) when a merged note would exceed ~800 words
- Do not consolidate notes in: AI/Journal, Templates
"""

_PREFS_HEADING = "## Cyberbrain Preferences"


def _read_prefs_section(vault_path: str) -> str | None:
    """Return the Cyberbrain Preferences section from vault CLAUDE.md, or None if absent."""
    claude_md = Path(vault_path) / "CLAUDE.md"
    if not claude_md.exists():
        return None
    text = claude_md.read_text(encoding="utf-8")
    idx = text.find(_PREFS_HEADING)
    if idx == -1:
        return None
    # Find the end: next ## heading at the same level or EOF
    rest = text[idx:]
    end_match = None
    for m in __import__("re").finditer(r"^## ", rest, __import__("re").MULTILINE):
        if m.start() > 0:
            end_match = m.start()
            break
    return rest[:end_match].strip() if end_match else rest.strip()


def _write_prefs_section(vault_path: str, prefs_text: str) -> None:
    """Write or replace the Cyberbrain Preferences section in vault CLAUDE.md."""
    claude_md = Path(vault_path) / "CLAUDE.md"
    if claude_md.exists():
        text = claude_md.read_text(encoding="utf-8")
    else:
        text = ""

    new_section = prefs_text.strip()
    if not new_section.startswith(_PREFS_HEADING):
        new_section = _PREFS_HEADING + "\n\n" + new_section

    idx = text.find(_PREFS_HEADING)
    if idx == -1:
        # Append
        separator = "\n\n" if text and not text.endswith("\n\n") else ""
        text = text + separator + new_section + "\n"
    else:
        # Replace existing section
        import re as _re
        rest = text[idx:]
        end_match = None
        for m in _re.finditer(r"^## ", rest, _re.MULTILINE):
            if m.start() > 0:
                end_match = m.start()
                break
        if end_match:
            text = text[:idx] + new_section + "\n\n" + rest[end_match:]
        else:
            text = text[:idx] + new_section + "\n"

    claude_md.write_text(text, encoding="utf-8")


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True))
    def cb_configure(
        vault_path: Annotated[str | None, Field(
            description="Absolute path to your notes folder. Creates the directory if it doesn't exist. Must be within your home directory."
        )] = None,
        inbox: Annotated[str | None, Field(
            description="Vault-relative subfolder for general notes, e.g. 'AI/Claude-Sessions'. Default: 'AI/Claude-Sessions'."
        )] = None,
        capture_mode: Annotated[str | None, Field(
            description="How to file insights in Claude Desktop: 'suggest' (offer first), 'auto' (file immediately), 'manual' (only when asked)."
        )] = None,
        discover: Annotated[bool, Field(
            description="Search this Mac for existing Obsidian vaults and return candidates."
        )] = False,
        show_prefs: Annotated[bool, Field(
            description="Display the current Cyberbrain Preferences section from the vault CLAUDE.md."
        )] = False,
        set_prefs: Annotated[str | None, Field(
            description="Replace the Cyberbrain Preferences section in vault CLAUDE.md with this text. Use natural language to describe extraction and consolidation preferences."
        )] = None,
        reset_prefs: Annotated[bool, Field(
            description="Restore the Cyberbrain Preferences section in vault CLAUDE.md to the built-in defaults."
        )] = False,
        working_memory_ttl: Annotated[dict | None, Field(
            description=(
                "Set per-type working memory TTL (days before review). Pass a dict with type names as keys "
                "and day counts as values, plus an optional 'default' key. "
                "Example: {\"default\": 28, \"decision\": 56, \"problem\": 14}. "
                "Only affects newly written working-memory notes."
            )
        )] = None,
        tool_models: Annotated[dict | None, Field(
            description=(
                "Set per-tool model overrides. Pass a dict with tool names as keys and model names as values. "
                "Valid keys: restructure, recall, enrich, review, judge. "
                "Example: {\"restructure\": \"claude-sonnet-4-5-20250514\", \"judge\": \"claude-sonnet-4-5-20250514\"}. "
                "Omitted keys fall back to the global model."
            )
        )] = None,
        quality_gate_enabled: Annotated[bool | None, Field(
            description="Enable or disable quality gates for curation tools (restructure, enrich, review, recall). Default: True."
        )] = None,
        proactive_recall: Annotated[bool | None, Field(
            description="Enable or disable proactive recall (automatic context injection). Default: True."
        )] = None,
        uncertain_filing_behavior: Annotated[str | None, Field(
            description=(
                "What to do when autofile confidence is below threshold. "
                "'inbox' routes the beat to the inbox folder (default). "
                "'ask' returns a clarification prompt to the user before writing."
            )
        )] = None,
        uncertain_filing_threshold: Annotated[float | None, Field(
            description=(
                "Confidence threshold (0.0-1.0) below which uncertain_filing_behavior applies. "
                "Default: 0.5. Beats with confidence >= threshold are filed normally."
            )
        )] = None,
    ) -> str:
        """
        Configure cyberbrain or show current configuration.

        Call with no arguments to see current config and health status.
        Call with discover=True to find Obsidian vaults on this Mac.
        Call with vault_path=... to set where notes are stored.
        Call with capture_mode='suggest'|'auto'|'manual' to set filing behavior.
        Call with show_prefs=True to see current extraction/consolidation preferences.
        Call with set_prefs='...' to update preferences (written to vault CLAUDE.md).
        Call with reset_prefs=True to restore default preferences.
        Call with working_memory_ttl={...} to set per-type review TTL in days.
        Call with tool_models={...} to set per-tool model overrides.
        Call with quality_gate_enabled=True/False to enable/disable quality gates.
        Call with proactive_recall=True/False to enable/disable proactive recall.
        Call with uncertain_filing_behavior='inbox'|'ask' to control low-confidence routing.
        Call with uncertain_filing_threshold=0.5 to set the confidence cutoff (0.0-1.0).

        Use this to set up cyberbrain through conversation instead of editing config files.
        """
        import json as _json
        import threading

        cfg_path = Path.home() / ".claude" / "cyberbrain" / "config.json"

        # --- preferences operations ---
        if show_prefs or set_prefs is not None or reset_prefs:
            cfg = _load_config()
            vp = cfg.get("vault_path", "")
            if not vp or not Path(vp).exists():
                return (
                    "No vault configured or vault path does not exist. "
                    "Run cb_configure(vault_path=...) first."
                )
            if reset_prefs:
                _write_prefs_section(vp, _DEFAULT_PREFS)
                return "Cyberbrain Preferences reset to defaults in vault CLAUDE.md."
            if set_prefs is not None:
                _write_prefs_section(vp, set_prefs)
                line_count = len(set_prefs.strip().splitlines())
                return f"Cyberbrain Preferences updated in vault CLAUDE.md ({line_count} lines)."
            # show_prefs
            current = _read_prefs_section(vp)
            if current is None:
                return (
                    "No Cyberbrain Preferences section found in vault CLAUDE.md.\n\n"
                    "To add defaults: cb_configure(reset_prefs=True)\n"
                    "To set custom:   cb_configure(set_prefs='...')"
                )
            return current

        def _load_raw() -> dict:
            if cfg_path.exists():
                try:
                    return _json.loads(cfg_path.read_text())
                except Exception:
                    return {}
            return {}

        def _save_raw(cfg: dict) -> None:
            cfg_path.write_text(_json.dumps(cfg, indent=2) + "\n")

        # --- discover mode ---
        if discover:
            search_roots = [
                Path.home() / "Documents",
                Path.home() / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents",
                Path.home() / "Obsidian",
                Path.home() / "Desktop",
            ]
            found = []
            for root in search_roots:
                if not root.exists():
                    continue
                try:
                    for obsidian_dir in root.rglob(".obsidian"):
                        vault_dir = obsidian_dir.parent
                        found.append(vault_dir)
                        if len(found) >= 10:
                            break
                except (PermissionError, OSError):
                    continue
                if len(found) >= 10:
                    break

            if not found:
                return (
                    "No Obsidian vaults found in ~/Documents/, ~/Library/Mobile Documents/, "
                    "~/Obsidian/, or ~/Desktop/.\n\n"
                    "To use a custom location, call cb_configure(vault_path='/absolute/path/to/folder')."
                )

            lines = ["Found Obsidian vaults on this Mac:\n"]
            for i, v in enumerate(found, 1):
                lines.append(f"  {i}. {v}")
            lines.append(
                "\nTo use one of these vaults, call cb_configure(vault_path='<path>') "
                "with the full path from above."
            )
            return "\n".join(lines)

        # --- writes ---
        changed = []
        if vault_path is not None or inbox is not None or capture_mode is not None or working_memory_ttl is not None or tool_models is not None or quality_gate_enabled is not None or proactive_recall is not None or uncertain_filing_behavior is not None or uncertain_filing_threshold is not None:
            cfg = _load_raw()

            if vault_path is not None:
                resolved = Path(vault_path).expanduser().resolve()
                try:
                    resolved.relative_to(Path.home())
                except ValueError:
                    raise ToolError(
                        f"vault_path must be within your home directory. Got: {vault_path}"
                    )
                resolved.mkdir(parents=True, exist_ok=True)
                cfg["vault_path"] = str(resolved)
                changed.append(f"vault_path → {resolved}")

                # Rebuild index in background
                def _rebuild():
                    try:
                        from cyberbrain.extractors.search_backends import get_search_backend
                        backend = get_search_backend(cfg)
                        if hasattr(backend, "build_full_index"):
                            backend.build_full_index(cfg)
                    except Exception:
                        pass
                threading.Thread(target=_rebuild, daemon=True).start()

            if inbox is not None:
                cfg["inbox"] = inbox
                changed.append(f"inbox → {inbox}")

            if capture_mode is not None:
                valid = {"suggest", "auto", "manual"}
                if capture_mode not in valid:
                    raise ToolError(
                        f"capture_mode must be 'suggest', 'auto', or 'manual'. Got: {capture_mode}"
                    )
                cfg["desktop_capture_mode"] = capture_mode
                changed.append(f"desktop_capture_mode → {capture_mode}")

            if working_memory_ttl is not None:
                if not isinstance(working_memory_ttl, dict):
                    raise ToolError("working_memory_ttl must be a dict, e.g. {\"default\": 28, \"decision\": 56}.")
                for k, v in working_memory_ttl.items():
                    if not isinstance(v, int) or v < 1:
                        raise ToolError(f"working_memory_ttl values must be positive integers. Got {k!r}: {v!r}")
                existing = cfg.get("working_memory_ttl", {})
                existing.update(working_memory_ttl)
                cfg["working_memory_ttl"] = existing
                changed.append(f"working_memory_ttl → {existing}")

            if tool_models is not None:
                if not isinstance(tool_models, dict):
                    raise ToolError("tool_models must be a dict, e.g. {\"restructure\": \"claude-sonnet-4-5-20250514\"}.")
                _valid_tool_keys = {"restructure", "recall", "enrich", "review", "judge"}
                for k, v in tool_models.items():
                    if k not in _valid_tool_keys:
                        raise ToolError(
                            f"Invalid tool_models key: {k!r}. "
                            f"Valid keys: {', '.join(sorted(_valid_tool_keys))}."
                        )
                    if not isinstance(v, str) or not v.strip():
                        raise ToolError(f"tool_models values must be non-empty strings. Got {k!r}: {v!r}")
                    cfg[f"{k}_model"] = v
                    changed.append(f"{k}_model → {v}")

            if quality_gate_enabled is not None:
                cfg["quality_gate_enabled"] = quality_gate_enabled
                changed.append(f"quality_gate_enabled → {quality_gate_enabled}")

            if proactive_recall is not None:
                cfg["proactive_recall"] = proactive_recall
                changed.append(f"proactive_recall → {proactive_recall}")

            if uncertain_filing_behavior is not None:
                valid_behaviors = {"inbox", "ask"}
                if uncertain_filing_behavior not in valid_behaviors:
                    raise ToolError(
                        f"uncertain_filing_behavior must be 'inbox' or 'ask'. Got: {uncertain_filing_behavior}"
                    )
                cfg["uncertain_filing_behavior"] = uncertain_filing_behavior
                changed.append(f"uncertain_filing_behavior → {uncertain_filing_behavior}")

            if uncertain_filing_threshold is not None:
                if not isinstance(uncertain_filing_threshold, (int, float)) or not (0.0 <= uncertain_filing_threshold <= 1.0):
                    raise ToolError(
                        f"uncertain_filing_threshold must be a float between 0.0 and 1.0. Got: {uncertain_filing_threshold}"
                    )
                cfg["uncertain_filing_threshold"] = float(uncertain_filing_threshold)
                changed.append(f"uncertain_filing_threshold → {uncertain_filing_threshold}")

            _save_raw(cfg)
            result = "Configuration updated:\n" + "\n".join(f"  - {c}" for c in changed)
            if vault_path is not None:
                result += "\n\nSearch index rebuild started in background."
            return result

        # --- no-args: show current config + health ---
        cfg = _load_config()
        lines = ["## Cyberbrain Configuration\n"]

        vault = cfg.get("vault_path", "(not set)")
        vault_path_obj = Path(vault) if vault and vault != "(not set)" else None
        if vault_path_obj and vault_path_obj.exists():
            stats = _read_index_stats(cfg)
            note_count = stats.get("total", 0)
            lines.append(f"Vault:        {vault}")
            lines.append(f"              ✓ exists ({note_count} notes indexed)")
        elif vault_path_obj:
            lines.append(f"Vault:        {vault}")
            lines.append(f"              ⚠ directory does not exist")
        else:
            lines.append(f"Vault:        (not configured)")
            lines.append(f"              Run cb_configure(discover=True) to find Obsidian vaults,")
            lines.append(f"              or cb_configure(vault_path='/path/to/folder') to set one.")

        lines.append(f"Inbox:        {cfg.get('inbox', 'AI/Claude-Sessions')}")
        backend = cfg.get("backend", "claude-code")
        model = cfg.get("model", "claude-haiku-4-5")
        lines.append(f"Backend:      {backend} ({model})")
        _tool_model_keys = ["restructure_model", "recall_model", "enrich_model", "review_model", "judge_model"]
        overrides = {k: cfg[k] for k in _tool_model_keys if k in cfg}
        if overrides:
            override_parts = [f"{k.replace('_model', '')}: {v}" for k, v in overrides.items()]
            lines.append(f"Tool models:  {', '.join(override_parts)}")
        if cfg.get("quality_gate_enabled") is False:
            lines.append("Quality gate: disabled")
        if cfg.get("proactive_recall") is False:
            lines.append("Proactive recall: disabled")
        capture = cfg.get("desktop_capture_mode", "suggest")
        lines.append(f"Capture mode: {capture}")
        filing_behavior = cfg.get("uncertain_filing_behavior", "inbox")
        filing_threshold = cfg.get("uncertain_filing_threshold", 0.5)
        lines.append(f"Uncertain filing: behavior={filing_behavior}, threshold={filing_threshold}")

        # Last extraction run
        runs_log = Path(RUNS_LOG_PATH)
        if runs_log.exists():
            try:
                import json as _json2
                lines_raw = runs_log.read_text(encoding="utf-8").splitlines()
                last_run = None
                for line in reversed(lines_raw):
                    line = line.strip()
                    if line:
                        try:
                            last_run = _json2.loads(line)
                            break
                        except Exception:
                            pass
                if last_run:
                    ts = last_run.get("timestamp", "")[:16].replace("T", " ")
                    beats = last_run.get("beats_written", 0)
                    sid = last_run.get("session_id", "")[:8]
                    lines.append(f"Last capture: {ts} ({beats} beats from session {sid})")
            except Exception:
                pass

        lines.append("")
        lines.append("To change settings: cb_configure(vault_path=..., inbox=..., capture_mode=...)")
        lines.append("To find Obsidian vaults: cb_configure(discover=True)")
        return "\n".join(lines)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
    def cb_status(
        last_n_runs: Annotated[int, Field(ge=1, le=50, description="How many recent runs to show")] = 10,
    ) -> str:
        """
        Show cyberbrain system status: recent extraction runs, index health, and config summary.
        Call this to understand what cyberbrain has captured and whether the index is healthy.
        """
        import json as _json
        config = _load_config()

        # --- Recent runs ---
        runs = []
        runs_log = Path(RUNS_LOG_PATH)
        if runs_log.exists():
            try:
                lines = runs_log.read_text(encoding="utf-8").splitlines()
                for line in lines[-last_n_runs:]:
                    line = line.strip()
                    if line:
                        try:
                            runs.append(_json.loads(line))
                        except _json.JSONDecodeError:
                            pass
            except OSError:
                pass

        # --- Index stats ---
        stats = _read_index_stats(config)

        # --- Manifest ---
        manifest = {}
        try:
            manifest_path = Path(config.get("search_manifest_path", _DEFAULT_MANIFEST_PATH))
            if manifest_path.exists():
                manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass

        # --- Format output ---
        lines = ["## Cyberbrain Status", ""]

        # Recent runs table
        lines.append(f"### Recent Runs (last {last_n_runs})")
        if runs:
            lines.append("| Time | Session | Project | Trigger | Beats | Duration |")
            lines.append("|------|---------|---------|---------|-------|----------|")
            for r in reversed(runs):
                ts = r.get("timestamp", "")[:16].replace("T", " ")
                sid = r.get("session_id", "")[:8]
                proj = r.get("project", "")[:20]
                trigger = r.get("trigger", "")
                beats = f"{r.get('beats_written', 0)}/{r.get('beats_extracted', 0)}"
                dur = f"{r.get('duration_seconds', 0)}s"
                lines.append(f"| {ts} | {sid} | {proj} | {trigger} | {beats} | {dur} |")
        else:
            lines.append("No runs recorded yet.")

        # Last run detail
        if runs:
            last = runs[-1]
            lines.append("")
            lines.append("### Last Run — Beats Extracted")
            for b in last.get("beats", []):
                lines.append(f"- **{b.get('title', '')}** ({b.get('type', '')} · {b.get('scope', '')}) → {b.get('path', '')}")
            for err in last.get("errors", []):
                lines.append(f"- ⚠ {err}")
            if not last.get("beats") and not last.get("errors"):
                lines.append("No beats written in last run.")

        # Index health
        lines.append("")
        lines.append("### Index Health")
        if stats:
            lines.append(f"- Notes indexed: {stats['total']}")
            if stats["by_type"]:
                type_str = ", ".join(f"{t}: {c}" for t, c in stats["by_type"].items())
                lines.append(f"  - {type_str}")
            lines.append(f"- Relations: {stats['relations_count']}")
            stale = stats["stale_count"]
            stale_note = "✓ all indexed notes exist on disk" if stale == 0 else f"⚠ {stale} path(s) not found on disk"
            lines.append(f"- Stale paths: {stale} ({stale_note})")
            if manifest.get("model_name"):
                vec_count = len(manifest.get("id_map", []))
                lines.append(f"- Semantic vectors: {vec_count} (model: {manifest['model_name']})")
        else:
            lines.append("Index not found or empty.")

        # Config summary
        lines.append("")
        lines.append("### Config")
        lines.append(f"- Vault: {config.get('vault_path', '(not set)')}")
        lines.append(f"- Inbox: {config.get('inbox', '(not set)')}")
        backend = config.get("backend", "claude-code")
        model = config.get("model", "claude-haiku-4-5")
        lines.append(f"- Backend: {backend} ({model})")

        # Per-tool model overrides
        _tool_model_keys = ["restructure_model", "recall_model", "enrich_model", "review_model", "judge_model"]
        overrides = {k: config[k] for k in _tool_model_keys if k in config}
        if overrides:
            override_parts = [f"{k.replace('_model', '')}: {v}" for k, v in overrides.items()]
            lines.append(f"- Per-tool models: {', '.join(override_parts)}")

        if not config.get("quality_gate_enabled", True):
            lines.append("- Quality gate: DISABLED")
        if not config.get("proactive_recall", True):
            lines.append("- Proactive recall: DISABLED")

        # Preferences and provenance coverage
        vp = config.get("vault_path", "")
        if vp and Path(vp).exists():
            prefs = _read_prefs_section(vp)
            if prefs:
                prefs_lines = len(prefs.strip().splitlines())
                lines.append(f"- Preferences: set ({prefs_lines} lines) — cb_configure(show_prefs=True) to view")
            else:
                lines.append("- Preferences: not set — cb_configure(reset_prefs=True) to add defaults")

            # Provenance coverage
            try:
                import sqlite3 as _sqlite3
                from cyberbrain.mcp.tools.recall import _DEFAULT_DB_PATH
                db_path = config.get("search_db_path", _DEFAULT_DB_PATH)
                conn = _sqlite3.connect(db_path)
                total_notes = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
                conn.close()
                lines.append(f"- Provenance coverage: {total_notes} notes indexed — run cb_enrich to backfill missing cb_source fields")
            except Exception:
                pass

            # Working memory stats
            wm_folder = config.get("working_memory_folder", "AI/Working Memory")
            wm_path = Path(vp) / wm_folder
            if wm_path.exists():
                wm_notes = list(wm_path.rglob("*.md"))
                from datetime import date as _date
                today = _date.today()
                due_count = 0
                for p in wm_notes:
                    try:
                        import yaml as _yaml
                        text = p.read_text(encoding="utf-8", errors="replace")
                        if not text.startswith("---"):
                            continue
                        end = text.find("\n---", 3)
                        if end == -1:
                            continue
                        fm = _yaml.safe_load(text[3:end]) or {}
                        raw = fm.get("cb_review_after", "")
                        if raw and _date.fromisoformat(str(raw)) <= today:
                            due_count += 1
                    except Exception:
                        pass
                lines.append(f"- Working memory: {len(wm_notes)} notes in {wm_folder}")
                if due_count:
                    lines.append(f"  ⚠ {due_count} note(s) due for review — run cb_review()")

        return "\n".join(lines)
