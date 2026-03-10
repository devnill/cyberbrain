# 019: Documentation Sync

## Objective
Update all stale documentation artifacts to match the current implementation. This addresses 9 spec-adherence findings (D1-D9), 3 gap-analysis findings (II1-II3), and incremental review findings 010-M2 and 013-M3.

## Acceptance Criteria
- [ ] `specs/plan/architecture.md` component map includes `quality_gate.py` entry (D1)
- [ ] `specs/plan/architecture.md` prompt count updated from 19 to correct number (D2)
- [ ] `specs/plan/architecture.md` config field listing includes: `quality_gate_enabled`, `restructure_model`, `recall_model`, `enrich_model`, `review_model`, `judge_model` (D7/II1) — note: `quality_gate_threshold` excluded per WI-014 removal
- [ ] `specs/plan/architecture.md` prompt variable table updated for `enrich-user.md` and `review-user.md` (D5)
- [ ] `specs/plan/architecture.md` prompt families table includes Synthesis, Quality Gate, and Evaluate families
- [ ] `specs/plan/architecture.md` design tension T2 marked as resolved by WI-013 (D9)
- [ ] `specs/plan/architecture.md` env var stripping section lists all 5 vars including `CLAUDE_CODE_SESSION_ACCESS_TOKEN` (D8/II3)
- [ ] `specs/steering/constraints.md` constraint #8 lists all 5 env vars (D8/II3)
- [ ] `CLAUDE.md` env var stripping section lists all 5 vars (II3)
- [ ] `specs/plan/modules/backends.md` includes `get_model_for_tool` and `get_judge_model` in Provides section (D4)
- [ ] `specs/plan/modules/mcp-tools.md` `_synthesize_recall` signature updated to 4 params (D3)
- [ ] `specs/plan/modules/mcp-tools.md` removes incorrect `ruamel.yaml` reference for `cb_enrich` (D6)
- [ ] `specs/plan/modules/prompts.md` file count and families updated (II2)
- [ ] All documentation changes are factual corrections — no code changes

## File Scope
- `specs/plan/architecture.md` (modify) — D1, D2, D5, D7, D8, D9, II1
- `specs/steering/constraints.md` (modify) — D8/II3
- `CLAUDE.md` (modify) — II3
- `specs/plan/modules/backends.md` (modify) — D4
- `specs/plan/modules/mcp-tools.md` (modify) — D3, D6
- `specs/plan/modules/prompts.md` (modify) — II2

## Dependencies
- Depends on: 014 (threshold removal affects which config keys to document)
- Blocks: none

## Implementation Notes
This is documentation-only. No code changes. Each change is a factual correction to match existing implementation.

For T2 resolution (D9), update `architecture.md:435-438`:
```markdown
### T2: Single Model vs Per-Task Model Selection ~~[RESOLVED]~~

Resolved by WI-013. `get_model_for_tool(config, tool)` provides per-tool model selection via `{tool}_model` config keys. All curation tools resolve their model through this helper. The default remains the global `config["model"]`.
```

For the component map (D1), add after the search index entry:
```markdown
| **Quality gate** | `extractors/quality_gate.py` | LLM-as-judge quality gate for curation tool output validation |
```

## Complexity
Medium (many files, each change is small)
