# 007: Per-Tool Model Selection

## Objective
Implement per-tool model configuration so that classification tasks (autofile, enrichment, audit) can use cheap models while content generation tasks (restructure merging, synthesis, hub pages) can use stronger models. Resolve deferred decision D11.

## Acceptance Criteria
- [ ] Config supports per-tool model overrides: `restructure_model`, `recall_model`, `enrich_model`, `review_model` (all optional, fall back to global `model`)
- [ ] `backends.call_model()` accepts a model override parameter
- [ ] Restructure pipeline uses separate models for decision and generation phases (if D10 split is implemented in 004)
- [ ] Quality comparison data (from evaluation tooling) demonstrates that per-tool model selection improves output where it matters without increasing cost where it doesn't
- [ ] Config validation accepts the new keys; `cb_configure` can read/write them; `cb_status` reports them
- [ ] Existing tests pass; new tests cover model override resolution

## File Scope
- `extractors/config.py` (modify) — new config keys, model resolution logic
- `extractors/backends.py` (modify) — model override parameter in call_model
- `mcp/tools/restructure.py` (modify) — per-phase model selection
- `mcp/tools/recall.py` (modify) — synthesis model selection
- `mcp/tools/enrich.py` (modify) — enrichment model selection
- `mcp/tools/review.py` (modify) — review model selection
- `mcp/tools/manage.py` (modify) — cb_configure and cb_status for new keys
- `tests/test_backends.py` (modify) — model override tests
- `tests/test_manage_tool.py` (modify) — config key tests

## Dependencies
- Depends on: 004 (restructure quality work determines which phases need stronger models), 005 (RAG work determines synthesis model needs)
- Blocks: none

## Implementation Notes
This is straightforward plumbing once the quality data from 004 and 005 demonstrates which tasks benefit from stronger models. The implementation pattern:

```python
# config resolution
def get_model_for_tool(config: dict, tool: str) -> str:
    tool_key = f"{tool}_model"
    return config.get(tool_key, config.get("model", "claude-haiku-4-5"))
```

The harder question — which tasks need which models — is answered by work items 004 and 005 using the evaluation tooling from 001. This work item just implements the configuration mechanism.

If D10 (decision/generation split) is implemented in 004, the restructure pipeline will have two distinct phases that naturally want different models: a cheap model for action classification and a strong model for content generation.

For ollama users, this matters especially: a 7B model may be adequate for routing/classification but produce poor restructure output.

## Complexity
Medium
