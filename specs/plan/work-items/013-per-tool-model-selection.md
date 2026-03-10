# 013: Per-Tool Model Selection

## Objective
Implement per-tool model configuration so that classification tasks can use cheap models while content generation and quality judging can use stronger models. This is the plumbing that makes quality gates practical — the gate can use a different (potentially stronger) model than the curation tool it's judging.

## Acceptance Criteria
- [ ] Config supports per-tool model overrides: `restructure_model`, `recall_model`, `enrich_model`, `review_model`, `judge_model` (all optional, fall back to global `model`)
- [ ] `backends.py` has a `get_model_for_tool(config, tool_name)` helper
- [ ] Each curation tool resolves its model via the helper, not by reading `config["model"]` directly
- [ ] `judge_model` is used by the quality gate infrastructure (009) when specified
- [ ] `cb_configure` can read/write the new model keys
- [ ] `cb_status` reports per-tool model configuration
- [ ] Config validation accepts the new keys without error
- [ ] Existing tests pass; new tests cover model override resolution

## File Scope
- `extractors/config.py` (modify) — no validation changes needed (config is a plain dict)
- `extractors/backends.py` (modify) — add `get_model_for_tool()` helper
- `mcp/tools/restructure.py` (modify) — use `get_model_for_tool(config, "restructure")`
- `mcp/tools/recall.py` (modify) — use `get_model_for_tool(config, "recall")`
- `mcp/tools/enrich.py` (modify) — use `get_model_for_tool(config, "enrich")`
- `mcp/tools/review.py` (modify) — use `get_model_for_tool(config, "review")`
- `extractors/quality_gate.py` (modify) — use `get_model_for_tool(config, "judge")`
- `mcp/tools/manage.py` (modify) — cb_configure and cb_status for new keys
- `tests/test_backends.py` (modify) — model override resolution tests
- `tests/test_manage_tool.py` (modify) — config key tests

## Dependencies
- Depends on: 009 (quality gate uses judge_model)
- Blocks: none

## Implementation Notes
The implementation is straightforward plumbing:

```python
def get_model_for_tool(config: dict, tool: str) -> str:
    tool_key = f"{tool}_model"
    return config.get(tool_key, config.get("model", "claude-haiku-4-5"))
```

Each tool already calls `call_model(system_prompt, user_message, config)`. The change is to create a modified config with the resolved model before calling:

```python
tool_config = dict(config)
tool_config["model"] = get_model_for_tool(config, "restructure")
raw = call_model(system_prompt, user_message, tool_config)
```

This is the same pattern the evaluate framework uses for variant overrides.

For the restructure pipeline specifically, if the decision/generation phases are separated, they could use different models: haiku for decision (classification), sonnet for generation (content). But this work item just provides the plumbing — the actual model assignments are determined by quality data from 010.

## Complexity
Medium
