#!/usr/bin/env python3
"""Deterministic glossary and prompt terminology linter.

Asserts that files under prompts/ adhere to GLOSSARY.md domain language
and do not contain prohibited terms (e.g., 'subpart', 'stem crop', etc.).
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

PROHIBITED_PATTERNS = [
    # (pattern, explanation, replacement)
    (r"\bsubpart\b", "Prohibited term 'subpart'", "Question Part"),
    (r"\bsubparts\b", "Prohibited term 'subparts'", "Question Parts"),
    (r"\bstem crop\b", "Prohibited term 'stem crop'", "Question Preamble Image"),
    (r"\bheader snippet\b", "Prohibited term 'header snippet'", "Question Preamble Image"),
    (r"\bpartial crop\b", "Prohibited term 'partial crop'", "Question Part Image"),
    (r"\bquestion folder\b", "Prohibited term 'question folder'", "Question Package"),
    (r"\bproblem bundle\b", "Prohibited term 'problem bundle'", "Question Package"),
    (r"\bmerged image\b", "Prohibited term 'merged image'", "Composite Question Image"),
    (r"\bstitched page\b", "Prohibited term 'stitched page'", "Composite Question Image"),
    (r"\btight box\b", "Prohibited term 'tight box'", "Full-Width Crop"),
    (r"\bdead zone\b", "Prohibited term 'dead zone'", "Answer Workspace"),
    (r"\bjob table\b", "Prohibited term 'job table'", "Processing Queue"),
]


class TestGlossaryLint(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent
        self.prompts_dir = self.repo_root / "prompts"

    def test_prompts_do_not_contain_prohibited_terms(self):
        """Ensure all prompt files obey GLOSSARY.md terminology prohibitions."""
        self.assertTrue(self.prompts_dir.is_dir(), f"Missing prompts directory: {self.prompts_dir}")

        violations: list[str] = []
        for prompt_file in self.prompts_dir.glob("*.md"):
            content = prompt_file.read_text(encoding="utf-8")
            for pattern, reason, replacement in PROHIBITED_PATTERNS:
                matches = list(re.finditer(pattern, content, flags=re.IGNORECASE))
                for match in matches:
                    # Determine line number
                    line_no = content[: match.start()].count("\n") + 1
                    matched_text = match.group(0)
                    violations.append(
                        f"{prompt_file.name}:{line_no} -> '{matched_text}' ({reason}; prefer '{replacement}')"
                    )

        if violations:
            self.fail(
                "Glossary terminology violations found in prompts:\n"
                + "\n".join(f"  - {v}" for v in violations)
            )


if __name__ == "__main__":
    unittest.main()
