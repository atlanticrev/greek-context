"""Exercise configurable local audio tools without synthesis or private data."""

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


SYNTHESIS = module("synthesis_portability", "synthesize-role-dialogues.py")
PRACTICE = module("practice_portability", "greek-listening-practice.py")


class ListeningPortabilityTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.bin = self.directory / "bin"
        self.bin.mkdir()

    def executable(self, name, directory=None):
        path = (directory or self.bin) / name
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
        return path

    def test_path_discovery_and_explicit_model_work_outside_homebrew(self):
        ffmpeg = self.executable("ffmpeg")
        whisper = self.executable("whisper-cli")
        model = self.directory / "custom-ggml.bin"
        model.write_bytes(b"synthetic model")
        with patch.dict(os.environ, {"PATH": str(self.bin)}, clear=True):
            tools = SYNTHESIS.resolve_tools(asr_model=model, check_asr=True)
        self.assertEqual(tools, {"ffmpeg": str(ffmpeg), "whisper_cli": str(whisper),
                                 "asr_model": str(model)})

    def test_flags_override_environment_and_environment_overrides_path(self):
        self.executable("ffmpeg")
        configured = self.executable("configured-ffmpeg")
        explicit = self.executable("explicit-ffmpeg")
        whisper = self.executable("configured-whisper")
        model = self.directory / "model.bin"
        model.write_bytes(b"synthetic model")
        environment = {"PATH": str(self.bin), "GREEK_CONTEXT_FFMPEG": str(configured),
                       "GREEK_CONTEXT_WHISPER_CLI": str(whisper), "GREEK_CONTEXT_ASR_MODEL": str(model)}
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(SYNTHESIS.resolve_tools()["ffmpeg"], str(configured))
            tools = SYNTHESIS.resolve_tools(ffmpeg=str(explicit), check_asr=True)
        self.assertEqual(tools, {"ffmpeg": str(explicit), "whisper_cli": str(whisper),
                                 "asr_model": str(model)})

    def test_legacy_fallback_and_unchecked_synthesis_need_no_asr_model(self):
        fallback = self.executable("legacy-ffmpeg")
        with patch.dict(os.environ, {"PATH": str(self.bin / "absent")}, clear=True), \
                patch.object(SYNTHESIS, "LEGACY_FFMPEG", str(fallback)):
            self.assertEqual(SYNTHESIS.resolve_tools(), {"ffmpeg": str(fallback)})

    def test_invalid_config_fails_with_actionable_flags_instead_of_falling_back(self):
        self.executable("ffmpeg")
        self.executable("whisper-cli")
        with patch.dict(os.environ, {"PATH": str(self.bin)}, clear=True):
            with self.assertRaisesRegex(ValueError, "--ffmpeg"):
                SYNTHESIS.resolve_tools(ffmpeg=str(self.directory / "absent"))
            with self.assertRaisesRegex(ValueError, "--asr-model"):
                SYNTHESIS.resolve_tools(asr_model=self.directory / "missing.bin", check_asr=True)

    def test_help_runs_without_optional_python_audio_packages(self):
        result = subprocess.run([sys.executable, "-S", str(ROOT / "scripts/synthesize-role-dialogues.py"),
                                 "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--asr-model", result.stdout)
        self.assertIn("--whisper-cli", result.stdout)

    def test_incompatible_local_service_stops_before_synthesis(self):
        ffmpeg = self.executable("ffmpeg")
        arguments = ["synthesize-role-dialogues.py", str(self.directory / "script.json"),
                     "--ffmpeg", str(ffmpeg), "--ollama-url", "http://127.0.0.1:12345/"]
        stderr = io.StringIO()
        with patch.object(sys, "argv", arguments), \
                patch.object(SYNTHESIS, "load_audio_dependencies"), \
                patch.object(SYNTHESIS, "request_json", return_value={}) as request, \
                patch.object(SYNTHESIS, "render") as render, patch.object(sys, "stderr", stderr):
            with self.assertRaises(SystemExit) as error:
                SYNTHESIS.main()
        self.assertEqual(error.exception.code, 2)
        self.assertIn("LFM speech service", stderr.getvalue())
        self.assertIn("male-greek and female-greek", stderr.getvalue())
        self.assertIn("/v1/audio/speech", stderr.getvalue())
        request.assert_called_once_with("http://127.0.0.1:12345/api/show", {"model": SYNTHESIS.MODEL})
        render.assert_not_called()

    def test_practice_render_forwards_tools_and_keeps_asr_required(self):
        draft_path = self.directory / "draft.json"
        draft_path.write_text("{}")
        (self.directory / "validation.json").write_text("{}")
        draft = {"format": "monologue", "turns": [{"text": "Καλημέρα."}]}

        class CapturedCommand(Exception):
            pass

        with patch.object(PRACTICE, "ROOT", self.directory), \
                patch.object(PRACTICE, "validate", return_value=(draft, {"ok": True})), \
                patch.object(PRACTICE.subprocess, "run", side_effect=CapturedCommand) as run:
            with self.assertRaises(CapturedCommand):
                PRACTICE.render(draft_path, "http://127.0.0.1:12345", "/custom/ffmpeg", "/custom/whisper",
                                Path("/custom/model.bin"))
        command = run.call_args.args[0]
        self.assertIn("--check-asr", command)
        for option, value in [("--ollama-url", "http://127.0.0.1:12345"), ("--ffmpeg", "/custom/ffmpeg"),
                              ("--whisper-cli", "/custom/whisper"), ("--asr-model", "/custom/model.bin")]:
            self.assertEqual(command[command.index(option) + 1], value)
        self.assertEqual(json.loads((self.directory / "script.json").read_text())["format"], "monologue")


if __name__ == "__main__":
    unittest.main()
