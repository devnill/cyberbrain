"""
tests/test_repair_vault_schema.py — Tests for scripts/repair_vault_schema.py

Tests cover:
- test_type_correction: beat type values are mapped to entity types
- test_missing_aliases_added: aliases: [] added when absent
- test_created_derived_from_cb_created: created field derived from cb_created
- test_dry_run_no_writes: dry-run mode does not write any files
- test_pytest_artifact_identified: notes whose cwd matches pytest pattern are flagged
"""

import importlib.util
import subprocess
import sys
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Module loading — repair_vault_schema.py lives in scripts/
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "repair_vault_schema", SCRIPTS_DIR / "repair_vault_schema.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load_module()
repair_note = _mod.repair_note
_PYTEST_TMPDIR_PATTERN = _mod._PYTEST_TMPDIR_PATTERN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXED_TODAY = date(2026, 3, 29)


def _make_note(**fields: object) -> str:
    """Build a minimal cyberbrain note with the given frontmatter fields."""
    lines = ["---"]
    # Always include cb_source so it's recognised as a cyberbrain note
    if "cb_source" not in fields:
        fields = {"cb_source": "extract", **fields}
    for key, value in fields.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
        elif value is None:
            lines.append(f"{key}:")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append("# Note body")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# test_type_correction
# ---------------------------------------------------------------------------


class TestTypeCorrection:
    def test_decision_mapped_to_resource(self):
        text = _make_note(type="decision")
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert "type: resource" in repaired
        assert any("decision" in c and "resource" in c for c in changes)

    def test_insight_mapped_to_resource(self):
        text = _make_note(type="insight")
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert "type: resource" in repaired
        assert any("insight" in c and "resource" in c for c in changes)

    def test_problem_mapped_to_note(self):
        text = _make_note(type="problem")
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert "type: note" in repaired
        assert any("problem" in c and "note" in c for c in changes)

    def test_reference_mapped_to_resource(self):
        text = _make_note(type="reference")
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert "type: resource" in repaired
        assert any("reference" in c and "resource" in c for c in changes)

    def test_already_valid_type_unchanged(self):
        text = _make_note(type="resource", aliases=[])
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        # aliases already present, type already valid — no type change
        assert not any("type" in c for c in changes)

    def test_non_cyberbrain_note_skipped(self):
        """Notes without cb_source or cb_created are not processed."""
        text = "---\ntitle: Random Note\ntype: decision\n---\n\n# Body\n"
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert changes == []
        assert repaired == text


# ---------------------------------------------------------------------------
# test_missing_aliases_added
# ---------------------------------------------------------------------------


class TestMissingAliasesAdded:
    def test_aliases_added_when_absent(self):
        text_no_aliases = _make_note()
        repaired, changes = repair_note(text_no_aliases, today=_FIXED_TODAY)
        assert "aliases:" in repaired
        assert any("aliases" in c for c in changes)

    def test_aliases_not_duplicated_when_present(self):
        text = _make_note(aliases=[])
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert not any("aliases" in c for c in changes)

    def test_aliases_with_existing_values_preserved(self):
        text = _make_note(aliases=["my-alias"])
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert not any("aliases" in c for c in changes)
        assert "my-alias" in repaired


# ---------------------------------------------------------------------------
# test_created_derived_from_cb_created
# ---------------------------------------------------------------------------


class TestCreatedDerivedFromCbCreated:
    def test_created_added_from_cb_created_iso_string(self):
        text = _make_note(cb_created="2026-01-15T10:00:00")
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert "created: 2026-01-15" in repaired
        assert any("created" in c and "2026-01-15" in c for c in changes)

    def test_created_not_overwritten_when_present(self):
        text = _make_note(cb_created="2026-01-15T10:00:00", created="2025-12-01")
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        # No change entry should say "created: derived ..."
        assert not any(c.startswith("created:") and "derived" in c for c in changes)
        # Original value preserved
        assert "2025-12-01" in repaired

    def test_updated_added_from_cb_modified(self):
        text = _make_note(
            cb_created="2026-01-15T10:00:00",
            cb_modified="2026-02-20T08:30:00",
        )
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        # ruamel.yaml may quote the date string; check for the date value either way
        assert "2026-02-20" in repaired
        assert any("updated" in c and "2026-02-20" in c for c in changes)

    def test_updated_falls_back_to_cb_created_when_no_cb_modified(self):
        text = _make_note(cb_created="2026-01-15T10:00:00")
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        # ruamel.yaml may quote the date string; check for the date value either way
        assert "2026-01-15" in repaired
        assert any("updated" in c and "2026-01-15" in c for c in changes)

    def test_no_cb_created_no_created_added(self):
        text = "---\ncb_source: extract\ntype: resource\naliases: []\n---\n\n# Body\n"
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert not any("created" in c and "derived" in c for c in changes)


# ---------------------------------------------------------------------------
# test_dry_run_no_writes
# ---------------------------------------------------------------------------


class TestDryRunNoWrites:
    def test_dry_run_does_not_write_files(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test-note.md"
        original = _make_note(type="decision", cb_created="2026-01-10T09:00:00")
        note.write_text(original, encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "repair_vault_schema.py"),
                "--vault-path",
                str(vault),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # File must be unchanged in dry-run
        on_disk = note.read_text(encoding="utf-8")
        assert on_disk == original

    def test_apply_mode_writes_files(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test-note.md"
        original = _make_note(type="decision", cb_created="2026-01-10T09:00:00")
        note.write_text(original, encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "repair_vault_schema.py"),
                "--vault-path",
                str(vault),
                "--apply",
            ],
            capture_output=True,
            text=True,
            input="n\n",  # don't delete test artifacts if prompted
        )
        assert result.returncode == 0

        on_disk = note.read_text(encoding="utf-8")
        assert on_disk != original
        assert "type: resource" in on_disk

    def test_repair_note_does_not_mutate_original(self):
        """repair_note itself is a pure function — original string is unchanged."""
        text = _make_note(type="insight", cb_created="2026-03-01T00:00:00")
        original_text = text
        _repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert text == original_text
        assert changes  # changes were detected

    def test_dry_run_output_shows_counts(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "note.md"
        note.write_text(_make_note(type="decision"), encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "repair_vault_schema.py"),
                "--vault-path",
                str(vault),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = result.stdout
        assert "scanned" in output
        assert "needing repair" in output


# ---------------------------------------------------------------------------
# test_pytest_artifact_identified
# ---------------------------------------------------------------------------


class TestPytestArtifactIdentified:
    def test_pytest_tmpdir_pattern_matches(self):
        assert _PYTEST_TMPDIR_PATTERN.search("/tmp/pytest_worker0/some/path")
        assert _PYTEST_TMPDIR_PATTERN.search("/private/var/folders/pytest-123/test0/")
        assert _PYTEST_TMPDIR_PATTERN.search("/tmp/pytest-of-user/test0/")
        assert _PYTEST_TMPDIR_PATTERN.search("/tmp/pytest_abc123/test0/")
        assert not _PYTEST_TMPDIR_PATTERN.search("/tmp/pytest")
        assert not _PYTEST_TMPDIR_PATTERN.search("/Users/dan/code/my-project")

    def test_artifact_detected_in_dry_run_output(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "artifact.md"
        note.write_text(
            "---\ncb_source: extract\ncwd: /tmp/pytest_worker0/some/path\n---\n\n# Note\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "repair_vault_schema.py"),
                "--vault-path",
                str(vault),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert (
            "Test artifact" in result.stdout or "test artifact" in result.stdout.lower()
        )
        assert "artifact.md" in result.stdout

    def test_artifact_not_deleted_in_dry_run(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "artifact.md"
        note.write_text(
            "---\ncb_source: extract\ncwd: /tmp/pytest_worker0/some/path\n---\n\n# Note\n",
            encoding="utf-8",
        )

        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "repair_vault_schema.py"),
                "--vault-path",
                str(vault),
            ],
            capture_output=True,
            text=True,
        )
        # File must still exist after dry-run
        assert note.exists()

    def test_artifact_prompt_n_does_not_delete(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "artifact.md"
        note.write_text(
            "---\ncb_source: extract\ncwd: /tmp/pytest_worker0/some/path\n---\n\n# Note\n",
            encoding="utf-8",
        )

        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "repair_vault_schema.py"),
                "--vault-path",
                str(vault),
                "--apply",
            ],
            capture_output=True,
            text=True,
            input="n\n",
        )
        # Answered 'n' — file must survive
        assert note.exists()

    def test_normal_cwd_not_flagged_as_artifact(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "normal.md"
        note.write_text(
            "---\ncb_source: extract\ncwd: /Users/dan/code/my-project\n---\n\n# Note\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "repair_vault_schema.py"),
                "--vault-path",
                str(vault),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Should not mention test artifacts
        assert "artifact" not in result.stdout.lower() or "0" in result.stdout


# ---------------------------------------------------------------------------
# Status correction
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# test_durability_added_from_cb_ephemeral
# ---------------------------------------------------------------------------


class TestDurabilityAdded:
    def test_cb_ephemeral_true_gets_working_memory(self):
        text = _make_note(cb_ephemeral="true")
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert "durability: working-memory" in repaired
        assert any("durability" in c and "working-memory" in c for c in changes)

    def test_no_cb_ephemeral_gets_durable(self):
        text = _make_note()
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert "durability: durable" in repaired
        assert any("durability" in c and "durable" in c for c in changes)

    def test_existing_durability_not_modified(self):
        text = _make_note(durability="durable", aliases=[])
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert not any("durability" in c for c in changes)

    def test_cb_ephemeral_true_gets_review_after(self):
        text = _make_note(cb_ephemeral="true")
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        # _FIXED_TODAY = 2026-03-29; +28 days = 2026-04-26
        # ruamel.yaml may quote the date string; check for the value either way
        assert "2026-04-26" in repaired
        assert any("cb_review_after" in c and "2026-04-26" in c for c in changes)

    def test_cb_review_after_not_overwritten(self):
        text = _make_note(cb_ephemeral="true", cb_review_after="2026-05-01")
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert "2026-05-01" in repaired
        assert not any("cb_review_after" in c for c in changes)

    def test_cb_ephemeral_string_false_not_treated_as_ephemeral(self):
        """The string 'false' must not be treated as truthy — durability must be durable."""
        text = _make_note(cb_ephemeral="false")
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert "durability: durable" in repaired
        assert not any("working-memory" in c for c in changes)
        assert not any("cb_review_after" in c for c in changes)

    def test_cb_ephemeral_integer_1_treated_as_ephemeral(self):
        """YAML integer 1 for cb_ephemeral is treated as ephemeral (working-memory)."""
        text = _make_note(cb_ephemeral=1)
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert "durability: working-memory" in repaired
        assert any("working-memory" in c for c in changes)


# ---------------------------------------------------------------------------
# Status correction
# ---------------------------------------------------------------------------


class TestStatusCorrection:
    def test_completed_non_ephemeral_becomes_active(self):
        text = _make_note(status="completed")
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert "status: active" in repaired
        assert any("completed" in c and "active" in c for c in changes)

    def test_completed_ephemeral_expired_becomes_done(self):
        text = _make_note(
            status="completed",
            cb_ephemeral="true",
            cb_review_after="2026-01-01",
        )
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert "status: done" in repaired
        assert any("done" in c for c in changes)

    def test_completed_ephemeral_not_expired_becomes_active(self):
        text = _make_note(
            status="completed",
            cb_ephemeral="true",
            cb_review_after="2030-01-01",
        )
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert "status: active" in repaired

    def test_active_status_unchanged(self):
        text = _make_note(status="active", aliases=[])
        repaired, changes = repair_note(text, today=_FIXED_TODAY)
        assert not any("status" in c for c in changes)
