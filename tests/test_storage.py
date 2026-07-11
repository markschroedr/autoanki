import tempfile
import unittest
from pathlib import Path

from autoanki.storage import (append_cards, create_stack, delete_stack, load_cards,
                              load_store, rename_stack, select_stack)


class StorageTests(unittest.TestCase):
    def test_append_cards_creates_list_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cards.json"
            total = append_cards([{"id": "1"}], path)
            self.assertEqual(total, [{"id": "1"}])
            self.assertEqual(load_cards(path), [{"id": "1"}])

    def test_stack_crud_and_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cards.json"
            default = load_store(path)["stacks"][0]
            work = create_stack("Work", path)
            append_cards([{"id": "work-1"}], path, work["id"])
            self.assertEqual(load_cards(path), [{"id": "work-1"}])
            select_stack(default["id"], path)
            self.assertEqual(load_cards(path), [])
            renamed = rename_stack(work["id"], "Exams", path)
            self.assertEqual(renamed["id"], work["id"])
            with self.assertRaises(ValueError):
                delete_stack(work["id"], "wrong", path)
            delete_stack(work["id"], "Exams", path)
            with self.assertRaises(ValueError):
                delete_stack(default["id"], "Default", path)

    def test_pending_is_persistent_in_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cards.json"
            store = load_store(path)
            store["stacks"][0]["pending"] = [{"id": "draft"}]
            from autoanki.storage import save_store
            save_store(store, path)
            self.assertEqual(load_store(path)["stacks"][0]["pending"], [{"id": "draft"}])


if __name__ == "__main__":
    unittest.main()
