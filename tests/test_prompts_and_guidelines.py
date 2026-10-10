import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestPromptsAndGuidelines(unittest.TestCase):
    def test_extractor_agent_prompt(self):
        prompt_path = REPO_ROOT / "prompts" / "extractor_agent.md"
        self.assertTrue(
            prompt_path.exists(), "prompts/extractor_agent.md does not exist"
        )
        content = prompt_path.read_text(encoding="utf-8")

        # Must instruct queue polling via uv run ppq-queue
        self.assertTrue(
            "ppq-queue next --role extractor" in content
            or "queue_manager next --role extractor" in content,
        )
        self.assertIn("uv run ppq-queue next --role extractor", content)
        # Must instruct PDF rendering via uv run ppq-render
        self.assertIn("uv run ppq-render", content)
        # Must reference vision slicing prompt
        self.assertIn("vision_slicing.md", content)
        # Must instruct cropping tool via uv run ppq-crop
        self.assertIn("uv run ppq-crop", content)
        # Must specify queue updating command via uv run ppq-queue update
        self.assertIn("uv run ppq-queue update", content)
        # Must specify --extracted-marks flag
        self.assertIn("--extracted-marks", content)
        # Must specify conventional git commit
        self.assertIn("feat(extractor):", content)
        # Direct multimodal LLM in scheduled hourly container (no inner LLM loops)
        self.assertTrue(
            "hourly" in content.lower(),
            "extractor_agent.md must state scheduled hourly execution",
        )
        self.assertTrue(
            "inner llm" in content.lower(),
            "extractor_agent.md must clarify no inner LLM API loops",
        )
        # Must instruct generating Question Packages and question.json
        self.assertTrue(
            "questions/q" in content or "question package" in content.lower(),
            "extractor_agent.md must instruct Question Package generation (questions/q{NN})",
        )
        self.assertIn("question.json", content)
        self.assertIn("manifest.json", content)
        # Must enforce question number invariant / safety buffer
        self.assertTrue(
            "safety buffer" in content.lower() or "question number" in content.lower(),
            "extractor_agent.md must enforce question numeral safety buffer",
        )

    def test_vision_slicing_prompt(self):
        prompt_path = REPO_ROOT / "prompts" / "vision_slicing.md"
        self.assertTrue(
            prompt_path.exists(), "prompts/vision_slicing.md does not exist"
        )
        content = prompt_path.read_text(encoding="utf-8")

        # Must specify normalized coordinates 0-1000
        self.assertIn("1000", content)
        # Must mention excising dotted or ruled answer lines
        self.assertTrue(
            "dotted" in content.lower()
            or "ruled" in content.lower()
            or "answer workspace" in content.lower(),
            "Prompt must mention excising dotted/ruled answer workspace lines",
        )
        # Must isolate preambles from question parts
        self.assertIn("preamble", content.lower())
        self.assertTrue("subpart" in content.lower() or "part" in content.lower())
        self.assertIn("Isolate Question Preambles from Question Parts", content)
        # Must mandate question number invariant and upward safety buffer (at least 15 units / px)
        self.assertTrue(
            "question 1" in content.lower()
            or "question number" in content.lower()
            or "numeral" in content.lower(),
            "vision_slicing.md must reference question numbers / numerals",
        )
        self.assertTrue(
            any(
                k in content.lower()
                for k in [
                    "safety buffer",
                    "upward buffer",
                    "15 normalized",
                    "15 units",
                    "15px",
                    "15 px",
                ]
            ),
            "vision_slicing.md must mandate upward safety buffer of at least 15 units/px for question numerals",
        )
        # Must document Question Package output expectations
        self.assertTrue(
            "question package" in content.lower() or "decoupled" in content.lower(),
            "vision_slicing.md must document Question Package expectations",
        )
        # Must return valid JSON schema example
        json_matches = re.findall(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
        self.assertTrue(
            len(json_matches) > 0,
            "vision_slicing.md should have a JSON schema example block",
        )
        # Ensure the schema block is valid JSON
        parsed = json.loads(json_matches[0])
        self.assertIn("items", parsed)

    def test_verifier_agent_prompt(self):
        prompt_path = REPO_ROOT / "prompts" / "verifier_agent.md"
        self.assertTrue(
            prompt_path.exists(), "prompts/verifier_agent.md does not exist"
        )
        content = prompt_path.read_text(encoding="utf-8")

        # Must specify queue polling for verifier role via uv run ppq-queue
        self.assertTrue(
            "ppq-queue next --role verifier" in content
            or "queue_manager next --role verifier" in content,
        )
        self.assertIn("uv run ppq-queue next --role verifier", content)
        # Scheduled hourly execution
        self.assertTrue(
            "hourly" in content.lower(),
            "verifier_agent.md must state scheduled hourly execution",
        )
        # Mark-sum invariant verification
        self.assertTrue("mark" in content.lower() and "invariant" in content.lower())
        # Visual audit against source pages
        self.assertTrue("page" in content.lower() and "audit" in content.lower())
        # Clipping checks and question number visibility (especially question 1)
        self.assertIn("clipping", content.lower())
        self.assertTrue(
            "question 1" in content.lower() or "question number" in content.lower(),
            "verifier_agent.md must audit question number visibility (especially question 1)",
        )
        # Question package and question.json integrity
        self.assertTrue(
            "question package" in content.lower() or "questions/q" in content,
            "verifier_agent.md must inspect Question Packages",
        )
        self.assertIn("question.json", content)
        # Autonomous repair loop via uv run ppq-crop
        self.assertTrue(
            "repair" in content.lower()
            or "crop_slices" in content
            or "ppq-crop" in content
        )
        self.assertIn("uv run ppq-crop", content)
        # Updating queue status to verified or needs_rework via uv run ppq-queue update
        self.assertIn("verified", content)
        self.assertNotIn('"approved"', content)
        self.assertNotIn("subpart", content.lower())
        self.assertIn("needs_rework", content)
        self.assertIn("uv run ppq-queue update", content)
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
        self.assertIn("Question Package", content)
        self.assertIn("Question Part Image", content)
        self.assertIn("Composite Question Image", content)
        self.assertIn("Full-Width Crop", content)
        self.assertIn("Answer Workspace", content)
        self.assertIn("Processing Queue", content)

        # Question packages layout and question.json
        self.assertTrue(
            "questions/q" in content or "question package" in content.lower(),
            "AGENTS.md must document Question Packages",
        )
        self.assertIn("question.json", content)

        # Question numeral safety invariant
        self.assertTrue(
            "safety buffer" in content.lower()
            or "question number" in content.lower()
            or "numeral" in content.lower(),
            "AGENTS.md must reference question number safety buffer or invariant",
        )

        # CLI Tooling references
        self.assertIn("pdf_to_images", content)
        self.assertIn("crop_slices", content)
        self.assertIn("queue_manager", content)
        self.assertIn("queue_manager show --id", content)

        # Documentation synchronization rule
        self.assertTrue(
            "continuous documentation synchronization" in content.lower()
            or "documentation synchronization" in content.lower(),
            "AGENTS.md must mandate continuous documentation synchronization",
        )

        # Conventional commits
        self.assertIn("feat(extractor):", content)
        self.assertIn("feat(verifier):", content)

    def test_glossary_forbidden_terms_absent(self):
        """Ensure prompts do not use terms forbidden by GLOSSARY.md."""
        forbidden_map = {
            "subpart snippet": "Question Part Image",
            "partial crop": "Question Part Image",
            "merged image": "Composite Question Image",
            "stitched page": "Composite Question Image",
            "tight box": "Full-Width Crop",
            "arbitrary crop": "Full-Width Crop",
            "dead zone": "Answer Workspace",
            "job table": "Processing Queue",
            "database queue": "Processing Queue",
        }
        for filename in [
            "vision_slicing.md",
            "extractor_agent.md",
            "verifier_agent.md",
        ]:
            prompt_file = REPO_ROOT / "prompts" / filename
            content = prompt_file.read_text(encoding="utf-8").lower()
            for forbidden, preferred in forbidden_map.items():
                self.assertNotIn(
                    forbidden,
                    content,
                    f"Prompt {filename} contains forbidden term '{forbidden}'. Use '{preferred}' instead.",
                )

    def test_prompts_require_uv_run_workflow(self):
        """Ensure all prompt templates use canonical 'uv run' commands exclusively."""
        for filename in [
            "extractor_agent.md",
            "verifier_agent.md",
            "vision_slicing.md",
        ]:
            prompt_file = REPO_ROOT / "prompts" / filename
            content = prompt_file.read_text(encoding="utf-8")
            # Must not use bare 'python3 -m tools.' in bash command blocks
            self.assertNotIn(
                "python3 -m tools.",
                content,
                f"Prompt {filename} contains bare 'python3 -m tools.' invocation. Use canonical 'uv run' command instead.",
            )


if __name__ == "__main__":
    unittest.main()
