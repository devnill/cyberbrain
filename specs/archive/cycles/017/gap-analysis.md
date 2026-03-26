# Gap Analysis — Cycle 017

## Verdict: 3 gaps. 0 Critical, 1 Significant, 2 Minor.

## Missing Requirements
None.

## Missing Infrastructure

### MI1: Design tensions T5, T6, T7 not marked resolved in architecture.md
- **File**: `specs/plan/architecture.md` (lines 454-464)
- **Issue**: WI-086/087/088 resolved T5 (hook/MCP divergence), T6 (search cache), T7 (relation vocabulary) but none are marked ~~[RESOLVED]~~ in the doc.
- **Severity**: Minor
- **Recommendation**: Trivial doc update.

## Implicit Requirements

### IR1: _write_beats_and_log is residual orchestration duplicate (Significant)
- **File**: `src/cyberbrain/extractors/extract_beats.py:398`
- **Issue**: WI-088 created run_extraction() for shared orchestration, but _write_beats_and_log() remains as a second orchestration path for --beats-json CLI mode. It duplicates the beat-writing loop, autofile fallback, journal, and run log — the same sequence run_extraction() implements. Any future change to these behaviors must be made in two places.
- **Severity**: Significant — WI-088's stated goal (eliminate duplication) is only partially achieved.
- **Fix**: Add optional `beats` parameter to run_extraction(), skip LLM extraction when provided, delete _write_beats_and_log, update --beats-json dispatch.

### IR2: Config docs incomplete vs TypedDict
- **File**: CLAUDE.md, specs/plan/architecture.md
- **Issue**: CyberbrainConfig TypedDict has 32 fields; CLAUDE.md shows 13 in example, architecture.md lists 25. Missing: autofile_model, index_refresh_interval, uncertain_filing_behavior, uncertain_filing_threshold, ollama_url.
- **Severity**: Minor — TypedDict is canonical and referenced.
- **Recommendation**: Defer to doc pass.

_Note: Gap-analyst agent exhausted turn limit. File written by coordinator._
