import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def create_dummy_pdf(filename: Path, num_pages: int) -> None:
    page_objs = " ".join([f"{i + 3} 0 R" for i in range(num_pages)])
    catalog = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    pages = f"2 0 obj\n<< /Type /Pages /Kids [{page_objs}] /Count {num_pages} >>\nendobj\n".encode()
    body = [catalog, pages]
    for i in range(num_pages):
        page = f"{i + 3} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n".encode()
        body.append(page)

    header = b"%PDF-1.4\n"
    content = bytearray(header)
    offsets = [0]
    for obj in body:
        offsets.append(len(content))
        content.extend(obj)

    xref_offset = len(content)
    content.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]:
        content.extend(f"{off:010d} 00000 n \n".encode())
    content.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    filename.parent.mkdir(parents=True, exist_ok=True)
    with open(filename, "wb") as f:
        f.write(content)


class TestQueueManagerCLI(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.tmpdir.name)
        self.source_dir = self.test_dir / "9709"
        self.queue_file = self.test_dir / ".pipeline" / "queue.json"

        # Create dummy PDF files
        # 1. Modern Pure 1 paper (2024, write-in, 20 pages, expected marks 75)
        create_dummy_pdf(
            self.source_dir / "2024" / "2024 Nov" / "9709_w24_qp_12.pdf", 20
        )
        # 2. Modern Mechanics paper (2024, write-in, 12 pages, expected marks 50)
        create_dummy_pdf(
            self.source_dir / "2024" / "2024 Nov" / "9709_w24_qp_42.pdf", 12
        )
        # 3. Compact pre-2017 Pure 3 paper (2016, compact, 4 pages, expected marks 75)
        create_dummy_pdf(
            self.source_dir / "2016" / "May_June 2016" / "9709_s16_qp_31.pdf", 4
        )
        # 4. Old single-digit component paper (2001, compact, 4 pages, expected marks 50)
        create_dummy_pdf(self.source_dir / "2001" / "9709_w01_qp_6.pdf", 4)
        # Non-QP PDF that should be ignored
        create_dummy_pdf(
            self.source_dir / "2024" / "2024 Nov" / "9709_w24_ms_12.pdf", 10
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def run_cli(self, args: list[str]) -> subprocess.CompletedProcess:
        cmd = [sys.executable, "-m", "tools.queue_manager"] + args
        env = dict(os.environ)
        repo_root = str(Path(__file__).parent.parent)
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{repo_root}:{existing_pp}" if existing_pp else repo_root
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(self.test_dir),
            env=env,
        )

    def test_scan_discovers_and_populates_metadata(self):
        result = self.run_cli(
            [
                "scan",
                "--source-dir",
                str(self.source_dir),
                "--queue-file",
                str(self.queue_file),
            ]
        )
        self.assertEqual(result.returncode, 0, f"Scan failed: {result.stderr}")
        self.assertTrue(self.queue_file.exists())

        with open(self.queue_file, "r") as f:
            data = json.load(f)

        self.assertEqual(data["version"], "1.0")
        self.assertEqual(data["summary"]["total"], 4)
        self.assertEqual(data["summary"]["unprocessed"], 4)
        self.assertEqual(data["summary"]["extracted"], 0)
        self.assertEqual(data["summary"]["verified"], 0)
        self.assertEqual(data["summary"]["needs_rework"], 0)

        papers_by_id = {p["id"]: p for p in data["papers"]}
        self.assertIn("9709_w24_qp_12", papers_by_id)
        self.assertIn("9709_w24_qp_42", papers_by_id)
        self.assertIn("9709_s16_qp_31", papers_by_id)
        self.assertIn("9709_w01_qp_6", papers_by_id)
        self.assertNotIn("9709_w24_ms_12", papers_by_id)

        # Check P1 2024 (write-in, 75 marks)
        p1 = papers_by_id["9709_w24_qp_12"]
        self.assertEqual(p1["syllabus"], "9709")
        self.assertEqual(p1["year"], 2024)
        self.assertEqual(p1["session"], "w")
        self.assertEqual(p1["session_slug"], "oct_nov")
        self.assertEqual(p1["component"], 1)
        self.assertEqual(p1["variant"], 2)
        self.assertEqual(p1["total_pages"], 20)
        self.assertEqual(p1["mode"], "write_in")
        self.assertEqual(p1["expected_marks"], 75)
        self.assertEqual(p1["status"], "unprocessed")
        self.assertEqual(p1["output_dir"], "data/extracted/9709/2024/oct_nov/paper_12")

        # Check P4 2024 (write-in, 50 marks)
        p4 = papers_by_id["9709_w24_qp_42"]
        self.assertEqual(p4["component"], 4)
        self.assertEqual(p4["variant"], 2)
        self.assertEqual(p4["expected_marks"], 50)
        self.assertEqual(p4["mode"], "write_in")
        self.assertEqual(p4["session_slug"], "oct_nov")
        self.assertEqual(p4["output_dir"], "data/extracted/9709/2024/oct_nov/paper_42")

        # Check P3 2016 (compact, 75 marks)
        p3 = papers_by_id["9709_s16_qp_31"]
        self.assertEqual(p3["year"], 2016)
        self.assertEqual(p3["session"], "s")
        self.assertEqual(p3["session_slug"], "may_june")
        self.assertEqual(p3["component"], 3)
        self.assertEqual(p3["variant"], 1)
        self.assertEqual(p3["expected_marks"], 75)
        self.assertEqual(p3["total_pages"], 4)
        self.assertEqual(p3["mode"], "compact")
        self.assertEqual(p3["output_dir"], "data/extracted/9709/2016/may_june/paper_31")

        # Check P6 2001 (compact, 50 marks, single-digit code)
        p6 = papers_by_id["9709_w01_qp_6"]
        self.assertEqual(p6["year"], 2001)
        self.assertEqual(p6["session"], "w")
        self.assertEqual(p6["session_slug"], "oct_nov")
        self.assertEqual(p6["component"], 6)
        self.assertIsNone(p6["variant"])
        self.assertEqual(p6["expected_marks"], 50)
        self.assertEqual(p6["total_pages"], 4)
        self.assertEqual(p6["mode"], "compact")
        self.assertEqual(p6["output_dir"], "data/extracted/9709/2001/oct_nov/paper_6")

    def test_scan_idempotency_preserves_existing_states(self):
        # Initial scan
        self.run_cli(
            [
                "scan",
                "--source-dir",
                str(self.source_dir),
                "--queue-file",
                str(self.queue_file),
            ]
        )

        # Update one paper
        self.run_cli(
            [
                "update",
                "--id",
                "9709_w24_qp_12",
                "--status",
                "extracted",
                "--queue-file",
                str(self.queue_file),
            ]
        )

        # Re-run scan
        result = self.run_cli(
            [
                "scan",
                "--source-dir",
                str(self.source_dir),
                "--queue-file",
                str(self.queue_file),
            ]
        )
        self.assertEqual(result.returncode, 0)

        with open(self.queue_file, "r") as f:
            data = json.load(f)

        papers_by_id = {p["id"]: p for p in data["papers"]}
        self.assertEqual(papers_by_id["9709_w24_qp_12"]["status"], "extracted")
        self.assertIsNotNone(papers_by_id["9709_w24_qp_12"]["extracted_at"])
        self.assertEqual(data["summary"]["extracted"], 1)
        self.assertEqual(data["summary"]["unprocessed"], 3)

    def test_next_command_for_extractor(self):
        self.run_cli(
            [
                "scan",
                "--source-dir",
                str(self.source_dir),
                "--queue-file",
                str(self.queue_file),
            ]
        )

        # First request returns an unprocessed paper
        res = self.run_cli(
            ["next", "--role", "extractor", "--queue-file", str(self.queue_file)]
        )
        self.assertEqual(res.returncode, 0)
        next_paper = json.loads(res.stdout)
        self.assertEqual(next_paper["status"], "unprocessed")

        # Set a paper to needs_rework
        self.run_cli(
            [
                "update",
                "--id",
                "9709_s16_qp_31",
                "--status",
                "needs_rework",
                "--notes",
                "Missing subpart (b)",
                "--queue-file",
                str(self.queue_file),
            ]
        )

        # Next request must prioritize needs_rework over unprocessed
        res_rework = self.run_cli(
            ["next", "--role", "extractor", "--queue-file", str(self.queue_file)]
        )
        self.assertEqual(res_rework.returncode, 0)
        rework_paper = json.loads(res_rework.stdout)
        self.assertEqual(rework_paper["id"], "9709_s16_qp_31")
        self.assertEqual(rework_paper["status"], "needs_rework")
        self.assertEqual(rework_paper["verifier_notes"], "Missing subpart (b)")

    def test_next_command_for_verifier(self):
        self.run_cli(
            [
                "scan",
                "--source-dir",
                str(self.source_dir),
                "--queue-file",
                str(self.queue_file),
            ]
        )

        # Initially no paper is extracted, so verifier finds nothing
        res_empty = self.run_cli(
            ["next", "--role", "verifier", "--queue-file", str(self.queue_file)]
        )
        self.assertNotEqual(res_empty.returncode, 0)

        # Mark a paper as extracted
        self.run_cli(
            [
                "update",
                "--id",
                "9709_w24_qp_42",
                "--status",
                "extracted",
                "--queue-file",
                str(self.queue_file),
            ]
        )

        # Verifier should now return that paper
        res = self.run_cli(
            ["next", "--role", "verifier", "--queue-file", str(self.queue_file)]
        )
        self.assertEqual(res.returncode, 0)
        verified_candidate = json.loads(res.stdout)
        self.assertEqual(verified_candidate["id"], "9709_w24_qp_42")
        self.assertEqual(verified_candidate["status"], "extracted")

    def test_update_command_lifecycle_and_summary_counts(self):
        self.run_cli(
            [
                "scan",
                "--source-dir",
                str(self.source_dir),
                "--queue-file",
                str(self.queue_file),
            ]
        )

        # Update to extracted
        res1 = self.run_cli(
            [
                "update",
                "--id",
                "9709_w24_qp_12",
                "--status",
                "extracted",
                "--queue-file",
                str(self.queue_file),
            ]
        )
        self.assertEqual(res1.returncode, 0)

        with open(self.queue_file, "r") as f:
            data = json.load(f)
        self.assertEqual(data["summary"]["extracted"], 1)
        self.assertEqual(data["summary"]["unprocessed"], 3)
        papers_by_id = {p["id"]: p for p in data["papers"]}
        self.assertIsNotNone(papers_by_id["9709_w24_qp_12"]["extracted_at"])

        # Update to verified
        res2 = self.run_cli(
            [
                "update",
                "--id",
                "9709_w24_qp_12",
                "--status",
                "verified",
                "--queue-file",
                str(self.queue_file),
            ]
        )
        self.assertEqual(res2.returncode, 0)

        with open(self.queue_file, "r") as f:
            data = json.load(f)
        self.assertEqual(data["summary"]["extracted"], 0)
        self.assertEqual(data["summary"]["verified"], 1)
        papers_by_id = {p["id"]: p for p in data["papers"]}
        self.assertIsNotNone(papers_by_id["9709_w24_qp_12"]["verified_at"])

        # Update with notes and extracted marks
        res_notes = self.run_cli(
            [
                "update",
                "--id",
                "9709_w24_qp_42",
                "--status",
                "needs_rework",
                "--notes",
                "Equation cut off in q03",
                "--extracted-marks",
                "45",
                "--queue-file",
                str(self.queue_file),
            ]
        )
        self.assertEqual(res_notes.returncode, 0)
        with open(self.queue_file, "r") as f:
            data = json.load(f)
        p42 = {p["id"]: p for p in data["papers"]}["9709_w24_qp_42"]
        self.assertEqual(p42["status"], "needs_rework")
        self.assertEqual(p42["verifier_notes"], "Equation cut off in q03")
        self.assertEqual(p42["extracted_marks"], 45)

        # Update invalid status should fail
        res_invalid = self.run_cli(
            [
                "update",
                "--id",
                "9709_w24_qp_12",
                "--status",
                "bogus_status",
                "--queue-file",
                str(self.queue_file),
            ]
        )
        self.assertNotEqual(res_invalid.returncode, 0)

        # Update non-existent paper should fail
        res_not_found = self.run_cli(
            [
                "update",
                "--id",
                "non_existent_paper",
                "--status",
                "extracted",
                "--queue-file",
                str(self.queue_file),
            ]
        )
        self.assertNotEqual(res_not_found.returncode, 0)

    def test_component_marks_and_mode_helpers(self):
        from tools.queue_manager import determine_expected_marks, determine_mode

        # Marks rule: 75 for P1, P3; 50 for P2, P4, P5, P6, P7
        self.assertEqual(determine_expected_marks(1), 75)
        self.assertEqual(determine_expected_marks(3), 75)
        self.assertEqual(determine_expected_marks(2), 50)
        self.assertEqual(determine_expected_marks(4), 50)
        self.assertEqual(determine_expected_marks(5), 50)
        self.assertEqual(determine_expected_marks(6), 50)
        self.assertEqual(determine_expected_marks(7), 50)

        # Explicit syllabus 9709
        self.assertEqual(determine_expected_marks("9709", 1), 75)
        self.assertEqual(determine_expected_marks("9709", 3), 75)
        self.assertEqual(determine_expected_marks("9709", 4), 50)

        # Extensible syllabuses
        self.assertEqual(determine_expected_marks("9231", 1), 75)
        self.assertEqual(determine_expected_marks("9231", 3), 50)
        self.assertEqual(determine_expected_marks("9702", 1), 40)
        self.assertEqual(determine_expected_marks("9702", 4), 100)

        # Mode rule: compact for <10 pages or year < 2017; write_in for >=10 pages and >= 2017
        self.assertEqual(determine_mode(4, 2024), "compact")
        self.assertEqual(determine_mode(8, 2010), "compact")
        self.assertEqual(determine_mode(12, 2016), "compact")
        self.assertEqual(determine_mode(12, 2017), "write_in")
        self.assertEqual(determine_mode(20, 2024), "write_in")

    def test_missing_queue_file_errors(self):
        non_existent_queue = self.test_dir / "does_not_exist" / "queue.json"
        res_next = self.run_cli(
            ["next", "--role", "extractor", "--queue-file", str(non_existent_queue)]
        )
        self.assertNotEqual(res_next.returncode, 0)

        res_update = self.run_cli(
            [
                "update",
                "--id",
                "any_id",
                "--status",
                "extracted",
                "--queue-file",
                str(non_existent_queue),
            ]
        )
        self.assertNotEqual(res_update.returncode, 0)

    def test_caie_session_slug_mapping(self):
        from tools.queue_manager import CAIE_SESSION_MAP, get_session_slug

        self.assertEqual(CAIE_SESSION_MAP["m"], "feb_march")
        self.assertEqual(CAIE_SESSION_MAP["s"], "may_june")
        self.assertEqual(CAIE_SESSION_MAP["w"], "oct_nov")

        self.assertEqual(get_session_slug("m"), "feb_march")
        self.assertEqual(get_session_slug("s"), "may_june")
        self.assertEqual(get_session_slug("w"), "oct_nov")
        self.assertEqual(get_session_slug("M"), "feb_march")
        self.assertEqual(get_session_slug("S"), "may_june")
        self.assertEqual(get_session_slug("W"), "oct_nov")

    def test_caie_output_dir_taxonomy(self):
        from tools.queue_manager import get_paper_output_dir

        self.assertEqual(
            get_paper_output_dir("9709", 2024, "w", "12"),
            "data/extracted/9709/2024/oct_nov/paper_12",
        )
        self.assertEqual(
            get_paper_output_dir("9709", 2016, "s", "31"),
            "data/extracted/9709/2016/may_june/paper_31",
        )
        self.assertEqual(
            get_paper_output_dir("9709", 2001, "w", "6"),
            "data/extracted/9709/2001/oct_nov/paper_6",
        )
        self.assertEqual(
            get_paper_output_dir("9709", 2022, "m", "12"),
            "data/extracted/9709/2022/feb_march/paper_12",
        )

    def test_parse_paper_metadata_taxonomy(self):
        from tools.queue_manager import parse_paper_metadata

        # March series test
        march_pdf = self.source_dir / "2022" / "9709_m22_qp_12.pdf"
        meta_m = parse_paper_metadata(march_pdf, self.source_dir, total_pages=16)
        self.assertIsNotNone(meta_m)
        self.assertEqual(meta_m["session"], "m")
        self.assertEqual(meta_m["session_slug"], "feb_march")
        self.assertEqual(
            meta_m["output_dir"],
            "data/extracted/9709/2022/feb_march/paper_12",
        )

        # Single digit paper code test
        p6_pdf = self.source_dir / "2001" / "9709_w01_qp_6.pdf"
        meta_p6 = parse_paper_metadata(p6_pdf, self.source_dir, total_pages=4)
        self.assertIsNotNone(meta_p6)
        self.assertEqual(
            meta_p6["output_dir"],
            "data/extracted/9709/2001/oct_nov/paper_6",
        )

    def test_show_command(self):
        self.run_cli(
            [
                "scan",
                "--source-dir",
                str(self.source_dir),
                "--queue-file",
                str(self.queue_file),
            ]
        )

        # Show existing paper
        res = self.run_cli(
            ["show", "--id", "9709_w24_qp_12", "--queue-file", str(self.queue_file)]
        )
        self.assertEqual(res.returncode, 0)
        paper = json.loads(res.stdout)
        self.assertEqual(paper["id"], "9709_w24_qp_12")
        self.assertEqual(
            paper["output_dir"], "data/extracted/9709/2024/oct_nov/paper_12"
        )

        # Show non-existent paper
        res_err = self.run_cli(
            ["show", "--id", "non_existent", "--queue-file", str(self.queue_file)]
        )
        self.assertNotEqual(res_err.returncode, 0)


if __name__ == "__main__":
    unittest.main()
