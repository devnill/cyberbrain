"""cb_setup tool — analyze Obsidian vault and generate/update CLAUDE.md."""

import json
import re
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from shared import _load_config


def _run_analyzer(vault: Path) -> dict:
    """Import and run the vault analyzer. Returns report dict (never raises)."""
    try:
        from analyze_vault import analyze_vault
        return analyze_vault(str(vault))
    except Exception as e:
        return {"error": str(e), "vault_path": str(vault), "total_notes": 0}


def _read_note_samples(vault: Path, md_files: list, vault_report: dict) -> str:
    """Read a representative sample of notes for LLM analysis."""
    total = len(md_files)
    if total < 50:
        sample_count = total
    elif total < 200:
        sample_count = 30
    elif total < 500:
        sample_count = 45
    else:
        sample_count = 70

    hub_stems = {n["note"] for n in vault_report.get("links", {}).get("hub_nodes", [])[:10]}
    priority = [f for f in md_files if f.stem in hub_stems]
    rest = [f for f in md_files if f.stem not in hub_stems]
    selected = (priority + rest)[:sample_count]

    samples = []
    for f in selected[:30]:  # cap at 30 for token budget
        try:
            content = f.read_text(encoding="utf-8", errors="replace")[:2000]
            rel = f.relative_to(vault)
            samples.append(f"=== {rel} ===\n{content}")
        except Exception:
            pass

    return "\n\n".join(samples)


def _build_report_summary(vault_report: dict, md_files: list) -> str:
    return json.dumps({
        "total_notes": vault_report.get("total_notes", len(md_files)),
        "folder_structure": vault_report.get("folder_structure", {}),
        "entity_types": vault_report.get("entity_types", {}),
        "naming_conventions": vault_report.get("naming_conventions", {}),
        "tags": {"top_tags": vault_report.get("tags", {}).get("top_tags", [])[:20]},
        "links": {
            "hub_nodes": vault_report.get("links", {}).get("hub_nodes", [])[:10],
            "notes_with_no_incoming_links": vault_report.get("links", {}).get("notes_with_no_incoming_links", 0),
        },
    }, indent=2)


_ANALYSIS_SYSTEM_PROMPT = """\
You are a vault knowledge architect. Analyze this Obsidian vault report and note samples.

Your job:
1. Identify the vault archetype (developer, research, whole-life, project, or hybrid)
2. Evaluate the existing type system quality (anti-patterns, design issues)
3. Generate 2-3 targeted clarifying questions the user must answer before you can \
generate a great CLAUDE.md

Return ONLY a JSON object (no markdown, no explanation):
{
  "archetype": "developer | research | whole-life | project | hybrid",
  "archetype_evidence": "1-2 sentences of evidence",
  "existing_types": ["list", "of", "types", "found"],
  "recommendation": "adopt | refine | redesign",
  "recommendation_rationale": "1-2 sentences",
  "anti_patterns": [
    {"name": "pattern name", "signal": "what you observed", "fix": "recommended fix"}
  ],
  "questions": [
    {"id": "q1", "question": "The question text"},
    {"id": "q2", "question": "The question text"}
  ]
}

Anti-pattern checklist:
- Topic-as-type (types named after domains: work-notes, personal, career)
- Type explosion (10+ types, many with only a few notes)
- Status-as-type (types like in-progress, done, archived)
- Overlapping types (feel interchangeable)
- No linking (nearly all notes have 0 outgoing wikilinks)

Only ask questions the vault makes genuinely ambiguous. If the archetype is obvious, \
don't ask about it."""

_GENERATION_SYSTEM_PROMPT = """\
You are a knowledge architect. Generate a complete, prescriptive CLAUDE.md for this \
Obsidian vault.

PRESCRIPTIVE means every section answers "what should Claude do?" — not "here's what \
currently exists." Write in imperative mood: "Use X", "Always include Y", "Do not Z."

Required sections (in order):
1. Vault Overview (2-4 sentences orienting Claude to the vault's scope and intent)
2. Knowledge Graph:
   2a. Principles (~300-400 words, adapted from canonical text below — do not copy verbatim)
   2b. Relation Vocabulary (table with columns: Predicate, When to use; include \
related/references/broader/narrower/supersedes/wasDerivedFrom plus 2-4 domain-specific ones)
3. Folder Structure (filing rules using structural patterns, not enumerated specific folders)
4. Entity Types (one subsection per type: what it captures, required frontmatter, \
YAML example with realistic values, body structure guidance)
5. Frontmatter Schema (required fields for all notes; type-specific required fields; optional)
6. Domain Taxonomy (how vault is organized by domain/area, domain tags)
7. Tagging Conventions (tag structure, what gets a tag vs type, what NOT to tag)
8. Linking Conventions (link style, how to express relationship in sentence around link)
9. File Naming and Organization (naming style, date prefixes, length guidelines)
10. Extending the Ontology (criteria for when to add types/tags — and when to resist)
11. Quality and Maintenance Rules (filing quality standards, good summary criteria)
12. Claude-Specific Behaviors (how Claude should behave when filing/recalling/enriching)
13. Known Issues / Migration Notes (ONLY if significant anti-patterns found)

Knowledge Graph Principles section must include these ideas (adapt, do not copy verbatim):
- Types describe epistemic role, not topic. `decision` is a type. `authentication` is a tag.
- Fewer types is better. If you can't classify in under 5 seconds, types are too similar.
- Write every note for your future self with no context — include situation, decision/discovery, why.
- One idea per note. "And also..." is a second note.
- Links express relationships. The sentence around a link matters as much as the link itself.
- Titles and summaries are the primary search surfaces. Make them specific and keyword-rich.
- Capture first, refine later.

Non-negotiable output rules:
- Flag inferred conventions: *(inferred — verify with vault owner)*
- Never include specific note counts, percentages, or frequencies
- Use structural patterns for folders, not enumerated specific names
- Every rule must be generalizable
- Preserve any custom sections found in an existing CLAUDE.md

Return ONLY the CLAUDE.md content. No preamble, no explanation, no markdown wrapping."""


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def cb_setup(
        vault_path: Annotated[str, Field(
            description="Absolute path to the vault. Empty = read from config."
        )] = "",
        types: Annotated[str, Field(
            description="Comma-separated type vocabulary override, e.g. 'decision,insight,problem,reference'. Skips archetype analysis if provided."
        )] = "",
        answers: Annotated[str, Field(
            description="JSON string of user answers to questions returned by a Phase 1 call. When provided, triggers Phase 2 (CLAUDE.md generation)."
        )] = "",
        dry_run: Annotated[bool, Field(
            description="Return the generated CLAUDE.md without writing it to disk."
        )] = False,
        write: Annotated[bool, Field(
            description="Write the generated CLAUDE.md to the vault root. Requires answers to be provided (Phase 2)."
        )] = False,
    ) -> str:
        """
        Analyze an Obsidian vault and generate or update its CLAUDE.md.

        Two-phase call pattern:
        - Phase 1 (call without answers): Analyzes vault structure, evaluates the type
          system, identifies anti-patterns, and returns 2-3 clarifying questions as JSON.
          Present these questions to the user and wait for answers.
        - Phase 2 (call with answers=<JSON string>): Takes user answers, generates a
          complete CLAUDE.md. Use write=True to save it, dry_run=True to preview.

        For initial configuration, run cb_configure() first to set the vault path.
        """
        from backends import call_model

        config = _load_config()
        resolved_vault = vault_path or config.get("vault_path", "")
        if not resolved_vault:
            raise ToolError(
                "No vault path configured. Pass vault_path= or run "
                "cb_configure(vault_path=...) first."
            )

        vault = Path(resolved_vault).expanduser().resolve()
        if not vault.exists():
            raise ToolError(f"Vault path does not exist: {vault}")

        md_files = [
            f for f in vault.rglob("*.md")
            if not any(part.startswith(".") for part in f.relative_to(vault).parts)
        ]

        claude_md_path = vault / "CLAUDE.md"
        existing_claude_md = (
            claude_md_path.read_text(encoding="utf-8") if claude_md_path.exists() else ""
        )

        vault_report = _run_analyzer(vault)
        note_samples = _read_note_samples(vault, md_files, vault_report)
        report_summary = _build_report_summary(vault_report, md_files)

        if not answers:
            # ── Phase 1: analyze vault, return JSON with questions ──
            types_note = (
                f"\nNote: User specified type vocabulary: {types}. "
                "Focus questions on other aspects — do not ask about types."
                if types else ""
            )
            user_message = (
                f"Vault path: {vault}\n\n"
                f"Vault analysis report:\n{report_summary}\n\n"
                f"Sample notes (representative selection):\n{note_samples[:20000]}\n\n"
                + (f"Existing CLAUDE.md:\n{existing_claude_md[:3000]}\n\n"
                   if existing_claude_md else "No existing CLAUDE.md found.\n\n")
                + types_note
                + "\nAnalyze this vault and return the JSON object."
            )

            try:
                raw = call_model(_ANALYSIS_SYSTEM_PROMPT, user_message, config)
                stripped = re.sub(r"^```(?:json)?\s*", "", raw.strip())
                stripped = re.sub(r"\s*```$", "", stripped).strip()
                result = json.loads(stripped)
                return json.dumps(result, indent=2)
            except json.JSONDecodeError:
                return raw
            except Exception as e:
                raise ToolError(f"Phase 1 analysis failed: {e}")

        else:
            # ── Phase 2: generate CLAUDE.md from analysis + user answers ──
            types_note = (
                f"\nType vocabulary specified by user: {types}"
                if types else
                "\nDetermine the type vocabulary from the analysis and user answers."
            )
            user_message = (
                f"Vault path: {vault}\n\n"
                f"Vault analysis:\n{report_summary}\n\n"
                f"Sample notes (for style and convention reference):\n{note_samples[:15000]}\n\n"
                + (f"Existing CLAUDE.md (preserve custom sections):\n{existing_claude_md[:3000]}\n\n"
                   if existing_claude_md else "No existing CLAUDE.md.\n\n")
                + f"User answers to clarifying questions:\n{answers}\n"
                + types_note
                + "\n\nGenerate the complete CLAUDE.md for this vault."
            )

            try:
                claude_md_content = call_model(_GENERATION_SYSTEM_PROMPT, user_message, config)
            except Exception as e:
                raise ToolError(f"Phase 2 generation failed: {e}")

            if dry_run or not write:
                prefix = "[DRY RUN] " if dry_run else ""
                return (
                    "## Generated CLAUDE.md\n\n"
                    f"```markdown\n{claude_md_content}\n```\n\n"
                    f"{prefix}No files written. "
                    "Call cb_setup(answers=..., write=True) to save."
                )

            try:
                claude_md_path.write_text(claude_md_content, encoding="utf-8")
            except OSError as e:
                raise ToolError(f"Failed to write CLAUDE.md: {e}")

            word_count = len(claude_md_content.split())
            return (
                f"CLAUDE.md written to {claude_md_path}\n\n"
                f"  Vault: {vault}\n"
                f"  Size:  {word_count} words\n\n"
                "Recommended next step: Run cb_enrich(dry_run=True) to see which "
                "notes are missing metadata."
            )
