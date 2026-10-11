import sqlite3
import tempfile
import unittest
from pathlib import Path


class TestDatabaseFoundation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.tmpdir.name)
        self.db_path = self.test_dir / "test.db"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_connection_factory_configuration(self):
        """Connection factory must configure WAL mode, 10s busy timeout, and foreign keys."""
        from tools.db.connection import get_connection

        conn = get_connection(self.db_path, auto_migrate=False)
        try:
            # WAL mode
            cur = conn.execute("PRAGMA journal_mode;")
            journal_mode = cur.fetchone()[0]
            self.assertEqual(journal_mode.lower(), "wal")

            # Busy timeout (10000ms = 10s)
            cur = conn.execute("PRAGMA busy_timeout;")
            busy_timeout = cur.fetchone()[0]
            self.assertEqual(busy_timeout, 10000)

            # Foreign keys enabled
            cur = conn.execute("PRAGMA foreign_keys;")
            fk = cur.fetchone()[0]
            self.assertEqual(fk, 1)

            # Row factory is sqlite3.Row
            self.assertIs(conn.row_factory, sqlite3.Row)
        finally:
            conn.close()

    def test_connection_creates_parent_directory(self):
        """Connection factory should automatically create nested parent directories."""
        from tools.db.connection import get_connection

        nested_path = self.test_dir / "sub" / "dir" / "nested.db"
        self.assertFalse(nested_path.parent.exists())

        conn = get_connection(nested_path, auto_migrate=False)
        try:
            self.assertTrue(nested_path.parent.exists())
            self.assertTrue(nested_path.exists())
        finally:
            conn.close()

    def test_atomic_transaction_commit_and_rollback(self):
        """atomic_transaction helper must commit on success and rollback on error."""
        from tools.db.connection import atomic_transaction, get_connection

        conn = get_connection(self.db_path, auto_migrate=False)
        try:
            conn.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, val TEXT);")

            # Successful transaction commits
            with atomic_transaction(conn):
                conn.execute("INSERT INTO test_data (val) VALUES ('committed');")

            cur = conn.execute("SELECT val FROM test_data;")
            rows = [r[0] for r in cur.fetchall()]
            self.assertEqual(rows, ["committed"])

            # Exception rolls back
            with self.assertRaises(ValueError):
                with atomic_transaction(conn):
                    conn.execute("INSERT INTO test_data (val) VALUES ('rolled_back');")
                    raise ValueError("Simulated failure")

            cur = conn.execute("SELECT val FROM test_data;")
            rows = [r[0] for r in cur.fetchall()]
            self.assertEqual(rows, ["committed"])
        finally:
            conn.close()

    def test_atomic_transaction_nested_savepoints(self):
        """Nested transactions must use SAVEPOINT and roll back inner failures without aborting outer."""
        from tools.db.connection import atomic_transaction, get_connection

        conn = get_connection(self.db_path, auto_migrate=False)
        try:
            conn.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, val TEXT);")

            with atomic_transaction(conn):
                conn.execute("INSERT INTO test_data (val) VALUES ('outer_1');")
                try:
                    with atomic_transaction(conn):
                        conn.execute(
                            "INSERT INTO test_data (val) VALUES ('inner_fail');"
                        )
                        raise RuntimeError("Inner failure")
                except RuntimeError:
                    pass
                conn.execute("INSERT INTO test_data (val) VALUES ('outer_2');")

            cur = conn.execute("SELECT val FROM test_data ORDER BY id;")
            rows = [r[0] for r in cur.fetchall()]
            self.assertEqual(rows, ["outer_1", "outer_2"])
        finally:
            conn.close()

    def test_migration_engine_schema_creation_and_version(self):
        """Migration runner creates all 6 tables, indexes, and tracks user_version."""
        from tools.db.connection import get_connection
        from tools.db.migrations import get_schema_version, run_migrations

        conn = get_connection(self.db_path, auto_migrate=False)
        try:
            self.assertEqual(get_schema_version(conn), 0)

            # Apply migrations
            applied_version = run_migrations(conn)
            self.assertGreaterEqual(applied_version, 1)
            self.assertEqual(get_schema_version(conn), applied_version)

            # Verify all 6 core tables exist
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
            )
            tables = {r["name"] for r in cur.fetchall()}
            expected_tables = {
                "papers",
                "questions",
                "question_parts",
                "topics",
                "question_topics",
                "slices",
            }
            self.assertTrue(
                expected_tables.issubset(tables),
                f"Missing tables: {expected_tables - tables}",
            )

            # Verify idempotence: running migrations again does not error and version remains same
            version_second_run = run_migrations(conn)
            self.assertEqual(version_second_run, applied_version)
            self.assertEqual(get_schema_version(conn), applied_version)
        finally:
            conn.close()

    def test_migration_rollback_on_error(self):
        """Migration runner must roll back atomically if a migration step fails."""
        from tools.db.connection import get_connection
        from tools.db.migrations import Migration, get_schema_version, run_migrations

        conn = get_connection(self.db_path, auto_migrate=False)
        try:
            initial_v = run_migrations(conn)
            self.assertEqual(get_schema_version(conn), initial_v)

            # Define a failing custom migration
            class BrokenMigration(Migration):
                def __init__(self):
                    super().__init__(
                        version=initial_v + 1,
                        name="broken_migration",
                        up="CREATE TABLE should_not_persist (id INT);",
                    )

                def apply(self, c):
                    c.execute("CREATE TABLE should_not_persist (id INT);")
                    raise RuntimeError("Migration explosion")

            custom_migrations = [BrokenMigration()]

            with self.assertRaises(RuntimeError):
                run_migrations(conn, custom_migrations=custom_migrations)

            # Version must NOT have incremented
            self.assertEqual(get_schema_version(conn), initial_v)

            # Table should have rolled back
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='should_not_persist';"
            )
            self.assertIsNone(cur.fetchone())
        finally:
            conn.close()

    def test_relational_schema_constraints_and_cascades(self):
        """Test relational foreign key enforcement and cascading deletes across all 6 tables."""
        from tools.db.connection import atomic_transaction, get_connection

        conn = get_connection(self.db_path, auto_migrate=True)
        try:
            with atomic_transaction(conn):
                # 1. Insert Paper
                conn.execute(
                    """
                    INSERT INTO papers (
                        id, syllabus, year, session, session_slug, component, variant,
                        source_pdf, status, total_pages, mode, expected_marks, output_dir
                    ) VALUES (
                        '9709_w24_qp_12', '9709', 2024, 'w', 'oct_nov', 1, 2,
                        'source.pdf', 'unprocessed', 16, 'write_in', 75, 'data/extracted/...'
                    );
                """
                )

                # 2. Insert Topics
                conn.execute(
                    """
                    INSERT INTO topics (topic_code, title, syllabus)
                    VALUES ('1.1', 'Quadratics', '9709');
                """
                )
                conn.execute(
                    """
                    INSERT INTO topics (topic_code, title, syllabus)
                    VALUES ('1.7', 'Differentiation', '9709');
                """
                )

                # 3. Insert Question
                conn.execute(
                    """
                    INSERT INTO questions (
                        id, paper_id, question_number, total_marks, composite_image_path, preamble_image_path, has_preamble
                    ) VALUES (
                        '9709_w24_qp_12_q01', '9709_w24_qp_12', 1, 5,
                        'questions/q01/full.png', 'questions/q01/preamble.png', 1
                    );
                """
                )

                # 4. Insert Question Part
                conn.execute(
                    """
                    INSERT INTO question_parts (
                        id, question_id, label, marks, part_image_path, has_preamble_context
                    ) VALUES (
                        '9709_w24_qp_12_q01_a', '9709_w24_qp_12_q01', 'a', 3,
                        'questions/q01/part_a.png', 1
                    );
                """
                )

                # 5. Insert Question Topics
                # Question-level topic (part_id is NULL)
                conn.execute(
                    """
                    INSERT INTO question_topics (question_id, topic_code, part_id)
                    VALUES ('9709_w24_qp_12_q01', '1.1', NULL);
                """
                )
                # Part-level topic
                conn.execute(
                    """
                    INSERT INTO question_topics (question_id, topic_code, part_id)
                    VALUES ('9709_w24_qp_12_q01', '1.7', '9709_w24_qp_12_q01_a');
                """
                )

                # 6. Insert Slices
                # Preamble slice
                conn.execute(
                    """
                    INSERT INTO slices (
                        question_id, part_id, kind, page, ymin, ymax, xmin, xmax
                    ) VALUES (
                        '9709_w24_qp_12_q01', NULL, 'preamble', 2, 74, 397, 0, 1000
                    );
                """
                )
                # Part slice
                conn.execute(
                    """
                    INSERT INTO slices (
                        question_id, part_id, kind, page, ymin, ymax, xmin, xmax
                    ) VALUES (
                        '9709_w24_qp_12_q01', '9709_w24_qp_12_q01_a', 'part', 2, 412, 438, 0, 1000
                    );
                """
                )

            # Foreign key integrity checks
            # Inserting question for non-existent paper must fail
            with self.assertRaises(sqlite3.IntegrityError):
                with atomic_transaction(conn):
                    conn.execute(
                        """
                        INSERT INTO questions (id, paper_id, question_number, total_marks)
                        VALUES ('bogus_q', 'non_existent_paper', 99, 5);
                    """
                    )

            # Inserting question_topic for non-existent topic must fail
            with self.assertRaises(sqlite3.IntegrityError):
                with atomic_transaction(conn):
                    conn.execute(
                        """
                        INSERT INTO question_topics (question_id, topic_code, part_id)
                        VALUES ('9709_w24_qp_12_q01', '99.99', NULL);
                    """
                    )

            # Test cascade delete: deleting paper cascades to questions, parts, slices, question_topics
            with atomic_transaction(conn):
                conn.execute("DELETE FROM papers WHERE id = '9709_w24_qp_12';")

            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM questions;").fetchone()[0], 0
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM question_parts;").fetchone()[0], 0
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM question_topics;").fetchone()[0], 0
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM slices;").fetchone()[0], 0
            )
            # Topics table remains intact
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM topics;").fetchone()[0], 2
            )
        finally:
            conn.close()

    def test_seed_syllabus_topics(self):
        """Syllabus topics can be seeded cleanly into topics table."""
        from tools.db.connection import get_connection
        from tools.db.migrations import seed_syllabus_topics

        conn = get_connection(self.db_path, auto_migrate=True)
        try:
            repo_syllabus = (
                Path(__file__).parent.parent / "data" / "syllabus" / "9709.json"
            )
            if repo_syllabus.exists():
                count = seed_syllabus_topics(conn, repo_syllabus)
                self.assertGreater(count, 0)
                # Verify topics like 1.1 Quadratics exist
                cur = conn.execute("SELECT title FROM topics WHERE topic_code = '1.1';")
                row = cur.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["title"], "Quadratics")

                # Seeding again is idempotent
                count_repeat = seed_syllabus_topics(conn, repo_syllabus)
                self.assertEqual(count_repeat, count)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
