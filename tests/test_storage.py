import tempfile
import unittest
from pathlib import Path

from autoanki.storage import append_cards, load_cards


class StorageTests(unittest.TestCase):
    def test_append_cards_creates_list_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cards.json"
            total = append_cards([{"id": "1"}], path)
            self.assertEqual(total, [{"id": "1"}])
            self.assertEqual(load_cards(path), [{"id": "1"}])


if __name__ == "__main__":
    unittest.main()
