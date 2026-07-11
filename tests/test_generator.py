import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autoanki.generator import (
    OpenRouterCardGenerator,
    card_schema,
    list_provider_models,
    load_custom_prompt,
    load_dotenv,
    provider_status,
    save_custom_prompt,
    set_provider_model,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class GeneratorTests(unittest.TestCase):
    def test_dotenv_loader_accepts_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_bytes("\ufeffOPENROUTER_API_KEY=test-key\n".encode("utf-8"))
            with patch.dict(os.environ, {}, clear=True):
                load_dotenv(path)
                self.assertEqual(os.environ["OPENROUTER_API_KEY"], "test-key")

    def test_payload_uses_configured_gemini_model(self):
        with patch.dict(os.environ, {"AUTOANKI_TARGET_CARD_COUNT": "5"}, clear=True):
            generator = OpenRouterCardGenerator(api_key="test-key", model="google/gemini-3.5-flash")
            payload = generator._openai_compatible_payload({"text": "Bode note", "image_b64": None}, ["concept"])
            self.assertEqual(payload["model"], "google/gemini-3.5-flash")
            self.assertEqual(payload["response_format"]["type"], "json_schema")
            schema = payload["response_format"]["json_schema"]["schema"]
            self.assertIn("note_to_user", schema["required"])
            self.assertEqual(schema["properties"]["note_to_user"]["type"], "string")
            self.assertEqual(schema["properties"]["cards"]["maxItems"], 5)
            tag_enum = schema["properties"]["cards"]["items"]["properties"]["tags"]["items"]["enum"]
            self.assertEqual(
                tag_enum,
                [
                    "concept",
                    "definition",
                    "formula",
                    "process",
                    "comparison",
                    "example",
                    "mistake",
                    "workflow",
                ],
            )

    def test_card_schema_uses_configured_tags(self):
        with patch.dict(os.environ, {"AUTOANKI_TAGS": "command,workflow"}, clear=True):
            tag_enum = card_schema()["properties"]["cards"]["items"]["properties"]["tags"]["items"]["enum"]
            self.assertEqual(tag_enum, ["command", "workflow"])

    def test_provider_status_marks_active_provider_and_key_state(self):
        with patch.dict(
            os.environ,
            {"AUTOANKI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "test-key"},
            clear=True,
        ):
            rows = {row["name"]: row for row in provider_status()}
            self.assertTrue(rows["anthropic"]["active"])
            self.assertTrue(rows["anthropic"]["key_set"])
            self.assertFalse(rows["openrouter"]["active"])

    def test_set_provider_model_persists_only_provider_and_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("OPENROUTER_API_KEY=secret\nOPENROUTER_MODEL=old-model\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                set_provider_model("openrouter", "google/gemini-3.5-flash", target_card_count=4, path=path)

            text = path.read_text(encoding="utf-8")
            self.assertIn("AUTOANKI_PROVIDER=openrouter", text)
            self.assertIn("OPENROUTER_MODEL=google/gemini-3.5-flash", text)
            self.assertIn("AUTOANKI_TARGET_CARD_COUNT=4", text)
            self.assertIn("OPENROUTER_API_KEY=secret", text)

    def test_custom_prompt_is_persisted_and_appended_after_generic_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "custom_prompt.txt"
            save_custom_prompt("Write concise German cards.", path)
            self.assertEqual(load_custom_prompt(path), "Write concise German cards.")

            with patch.dict(os.environ, {"AUTOANKI_TAGS": "concept"}, clear=True):
                generator = OpenRouterCardGenerator(
                    api_key="test-key",
                    model="test-model",
                    custom_prompt_path=path,
                )
                prompt = generator._system_prompt()

            self.assertIn("You create high-quality Anki cards", prompt)
            self.assertIn("generic output, safety, MathJax, and allowed-tag rules remain authoritative", prompt)
            self.assertIn("Write concise German cards.", prompt)

            save_custom_prompt("", path)
            self.assertFalse(path.exists())

    @patch("autoanki.generator.urllib.request.urlopen")
    def test_list_provider_models_parses_openrouter_models(self, urlopen):
        urlopen.return_value = FakeResponse({"data": [{"id": "z-model"}, {"id": "a-model"}]})
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(list_provider_models("openrouter"), ["a-model", "z-model"])

    @patch("autoanki.generator.urllib.request.urlopen")
    def test_list_provider_models_strips_gemini_prefix_and_filters_generate_content(self, urlopen):
        urlopen.return_value = FakeResponse(
            {
                "models": [
                    {"name": "models/gemini-3.5-flash", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
                ]
            }
        )
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True):
            self.assertEqual(list_provider_models("gemini"), ["gemini-3.5-flash"])


if __name__ == "__main__":
    unittest.main()
