"""Behavioral checks use synthetic private captures in temporary directories."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/import-quizlet.py"
SPEC = importlib.util.spec_from_file_location("import_quizlet", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class QuizletImportTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.dictionary = self.directory / "greek-russian.json"

    def snapshot(self, identifier, pairs, **overrides):
        value = {"id": identifier, "title": "Synthetic Greek vocabulary",
                 "url": f"https://quizlet.com/{identifier}/", "extracted_at": "2026-01-01T00:00:00Z",
                 "card_count": len(pairs), "extracted_card_count": len(pairs), "complete": True,
                 "cards": [{"row": index, "greek": greek, "russian": russian}
                           for index, (greek, russian) in enumerate(pairs, 1)]} | overrides
        path = self.directory / "quizlet/raw" / f"{identifier}.json"
        MODULE.save(path, value)
        return path

    def run_cli(self, *arguments, success=True):
        result = subprocess.run([sys.executable, str(SCRIPT), "--dictionary", str(self.dictionary),
                                 *map(str, arguments)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if success else 1, result.stderr)
        return json.loads(result.stdout) if success else result.stderr

    def test_dedup_keeps_every_source_row_and_preserves_existing_metadata(self):
        first = self.snapshot("111111111", [("καφές", "кофе"), ("καφές", "кофе"), ("ο καφές", "кофе")])
        self.run_cli(first)
        data = MODULE.read(self.dictionary)
        self.assertEqual(len(data["entries"]), 2)
        data["entries"][0]["editorial_note"] = "Preserve prior review"
        MODULE.save(self.dictionary, data)
        old = deepcopy(data["entries"])
        second = self.snapshot("222222222", [("καφε\u0301ς", "кофе"), ("νερό", "вода")])
        report = self.run_cli(second)
        new = MODULE.read(self.dictionary)
        self.assertEqual(report["new_entries"], 1)
        self.assertEqual(new["summary"]["source_cards"], 5)
        self.assertEqual(new["summary"]["entries"], 3)
        self.assertEqual(new["entries"][0]["editorial_note"], old[0]["editorial_note"])
        self.assertEqual(new["entries"][1], old[1])
        self.assertEqual(len(new["entries"][0]["sources"]), 3)
        self.assertEqual(new["sources"][-1]["learning_context"],
                         {"evidence_level": "introduced", "mastery_assessed": False})
        self.assertTrue(list((self.directory / "quizlet/history").glob("*.json")))
        self.run_cli("--validate-only")

    def test_dry_run_and_repeated_import_do_not_write_files(self):
        capture = self.snapshot("111111111", [("νερό", "вода")])
        before = {p: p.read_bytes() for p in self.directory.rglob("*") if p.is_file()}
        report = self.run_cli(capture, "--dry-run")
        self.assertTrue(report["changed"])
        self.assertFalse(self.dictionary.exists())
        self.assertEqual(before, {p: p.read_bytes() for p in self.directory.rglob("*") if p.is_file()})
        self.run_cli(capture)
        before = {p: p.read_bytes() for p in self.directory.rglob("*") if p.is_file()}
        self.assertFalse(self.run_cli(capture)["changed"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.directory.rglob("*") if p.is_file()})

    def test_reviewed_correction_preserves_literal_raw_and_is_idempotent(self):
        capture = self.snapshot("111111111", [("μαγειρισσα", "повар")])
        original = capture.read_bytes()
        review = self.directory / "review.json"
        MODULE.save(review, [{"set_id": "111111111", "row": 1, "field": "greek",
                              "original": "μαγειρισσα", "corrected": "μαγείρισσα",
                              "reason": "Reviewed stress correction"}])
        self.run_cli(capture, "--corrections", review)
        entry = MODULE.read(self.dictionary)["entries"][0]
        self.assertEqual(entry["greek"], "μαγείρισσα")
        self.assertEqual(entry["corrections"][0]["original"], "μαγειρισσα")
        self.assertEqual(entry["corrections"][0]["source_set_id"], "111111111")
        self.assertEqual(capture.read_bytes(), original)
        self.assertFalse(self.run_cli(capture, "--corrections", review)["changed"])
        self.run_cli("--validate-only")

    def test_rejects_partial_capture_and_changed_previously_imported_set(self):
        partial = self.snapshot("111111111", [("νερό", "вода")], card_count=2)
        self.assertIn("incomplete", self.run_cli(partial, success=False))
        self.assertFalse(self.dictionary.exists())
        capture = self.snapshot("111111111", [("νερό", "вода")])
        self.run_cli(capture)
        previous = self.dictionary.read_bytes()
        self.snapshot("111111111", [("νερό", "вода"), ("καφές", "кофе")])
        self.run_cli(capture, success=False)
        self.assertEqual(self.dictionary.read_bytes(), previous)

    def test_legacy_corrections_and_numeric_translations_remain_reconstructable(self):
        first = self.snapshot("111111111", [("Ενα", "1")])
        self.run_cli(first)
        value = MODULE.read(self.dictionary)
        entry = value["entries"][0]
        entry.update({"greek": "Ένα", "russian": "одно", "numeric_value": 1, "source_translation": "1",
                      "corrections": [{"field": "greek", "original": "Ενα", "corrected": "Ένα",
                                       "reason": "Legacy stress correction"}]})
        MODULE.save(self.dictionary, value)
        raw = MODULE.read(first)
        legacy = {key: raw[key] for key in ("title", "url", "extracted_at")}
        legacy.update({"set_id": raw["id"], "rows": [{"source_row": 1, "sides": [
            {"language": "el", "text": "Ενα"}, {"language": "ru", "text": "1"}]}]})
        MODULE.save(first, legacy)
        second = self.snapshot("222222222", [("Ένα", "одно")])
        self.run_cli(second)
        self.assertEqual(MODULE.read(self.dictionary)["entries"][0]["source_translation"], "1")
        self.run_cli("--validate-only")

    def test_duplicate_or_missing_provenance_is_rejected(self):
        capture = self.snapshot("111111111", [("νερό", "вода")])
        self.run_cli(capture)
        data = MODULE.read(self.dictionary)
        data["entries"][0]["sources"].append(data["entries"][0]["sources"][0].copy())
        MODULE.save(self.dictionary, data)
        self.assertIn("exactly once", self.run_cli("--validate-only", success=False))


if __name__ == "__main__":
    unittest.main()
