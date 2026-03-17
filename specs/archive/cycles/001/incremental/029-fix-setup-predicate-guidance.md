## Verdict: Pass (after rework)

Setup prompt fixed to list only supported predicates. Pre-existing wasDerivedFrom case-comparison bug in vault.py also fixed.

## Critical Findings

### C1: wasDerivedFrom predicate always silently coerced to "related" (pre-existing)
- **File**: `extractors/vault.py:196-198`
- **Issue**: `resolve_relations()` lowercases the predicate before comparing against `VALID_PREDICATES`, but the set contained `"wasDerivedFrom"` (camelCase). The lowercased form `"wasderivedfrom"` never matched.
- **Impact**: Every `wasDerivedFrom` relation emitted by the LLM was silently stored as `"related"`.
- **Resolution**: Lowercased the entry in `VALID_PREDICATES` to `"wasderivedfrom"` so the comparison works correctly. Prompts continue using camelCase for LLM readability; the `.lower()` normalization handles the conversion.

## Significant Findings

None.

## Minor Findings

None.

## Unmet Acceptance Criteria

None — all criteria met after rework.
