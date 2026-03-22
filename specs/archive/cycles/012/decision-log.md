# Decision Log — Cycle 012

## Decisions from Cycles 10-11

### D1: ruff + basedpyright as the quality tooling stack
Research evaluated ruff vs alternatives and mypy vs pyright vs basedpyright. Decision: ruff (de facto standard) + basedpyright (faster, stricter defaults, pyproject.toml config). Both configured in basic mode with targeted ignores.

### D2: Per-file F401 ignores for re-export hubs
Global F401 ignore was rejected by code review (too broad). Per-file ignores on extract_beats.py and shared.py are the correct pattern for re-export modules.

### D3: restructure.py phase-based decomposition
2832-line file decomposed into 11 files by pipeline phase (collect, cluster, cache, audit, decide, generate, execute, format, utils, pipeline, __init__). Phase-based split chosen over horizontal (layer) or feature (vertical) alternatives.

### D4: shared.py direct imports
shared.py converted from importing via extract_beats re-export hub to direct imports from source modules. This was the prerequisite for removing conftest.py sys.modules mock injection.

### D5: Exception handler documentation over narrowing
For ambiguous cases, documenting `# intentional:` comments was preferred over potentially incorrect narrowing. ~10 handlers narrowed where unambiguous; 40+ documented.

### D6: Light-touch test cleanup over full rewrite
sys.modules patterns in 10 test files were documented and consolidated (helper function, consistent patterns) rather than fully rewritten. Full elimination deferred.

### D7: pre-commit with ruff hooks
Standard ruff-pre-commit integration. UP038 added to global ignore because it requires --unsafe-fixes for some cases.

## Open Questions
- G3: Should CI/CD be added? (No CI exists currently)
- G4: CLAUDE.md references stale file paths after restructure decomposition
