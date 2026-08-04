import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class RuntimeMetadataTests(unittest.TestCase):
    def test_package_selects_python_314(self):
        self.assertEqual((ROOT / ".python-version").read_text().strip(), "3.14")

    def test_dependencies_are_limited_to_sublime_4205_or_newer(self):
        metadata = json.loads((ROOT / "dependencies.json").read_text())
        self.assertEqual(set(metadata), {"*"})
        self.assertEqual(set(metadata["*"]), {">=4205"})
        self.assertEqual(
            metadata["*"][">=4205"],
            ["requests", "mdpopups", "typing_extensions", "llm_runner"],
        )


if __name__ == "__main__":
    unittest.main()
