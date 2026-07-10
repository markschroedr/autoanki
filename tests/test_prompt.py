import unittest
from pathlib import Path


class PromptTests(unittest.TestCase):
    def test_prompt_contains_card_quality_rules(self):
        prompt = Path("autoanki/system_prompt.txt").read_text(encoding="utf-8")
        for phrase in [
            "Stay close to the input",
            "Do not invent new cases",
            "Cloze atomicity",
            "Anti-duplication",
            "Use neutral wording",
            "topic-agnostic",
            "practical workflow or command",
            "terminal commands",
            "workflow",
            "mistake",
        ]:
            self.assertIn(phrase, prompt)
        self.assertNotIn("control engineering", prompt)
        self.assertNotIn("bode", prompt.lower())


if __name__ == "__main__":
    unittest.main()
