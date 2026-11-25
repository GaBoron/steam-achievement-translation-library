import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workflow-scripts"))
from steam_schema import language_coverage


class LanguageCoverageTests(unittest.TestCase):
    def test_optional_fields_and_incomplete_translations_are_checked_independently(self):
        rows = [
            {"api_name": "complete", "english_name": "Name", "schinese_name": "名称", "english_description": "", "schinese_description": ""},
            {"api_name": "missing_description", "english_name": "Name", "schinese_name": "名称", "english_description": "Description", "schinese_description": " "},
            {"api_name": "missing_name", "english_name": "Name", "schinese_name": "", "english_description": "", "schinese_description": ""},
        ]
        coverage, missing = language_coverage(rows, ["english", "schinese"])
        self.assertEqual(coverage, {"english": 3, "schinese": 1})
        self.assertEqual(missing, {"english": [], "schinese": ["missing_description", "missing_name"]})


if __name__ == "__main__":
    unittest.main()
