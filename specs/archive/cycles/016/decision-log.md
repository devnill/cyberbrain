# Decision Log — Cycle 016

## DL1: ARCHITECTURE.md is the human-facing overview
User decided ARCHITECTURE.md should match reality and not be deprecated. specs/plan/architecture.md remains the decision record. Both are maintained.

## DL2: CyberbrainConfig TypedDict missing from source
Gap analyst discovered that `CyberbrainConfig` TypedDict, documented as created in WI-061, does not exist in source code. Journal notes concurrent worker overwrites during the brrr cycle that required manual restoration. The TypedDict was likely a casualty. This is a pre-existing gap — not a cycle 016 regression.

## Open Questions
- Should CyberbrainConfig TypedDict be recreated? (Candidate for future work item)
- Should install.sh/uninstall.sh references be cleaned from README, or should the scripts be recreated?
