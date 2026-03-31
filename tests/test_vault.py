"""
test_vault.py — unit tests for vault write abstraction layer

Covers:
- write_vault_note: happy path, path traversal rejection, parent dir creation
- update_vault_note: happy path, path traversal rejection
- move_vault_note: happy path, path traversal rejection (src and dest), parent dir creation
"""

import pytest

from cyberbrain.extractors.vault import (
    move_vault_note,
    update_vault_note,
    write_vault_note,
)


class TestWriteVaultNote:
    def test_happy_path_writes_content(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        note_path = vault / "note.md"
        result = write_vault_note(note_path, "# Hello", str(vault))
        assert result == note_path
        assert note_path.read_text(encoding="utf-8") == "# Hello"

    def test_creates_parent_dirs(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        note_path = vault / "a" / "b" / "note.md"
        write_vault_note(note_path, "content", str(vault))
        assert note_path.exists()
        assert note_path.read_text(encoding="utf-8") == "content"

    def test_path_traversal_rejected(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        outside = tmp_path / "outside" / "note.md"
        with pytest.raises(ValueError):
            write_vault_note(outside, "bad", str(vault))

    def test_path_traversal_via_dotdot_rejected(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        # Construct a path that appears to start inside vault but escapes via ..
        traversal = vault / ".." / "escape.md"
        with pytest.raises(ValueError):
            write_vault_note(traversal, "bad", str(vault))


class TestUpdateVaultNote:
    def test_happy_path_overwrites_content(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        note_path = vault / "note.md"
        note_path.write_text("old content", encoding="utf-8")
        result = update_vault_note(note_path, "new content", str(vault))
        assert result == note_path
        assert note_path.read_text(encoding="utf-8") == "new content"

    def test_path_traversal_rejected(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        outside = tmp_path / "outside.md"
        with pytest.raises(ValueError):
            update_vault_note(outside, "bad", str(vault))

    def test_path_traversal_via_dotdot_rejected(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        traversal = vault / ".." / "escape.md"
        with pytest.raises(ValueError):
            update_vault_note(traversal, "bad", str(vault))

    def test_raises_if_note_does_not_exist(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        missing = vault / "nonexistent.md"
        with pytest.raises(FileNotFoundError):
            update_vault_note(missing, "content", str(vault))


class TestMoveVaultNote:
    def test_happy_path_moves_note(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        src = vault / "src.md"
        src.write_text("content", encoding="utf-8")
        dest = vault / "dest.md"
        result = move_vault_note(src, dest, str(vault))
        assert result == dest
        assert dest.read_text(encoding="utf-8") == "content"
        assert not src.exists()

    def test_creates_parent_dirs_for_dest(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        src = vault / "note.md"
        src.write_text("content", encoding="utf-8")
        dest = vault / "sub" / "folder" / "note.md"
        move_vault_note(src, dest, str(vault))
        assert dest.exists()
        assert dest.read_text(encoding="utf-8") == "content"
        assert not src.exists()

    def test_src_path_traversal_rejected(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        outside_src = tmp_path / "outside.md"
        outside_src.write_text("x", encoding="utf-8")
        dest = vault / "dest.md"
        with pytest.raises(ValueError):
            move_vault_note(outside_src, dest, str(vault))

    def test_dest_path_traversal_rejected(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        src = vault / "note.md"
        src.write_text("content", encoding="utf-8")
        outside_dest = tmp_path / "outside.md"
        with pytest.raises(ValueError):
            move_vault_note(src, outside_dest, str(vault))

    def test_dest_dotdot_traversal_rejected(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        src = vault / "note.md"
        src.write_text("content", encoding="utf-8")
        traversal = vault / ".." / "escape.md"
        with pytest.raises(ValueError):
            move_vault_note(src, traversal, str(vault))

    def test_raises_if_src_does_not_exist(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        missing = vault / "nonexistent.md"
        dest = vault / "dest.md"
        with pytest.raises(FileNotFoundError):
            move_vault_note(missing, dest, str(vault))
