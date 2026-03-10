# Module: Prompts

## Scope

LLM prompt templates stored as markdown files. These define the behavior of all LLM calls in the system: extraction, autofile routing, enrichment, restructuring (6 phases), working memory review, recall synthesis, quality gate validation, and evaluation.

NOT responsible for: prompt loading logic (config module and per-tool loaders), template variable injection (calling code).

## Provides

23 prompt files organized into families:

### Extraction (2 files)
- `extract-beats-system.md` — System prompt for beat extraction. Defines beat JSON schema, type vocabulary reference, durability rules, title constraints, relation format. (~7,900 chars)
- `extract-beats-user.md` — User message template. Variables: `{project_name}`, `{cwd}`, `{trigger}`, `{transcript}`, `{vault_claude_md_section}`.

### Autofile (2 files)
- `autofile-system.md` — System prompt for filing decisions. Defines action schema (create/extend), note format, collision handling rules, path constraints.
- `autofile-user.md` — User message template. Variables: `{beat_json}`, `{related_docs}`, `{vault_context}`, `{vault_folders}`.

### Enrichment (2 files)
- `enrich-system.md` — System prompt for batch frontmatter enrichment. Variables: `{vault_type_context}`.
- `enrich-user.md` — User message template. Variables: `{count}`, `{notes_block}`.

### Restructure (8 files)
- `restructure-system.md` / `restructure-user.md` — Legacy single-call restructure prompt (split + merge).
- `restructure-audit-system.md` / `restructure-audit-user.md` — Audit phase: topical fit and quality checks. Flags `flag-misplaced`, `flag-low-quality`.
- `restructure-decide-system.md` / `restructure-decide-user.md` — Decision phase: action selection for clusters (merge, hub-spoke, subfolder, keep-separate).
- `restructure-generate-system.md` / `restructure-generate-user.md` — Content generation phase: produces merged notes, hub pages.
- `restructure-group-system.md` / `restructure-group-user.md` — LLM-driven semantic clustering.

### Review (2 files)
- `review-system.md` — System prompt for working memory review decisions (promote/extend/delete).
- `review-user.md` — User message template. Variables: `{note_count}`, `{vault_prefs_section}`, `{notes_block}`.

### Synthesis (2 files)
- `synthesize-system.md` — System prompt for LLM synthesis of recall results.
- `synthesize-user.md` — User message template. Variables: `{query}`, `{note_count}`, `{notes_block}`.

### Quality Gate (1 file)
- `quality-gate-system.md` — System prompt for LLM-as-judge quality validation. Variables: `{operation}`. Contains per-operation criteria sections.

### Evaluate (1 file)
- `evaluate-system.md` — System prompt for internal dev tooling (extraction quality evaluation). Not loaded by production code.

### Claude Desktop (1 file)
- `claude-desktop-project.md` — System prompt / project context for Claude Desktop sessions using cyberbrain.

## Requires

Nothing — prompts are passive template files loaded by other modules.

## Boundary Rules

- Prompts are the primary mechanism for controlling LLM behavior. Changing a prompt file changes system behavior on next invocation.
- Prompts use `{variable_name}` syntax for Python `str.format_map()` injection.
- Hot reload: prompts are read from disk on each invocation (no caching).
- The vault's CLAUDE.md content is injected into prompts via `{vault_claude_md_section}` or `{vault_context}` — this is how vault-adaptive behavior works.
- The Cyberbrain Preferences section (managed via `cb_configure`) is injected into extraction and restructure prompts.
- Prompt files must not contain unescaped `{` or `}` outside of template variables (would cause `KeyError` on format_map).

## Internal Design Notes

- Directory: `prompts/` (23 files)
- Restructure has the most prompts (8 files) reflecting its multi-phase architecture
- `extract-beats-system.md` is the longest prompt (~7,900 chars) — defines the core beat extraction behavior
- `claude-desktop-project.md` (~6,500 chars) is a standalone guide not loaded by any Python code — it's meant to be pasted into Claude Desktop project settings
