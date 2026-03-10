# 009: Quality Gate Infrastructure

## Objective
Build reusable infrastructure for LLM-as-judge quality gates that curation tools can invoke after producing output. When a cheap model produces output, the gate evaluates it and either accepts, retries with adjusted parameters, or surfaces uncertainty to the user. This makes cheap models viable for curation by catching their failures automatically.

## Acceptance Criteria
- [ ] A `quality_gate()` function exists that accepts raw LLM output + context and returns a pass/fail/uncertain verdict with rationale
- [ ] The gate uses a configurable judge (defaults to the same model; can be overridden to a stronger model)
- [ ] On "fail" verdict, the gate can trigger a retry with a different model or adjusted prompt (caller controls retry policy)
- [ ] On "uncertain" verdict, the gate returns the uncertainty to the caller for human-in-the-loop surfacing
- [ ] The gate prompt is operation-aware: it knows whether it's judging a restructure merge, an enrichment classification, or a review decision
- [ ] Gate results are logged (not persisted to vault — logged to stderr or runs log for debugging)
- [ ] Test coverage for the gate function with mocked LLM calls

## File Scope
- `extractors/quality_gate.py` (create) — quality gate function, verdict dataclass, retry logic
- `prompts/quality-gate-system.md` (create) — judge prompt template with operation-type placeholders
- `tests/test_quality_gate.py` (create) — tests for gate verdicts, retry, logging
- `extractors/backends.py` (modify) — add optional `judge_model` resolution (if config has `judge_model`, use it; else fall back to `model`)

## Dependencies
- Depends on: none
- Blocks: 010, 011, 012

## Implementation Notes
The quality gate pattern:

```python
@dataclass
class GateVerdict:
    passed: bool
    confidence: float  # 0.0-1.0
    rationale: str
    suggest_retry: bool = False
    suggested_model: str = ""  # if retry recommended with stronger model

def quality_gate(
    operation: str,  # "restructure_merge", "enrich", "review", etc.
    input_context: str,  # what was given to the curation model
    output: str,  # what the curation model produced
    config: dict,
) -> GateVerdict:
```

The prompt template should be parameterized by operation type. Each curation tool defines what "good" looks like for its operation in the prompt context.

Key design: the gate is a function, not a tool. It's called internally by curation tools. The user never interacts with it directly — they see its effects when a tool says "I'm not confident about this merge — here's what I'd do, should I proceed?"

For `backends.py`: add a `get_judge_model(config)` helper that returns `config.get("judge_model", config.get("model"))`. This is lighter than the full per-tool model selection (007) — it's just a single override for the judge.

## Complexity
Medium
