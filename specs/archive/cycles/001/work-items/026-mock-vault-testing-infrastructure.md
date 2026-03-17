# Work Item 026: Mock vault testing infrastructure

## Objective

Create a set of mock Obsidian vaults for manual/human-in-the-loop testing of cyberbrain features. These vaults complement the automated test fixtures by providing realistic vault structures that humans can act upon to feel the effects of changes beyond unit tests.

## Complexity

Medium-High

## Dependencies

None

## File Scope

- `tests/vaults/` (create) — directory containing mock vault variants
- `tests/vaults/README.md` (create) — documentation of vault variants, use cases, and reset instructions
- `tests/vaults/empty/` (create) — empty vault variant
- `tests/vaults/para/` (create) — PARA-structured vault
- `tests/vaults/zettelkasten/` (create) — Zettelkasten-structured vault
- `tests/vaults/mature/` (create) — fully populated vault with all feature surfaces
- `tests/vaults/working-memory/` (create) — vault focused on working memory lifecycle
- `scripts/test-vault.sh` (create) — script to deploy, reset, and select vault variants

## Acceptance Criteria

- [ ] 5 vault variants exist, each with `.obsidian/` marker directory
- [ ] Each vault has a `CLAUDE.md` with appropriate type vocabulary and preferences for that vault structure
- [ ] `scripts/test-vault.sh deploy <variant>` deep-copies the selected vault to `~/.claude/cyberbrain/test-vault/` and updates `config.json` to point to it
- [ ] `scripts/test-vault.sh reset` restores the active test vault to its initial state from the repo copy
- [ ] `scripts/test-vault.sh list` shows available variants with brief descriptions
- [ ] `scripts/test-vault.sh status` shows which variant is currently deployed and whether it has been modified
- [ ] `tests/vaults/README.md` documents each variant's purpose, structure, note count, and which features/tools it is designed to test
- [ ] All vault notes use valid frontmatter with realistic content (not lorem ipsum)
- [ ] No vault variant contains real personal data

### Vault Variant Requirements

#### 1. `empty` — Fresh onboarding
- [ ] Contains only `.obsidian/` directory (no notes, no CLAUDE.md)
- [ ] Tests: `cb_setup` first-run experience, vault discovery via `cb_configure`

#### 2. `para` — PARA methodology vault
- [ ] Folders: `Projects/`, `Areas/`, `Resources/`, `Archive/`
- [ ] 15-20 notes distributed across folders with realistic project/area content
- [ ] CLAUDE.md with PARA-appropriate type vocabulary and folder conventions
- [ ] Tests: `cb_extract` routing into PARA folders, `cb_enrich` across folder types, `cb_restructure folder_hub` within Projects

#### 3. `zettelkasten` — Zettelkasten/atomic notes vault
- [ ] Flat or lightly nested structure with numeric/timestamp-prefixed note filenames
- [ ] 20-25 short atomic notes with extensive `related` frontmatter links
- [ ] CLAUDE.md with Zettelkasten conventions (atomic notes, link-heavy)
- [ ] Tests: `cb_restructure` grouping and hub creation, `cb_recall` across a dense link network, relation-based discovery

#### 4. `mature` — Fully populated vault covering all feature surfaces
- [ ] 40-50 notes across multiple folders
- [ ] Mix of all 4 beat types (decision, insight, problem, reference)
- [ ] Working memory notes with `cb_ephemeral: true` and `cb_review_after` dates (some past-due, some future)
- [ ] Notes with `cb_lock: true` (should be skipped by restructure/review)
- [ ] Notes in `.trash/` folder
- [ ] Notes with relations (`related`, `references`, `broader`)
- [ ] Notes with and without complete frontmatter (some missing summary, tags, type)
- [ ] A `Cyberbrain-Log.md` consolidation log with sample entries
- [ ] `wm-recall.jsonl` with sample recall log entries
- [ ] CLAUDE.md with custom preferences set via `cb_configure`
- [ ] Tests: all tools — `cb_enrich` (finds notes missing fields), `cb_review` (finds due WM notes), `cb_restructure` (has mergeable clusters and splittable large notes), `cb_recall` (searches across types), `cb_reindex` (has stale entries to prune)

#### 5. `working-memory` — Working memory lifecycle focus
- [ ] 15-20 notes, all working memory (`cb_ephemeral: true`)
- [ ] Varied `cb_review_after` dates: 5 past-due, 5 due within 7 days, 5 future
- [ ] Varied recall counts in `wm-recall.jsonl` (some heavily recalled, some never)
- [ ] Mix of project-scoped and general-scoped WM notes
- [ ] Tests: `cb_review` decision quality (promote high-recall notes, delete never-recalled past-due notes), working memory TTL behavior

## Implementation Notes

- Vault notes should contain realistic technical content — use topics like software architecture decisions, debugging sessions, API design patterns, tool configurations. Avoid placeholder text.
- Each vault's `.obsidian/` directory needs only the marker (empty directory is sufficient for vault detection). No need to replicate full Obsidian config.
- The `test-vault.sh` script should:
  - Use `cp -r` for deep copy (preserve directory structure)
  - Back up existing `vault_path` in config before overwriting
  - Provide a `teardown` command that restores the original `vault_path`
  - Print clear status messages about what was deployed/reset
- Working memory dates should use relative offsets from the current date when deployed (the deploy script should rewrite `cb_review_after` dates relative to today)
- The `mature` vault should include at least one cluster of 3-4 closely related notes that `cb_restructure` would naturally want to merge, and at least one note >2000 words that would be a split candidate
- Frontmatter `id` fields should use realistic UUIDs
- Tags should be realistic and varied, not uniform
