# Mock Vault Testing Infrastructure

Mock Obsidian vaults for manual and human-in-the-loop testing of cyberbrain features. These vaults complement the automated test suite by providing realistic vault structures you can operate on to observe tool behavior beyond unit tests.

## Quick Start

```bash
# List available vaults
bash scripts/test-vault.sh list

# Deploy a vault for testing
bash scripts/test-vault.sh deploy mature

# Test cyberbrain tools against the deployed vault
# ...

# Reset to initial state after testing
bash scripts/test-vault.sh reset

# Restore original config when done
bash scripts/test-vault.sh teardown
```

## Vault Variants

### 1. `empty/` — Fresh Onboarding

**Purpose:** Test the first-run experience when no vault structure exists.

- Contains only `.obsidian/` directory marker
- No notes, no CLAUDE.md
- **Note count:** 0

**Tests:**
- `cb_setup` first-run (generates CLAUDE.md from vault analysis)
- `cb_configure` vault discovery and initial configuration

---

### 2. `para/` — PARA Methodology

**Purpose:** Test tool behavior with a structured vault using Projects/Areas/Resources/Archive organization.

- Folders: `Projects/API-Gateway/`, `Projects/Auth-Service/`, `Areas/DevOps/`, `Areas/Security/`, `Resources/Patterns/`, `Resources/Tools/`, `Archive/Legacy-Migration/`
- CLAUDE.md with PARA-specific type vocabulary and folder conventions
- **Note count:** 18

**Tests:**
- `cb_extract` routing into PARA folders based on scope and project
- `cb_enrich` across different folder types
- `cb_restructure folder_hub` within Projects subfolders
- `cb_recall` across PARA categories

---

### 3. `zettelkasten/` — Atomic Notes

**Purpose:** Test tool behavior with a flat, link-heavy vault using Zettelkasten conventions.

- Flat structure with timestamp-prefixed filenames (`YYYYMMDDHHMMSS Title.md`)
- Extensive `related` frontmatter links forming a dense knowledge graph
- CLAUDE.md with Zettelkasten conventions
- **Note count:** 21

**Tests:**
- `cb_restructure` grouping and hub creation across flat notes
- `cb_recall` across a dense link network
- Relation-based discovery and traversal
- `cb_reindex` with many cross-references

---

### 4. `mature/` — Full Feature Coverage

**Purpose:** Exercise every cyberbrain tool against a vault that covers all feature surfaces.

- Multiple folders: `AI/Claude-Sessions/`, `AI/Working Memory/`, `Projects/Data-Pipeline/`, `Projects/Frontend-Rewrite/`
- All 4 beat types: decision, insight, problem, reference
- Working memory notes with `cb_ephemeral: true` and `cb_review_after` dates
- Locked notes (`cb_lock: true`) that should be skipped by restructure/review
- Notes in `.trash/` folder
- Notes with relations (`related`, `references`, `broader`)
- Notes with incomplete frontmatter (missing summary, tags, or type)
- `AI/Cyberbrain-Log.md` consolidation log with sample entries
- `wm-recall.jsonl` with sample recall log entries
- CLAUDE.md with custom Cyberbrain Preferences section
- A cluster of 4 closely related Airflow notes suitable for merging
- One note >2000 words suitable for splitting ("Comprehensive Guide to Database Indexing")
- **Note count:** 40+ (excluding CLAUDE.md, log, and trash)

**Tests:**
- `cb_enrich` finds notes with missing frontmatter fields
- `cb_review` finds due and past-due working memory notes
- `cb_restructure` has mergeable clusters (Airflow notes) and splittable large notes
- `cb_recall` searches across all beat types
- `cb_reindex` has stale entries to prune (trash notes)
- `cb_configure` reads custom preferences from CLAUDE.md
- Locked notes are skipped appropriately

---

### 5. `working-memory/` — Working Memory Lifecycle

**Purpose:** Test working memory review decisions with varied note ages and recall patterns.

- All notes are working memory (`cb_ephemeral: true`)
- Date distribution (rewritten relative to today on deploy):
  - 5 past-due (`cb_review_after` 7-35 days ago)
  - 5 due within 7 days
  - 5 future (14-56 days from now)
  - 3 additional notes with near-term dates
- `wm-recall.jsonl` with varied recall counts (some heavily recalled, some never)
- Mix of project-scoped (webshop) and general-scoped notes
- **Note count:** 18

**Tests:**
- `cb_review` decision quality: promote heavily-recalled notes, extend active ones, delete never-recalled past-due notes
- Working memory TTL behavior
- Recall count correlation with review decisions

## Script Commands

| Command | Description |
|---------|-------------|
| `deploy <variant>` | Deep-copy vault to `~/.claude/cyberbrain/test-vault/`, update `config.json` vault_path. Rewrites `cb_review_after` dates relative to today for `working-memory` and `mature` vaults. For `mature` and `working-memory` variants, copies `wm-recall.jsonl` to `~/.claude/cyberbrain/` (backs up any existing file; restored on teardown). |
| `reset` | Restore active test vault to initial state from repo copy |
| `list` | Show available variants with brief descriptions |
| `status` | Show which variant is deployed and whether files have been modified |
| `teardown` | Restore original `vault_path` in config and clean up test vault |

## Content Guidelines

- All notes use realistic technical content (software architecture, debugging, API design, tool configurations)
- Valid YAML frontmatter with realistic UUIDs for `id` fields
- Varied and realistic tags
- No personal data, no lorem ipsum
- Beat titles do not contain `#`, `[`, `]`, or `^` (Obsidian wikilink constraint)
- Date placeholders (`REVIEW_DATE_PAST_N`, `REVIEW_DATE_SOON_N`, `REVIEW_DATE_FUTURE_N`) in working memory notes are rewritten to relative dates by the deploy script
