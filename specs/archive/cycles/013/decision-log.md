# Decision Log — Cycle 013
## D1: Two Path.home() references kept dynamic
manage.py and backends.py compute paths dynamically at call time because tests monkeypatch Path.home(). state.py constants are import-time computed and can't be redirected by monkeypatch. Both paths are documented.
## D2: extract_beats.py hub eliminated
25 re-exports removed. All callers migrated to direct imports. scripts/import.py rewritten from eb.X pattern to direct module imports. extract_beats.py is now a pure CLI script.
## D3: _dependency_map.py features restored
WI-055/056 features (_REPO_ROOT, scripts/ fallback, absolute path normalization) were lost to worker overwrite in cycle 10. Re-implemented in WI-074.
