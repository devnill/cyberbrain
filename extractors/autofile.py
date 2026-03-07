"""
autofile.py

Intelligent beat filing using LLM judgment for vault placement.
"""

import json
import os
import re
import sys
from pathlib import Path

from backends import BackendError, call_model
from config import load_prompt
from frontmatter import parse_frontmatter, read_frontmatter_tags
from vault import (
    _is_within_vault,
    _wm_frontmatter_fields,
    build_vault_titles_set,
    inject_provenance,
    read_vault_claude_md,
    resolve_relations,
    search_vault,
    write_beat,
)


def _update_cb_modified(note_path: Path, now) -> None:
    """Update or add cb_modified timestamp in a note's frontmatter using ruamel.yaml."""
    try:
        from ruamel.yaml import YAML
    except ImportError:
        return

    try:
        text = note_path.read_text(encoding="utf-8")
    except OSError:
        return

    if not text.startswith("---"):
        return
    end = text.find("\n---", 3)
    if end == -1:
        return

    fm_text = text[3:end]
    body_text = text[end + 4:]

    yaml = YAML()
    yaml.preserve_quotes = True
    try:
        import io
        fm = yaml.load(fm_text)
    except Exception:
        return

    if not isinstance(fm, dict):
        return

    fm["cb_modified"] = now.strftime("%Y-%m-%dT%H:%M:%S")

    import io
    out = io.StringIO()
    yaml.dump(fm, out)
    new_fm = out.getvalue().rstrip("\n")
    note_path.write_text(f"---\n{new_fm}\n---{body_text}", encoding="utf-8")


def _merge_relations_into_note(note_path: Path, new_relations: list) -> None:
    """
    Merge new resolved relations into a note's related: frontmatter field
    using ruamel.yaml for round-trip rewriting (preserves all other formatting).

    Falls back to a no-op with a warning if ruamel.yaml is not installed.
    Only adds wikilinks not already present — deduplicates by target title.
    """
    try:
        from ruamel.yaml import YAML
    except ImportError:
        print(
            "[extract_beats] ruamel.yaml not installed — skipping relation merge. "
            "Run: pip install ruamel.yaml  (or install via cyberbrain venv)",
            file=sys.stderr,
        )
        return

    try:
        text = note_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[extract_beats] Could not read note for relation merge: {e}", file=sys.stderr)
        return

    if not text.startswith("---"):
        return
    end = text.find("\n---", 3)
    if end == -1:
        return

    fm_text = text[3:end]
    body_text = text[end + 4:]

    yaml = YAML()
    yaml.preserve_quotes = True
    try:
        import io
        fm = yaml.load(fm_text)
    except Exception as e:
        print(f"[extract_beats] ruamel.yaml parse error: {e}", file=sys.stderr)
        return

    if not isinstance(fm, dict):
        return

    existing_related = fm.get("related", [])
    if not isinstance(existing_related, list):
        existing_related = []

    # Deduplicate by target title (strip [[ ]] for comparison)
    existing_targets = {
        str(link).strip("[]").lower()
        for link in existing_related
    }

    added = False
    for rel in new_relations:
        wikilink = f"[[{rel['target']}]]"
        if rel["target"].lower() not in existing_targets:
            existing_related.append(wikilink)
            existing_targets.add(rel["target"].lower())
            added = True

    if not added:
        return

    fm["related"] = existing_related

    import io
    out = io.StringIO()
    yaml.dump(fm, out)
    new_fm = out.getvalue().rstrip("\n")

    new_text = f"---\n{new_fm}\n---{body_text}"
    try:
        note_path.write_text(new_text, encoding="utf-8")
        print(f"[extract_beats] Merged {len([r for r in new_relations])} relation(s) into {note_path.name}", file=sys.stderr)
    except OSError as e:
        print(f"[extract_beats] Could not write relation merge: {e}", file=sys.stderr)


def autofile_beat(beat: dict, config: dict, session_id: str, cwd: str, now,
                  vault_context: str | None = None, source: str = "hook-extraction") -> Path | None:
    """File a beat intelligently into the vault using LLM judgment."""
    vault_path = config["vault_path"]

    # Load vault filing context from CLAUDE.md if not pre-cached by caller
    if vault_context is None:
        vault_context_text = read_vault_claude_md(vault_path)
        vault_context = vault_context_text if vault_context_text is not None else \
            "File notes using human-readable names with spaces. Use types: decision, insight, problem, reference."

    # Working-memory beats search within the WM folder; durable beats search the whole vault
    durability = beat.get("durability", "durable")
    if durability == "working-memory":
        wm_root = config.get("working_memory_folder", "AI/Working Memory")
        project_name = config.get("project_name", "")
        if beat.get("scope") == "project" and project_name:
            search_root = str(Path(vault_path) / wm_root / project_name)
        else:
            search_root = str(Path(vault_path) / wm_root)
        # Fall back to vault root if WM folder doesn't exist yet
        if not Path(search_root).exists():
            search_root = vault_path
    else:
        search_root = vault_path

    # Search for related docs — ranked by keyword match count, up to 5 candidates
    related_paths = search_vault(beat, search_root, max_results=5)
    related_docs = []
    for path in related_paths:
        try:
            content = Path(path).read_text(encoding="utf-8")
            rel = os.path.relpath(path, vault_path)
            related_docs.append(f"### {rel}\n\n{content[:2000]}")
        except OSError:
            pass

    # Folder listing: WM beats see the WM folder tree; durable beats see the vault root
    try:
        folder_root = Path(search_root) if durability == "working-memory" else Path(vault_path)
        vault_folders = "\n".join(
            str(p.relative_to(vault_path))
            for p in sorted(folder_root.iterdir())
            if p.is_dir() and not p.name.startswith(".")
        )
    except OSError:
        vault_folders = ""

    system_prompt = load_prompt("autofile-system.md")
    user_message = load_prompt("autofile-user.md").format_map({
        "beat_json": json.dumps(beat, indent=2),
        "related_docs": "\n\n---\n\n".join(related_docs) if related_docs else "(none found)",
        "vault_context": vault_context,
        "vault_folders": vault_folders or "(empty)",
    })

    print(f"[extract_beats] autofile: using model for filing decision", file=sys.stderr)

    try:
        raw = call_model(system_prompt, user_message, config)
    except BackendError as e:
        print(f"[extract_beats] autofile: backend error, falling back to inbox: {e}", file=sys.stderr)
        return write_beat(beat, config, session_id, cwd, now, source=source)
    if not raw:
        return write_beat(beat, config, session_id, cwd, now, source=source)

    # Strip code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        decision = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[extract_beats] autofile: bad JSON from model: {e}", file=sys.stderr)
        return write_beat(beat, config, session_id, cwd, now)

    action = decision.get("action")
    vault = Path(vault_path)

    if action == "extend":
        target_rel = decision.get("target_path", "")
        target = vault / target_rel
        if not _is_within_vault(vault, target):
            print(f"[extract_beats] autofile: path traversal rejected: {target_rel}", file=sys.stderr)
            return write_beat(beat, config, session_id, cwd, now, source=source)
        insertion = decision.get("insertion", "")
        if not target.exists() or not insertion:
            return write_beat(beat, config, session_id, cwd, now, source=source)

        vault_titles = build_vault_titles_set(vault_path)
        raw_relations = beat.get("relations", [])
        new_relations = resolve_relations(raw_relations, vault_titles)
        if new_relations:
            _merge_relations_into_note(target, new_relations)

        with open(target, "a", encoding="utf-8") as f:
            f.write(f"\n\n{insertion.strip()}\n")
        _update_cb_modified(target, now)
        print(f"[extract_beats] autofile: extended {target}", file=sys.stderr)
        return target

    elif action == "create":
        rel_path = decision.get("path", "")
        content = decision.get("content", "")
        if not rel_path or not content:
            return write_beat(beat, config, session_id, cwd, now, source=source)
        output_path = vault / rel_path
        if not _is_within_vault(vault, output_path):
            print(f"[extract_beats] autofile: path traversal rejected: {rel_path}", file=sys.stderr)
            return write_beat(beat, config, session_id, cwd, now, source=source)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Inject provenance (and WM fields if applicable) into LLM-generated content
        extra_fields = None
        if beat.get("durability") == "working-memory":
            extra_fields = _wm_frontmatter_fields(beat, config, now)
        content = inject_provenance(content, source, session_id, now, extra_fields=extra_fields)

        # Collision handling: check if target already exists
        if output_path.exists():
            existing_tags = read_frontmatter_tags(output_path)
            beat_tags = set(str(t).lower() for t in beat.get("tags", []) if t)
            overlap = len(existing_tags & beat_tags)

            if overlap >= 2:
                with open(output_path, "a", encoding="utf-8") as f:
                    f.write(f"\n\n{content.strip()}\n")
                _update_cb_modified(output_path, now)
                print(f"[extract_beats] autofile: collision resolved as extend (tag overlap={overlap}): {output_path}", file=sys.stderr)
                return output_path
            else:
                beat_tags_list = [str(t).lower() for t in beat.get("tags", []) if t]
                distinguishing_tag = beat_tags_list[0] if beat_tags_list else "new"
                base_stem = output_path.stem
                specific_path = output_path.parent / f"{base_stem} — {distinguishing_tag}.md"

                if specific_path.exists():
                    counter = 2
                    specific_path = output_path.parent / f"{counter} {output_path.name}"
                    while specific_path.exists():
                        counter += 1
                        specific_path = output_path.parent / f"{counter} {output_path.name}"

                output_path = specific_path

        output_path.write_text(content, encoding="utf-8")
        print(f"[extract_beats] autofile: created {output_path}", file=sys.stderr)

        # Update search index post-create
        try:
            from search_index import update_search_index
            fm = parse_frontmatter(output_path.read_text(encoding="utf-8"))
            update_search_index(str(output_path), fm, config)
        except (ImportError, Exception):
            pass

        return output_path

    else:
        print(f"[extract_beats] autofile: unknown action '{action}', falling back", file=sys.stderr)
        return write_beat(beat, config, session_id, cwd, now, source=source)
