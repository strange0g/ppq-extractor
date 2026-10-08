import json
import re
from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent

class TestPromptsAndGuidelines(unittest.TestCase):
    def test_extractor_agent_prompt(self):
        prompt_path = REPO_ROOT / "prompts" / "extractor_agent.md"
        self.assertTrue(prompt_path.exists(), "prompts/extractor_agent.md does not exist")
        content = prompt_path.read_text(encoding="utf-8")

        # Must instruct queue polling via queue_manager CLI
        self.assertIn("queue_manager next --role extractor", content)
        # Must instruct PDF rendering via pdf_to_images tool
        self.assertIn("pdf_to_images", content)
        # Must reference vision slicing prompt
        self.assertIn("vision_slicing.md", content)
        # Must instruct cropping tool via crop_slices
        self.assertIn("crop_slices", content)
        # Must specify queue updating command
        self.assertIn("queue_manager update", content)
        # Must specify conventional git commit
        self.assertIn("feat(extractor):", content)

    def test_vision_slicing_prompt(self):
        prompt_path = REPO_ROOT / "prompts" / "vision_slicing.md"
        self.assertTrue(prompt_path.exists(), "prompts/vision_slicing.md does not exist")
        content = prompt_path.read_text(encoding="utf-8")

        # Must specify normalized coordinates 0-1000
        self.assertIn("1000", content)
        # Must mention excising dotted or ruled answer lines
        self.assertTrue(
            "dotted" in content.lower() or "ruled" in content.lower() or "answer workspace" in content.lower(),
            "Prompt must mention excising dotted/ruled answer workspace lines"
        )
        # Must isolate preambles from subparts
        self.assertIn("preamble", content.lower())
        self.assertTrue("subpart" in content.lower() or "part" in content.lower())
        # Must return valid JSON schema example
        json_matches = re.findall(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
        self.assertTrue(len(json_matches) > 0, "vision_slicing.md should have a JSON schema example block")
        # Ensure the schema block is valid JSON
        parsed = json.loads(json_matches[0])
        self.assertIn("items", parsed)

    def test_verifier_agent_prompt(self):
        prompt_path = REPO_ROOT / "prompts" / "verifier_agent.md"
        self.assertTrue(prompt_path.exists(), "prompts/verifier_agent.md does not exist")
        content = prompt_path.read_text(encoding="utf-8")

        # Must specify queue polling for verifier role
        self.assertIn("queue_manager next --role verifier", content)
        # Mark-sum invariant verification
        self.assertTrue("mark" in content.lower() and "invariant" in content.lower())
        # Visual audit against source pages
        self.assertTrue("page" in content.lower() and "audit" in content.lower())
        # Clipping checks
        self.assertIn("clipping", content.lower())
        # Autonomous repair loop
        self.assertTrue("repair" in content.lower() or "crop_slices" in content)
        # Updating queue status to verified or needs_rework
        self.assertIn("verified", content)
        self.assertIn("needs_rework", content)
        self.assertIn("queue_manager update", content)
        # Git commit convention
        self.assertIn("feat(verifier):", content)

    def test_agents_markdown_guidelines(self):
        agents_path = REPO_ROOT / "AGENTS.md"
        self.assertTrue(agents_path.exists(), "AGENTS.md does not exist")
        content = agents_path.read_text(encoding="utf-8")

        # Preserves existing agent skills sections
        self.assertIn("## Agent skills", content)
        self.assertIn("### Issue tracker", content)
        self.assertIn("### Triage labels", content)
        self.assertIn("### Domain docs", content)

        # Pipeline roles
        self.assertIn("Extractor Agent", content)
        self.assertIn("Verifier Agent", content)

        # Domain grounding
        self.assertIn("GLOSSARY.md", content)

        # CLI Tooling references
        self.assertIn("pdf_to_images", content)
        self.assertIn("crop_slices", content)
        self.assertIn("queue_manager", content)

        # Conventional commits
        self.assertIn("feat(extractor):", content)
        self.assertIn("feat(verifier):", content)

if __name__ == "__main__":
    unittest.main()
