import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflow-scripts"))

import index_maintenance


def index_with(*entries: dict) -> dict:
    return {"entries": list(entries)}


def single_entry(game_id: str) -> dict:
    return {
        "game_id": game_id,
        "schema_file": f"files/{game_id}/UserGameStatsSchema_{game_id}.bin",
    }


def multi_entry(game_id: str) -> dict:
    primary = f"files/{game_id}/UserGameStatsSchema_{game_id}.bin"
    variant = f"files/{game_id}/clean/UserGameStatsSchema_{game_id}.bin"
    return {
        "game_id": game_id,
        "schema_file": primary,
        "schema_files": [
            {"variant_id": "default", "primary": True, "schema_file": primary},
            {"variant_id": "clean", "primary": False, "schema_file": variant},
        ],
    }


class IndexMaintenanceTests(unittest.TestCase):
    def test_removed_single_file_entry_deletes_schema_and_empty_game_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema = root / "files" / "123" / "UserGameStatsSchema_123.bin"
            schema.parent.mkdir(parents=True)
            schema.write_bytes(b"schema")

            removed = index_maintenance.remove_deleted_entry_files(
                root,
                index_with(single_entry("123")),
                index_with(),
            )

            self.assertEqual(("files/123/UserGameStatsSchema_123.bin",), removed)
            self.assertFalse(schema.exists())
            self.assertFalse(schema.parent.exists())

    def test_removed_multi_file_entry_deletes_every_declared_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = root / "files" / "456" / "UserGameStatsSchema_456.bin"
            variant = root / "files" / "456" / "clean" / "UserGameStatsSchema_456.bin"
            primary.parent.mkdir(parents=True)
            variant.parent.mkdir(parents=True)
            primary.write_bytes(b"primary")
            variant.write_bytes(b"variant")

            removed = index_maintenance.remove_deleted_entry_files(
                root,
                index_with(multi_entry("456")),
                index_with(),
            )

            self.assertEqual(
                (
                    "files/456/UserGameStatsSchema_456.bin",
                    "files/456/clean/UserGameStatsSchema_456.bin",
                ),
                removed,
            )
            self.assertFalse((root / "files" / "456").exists())

    def test_retained_entry_does_not_delete_its_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema = root / "files" / "123" / "UserGameStatsSchema_123.bin"
            schema.parent.mkdir(parents=True)
            schema.write_bytes(b"schema")
            entry = single_entry("123")

            removed = index_maintenance.remove_deleted_entry_files(
                root,
                index_with(entry),
                index_with(entry),
            )

            self.assertEqual((), removed)
            self.assertTrue(schema.is_file())

    def test_removed_entry_skips_schema_that_is_already_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            removed = index_maintenance.remove_deleted_entry_files(
                Path(tmp),
                index_with(single_entry("123")),
                index_with(),
            )

            self.assertEqual((), removed)

    def test_removed_entry_rejects_noncanonical_path(self) -> None:
        entry = single_entry("123")
        entry["schema_file"] = "files/999/UserGameStatsSchema_123.bin"

        with self.assertRaisesRegex(ValueError, "unsafe or non-canonical"):
            index_maintenance.removed_entry_files(index_with(entry), index_with())

    def test_removed_entry_fails_when_undeclared_files_would_be_left_behind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_root = root / "files" / "123"
            game_root.mkdir(parents=True)
            (game_root / "UserGameStatsSchema_123.bin").write_bytes(b"schema")
            extra = game_root / "unexpected.bin"
            extra.write_bytes(b"do not delete silently")

            with self.assertRaisesRegex(RuntimeError, "left undeclared files"):
                index_maintenance.remove_deleted_entry_files(
                    root,
                    index_with(single_entry("123")),
                    index_with(),
                )

            self.assertTrue(extra.is_file())


if __name__ == "__main__":
    unittest.main()
