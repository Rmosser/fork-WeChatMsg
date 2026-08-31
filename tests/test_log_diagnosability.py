import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.DataBase.merge import build_merged_database, merge_databases, read_message_receipt
from app.log.logger import log, safe_log_object


def create_message_db(path, value):
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE MSG (TalkerId TEXT, MsgsvrID INTEGER, Type INTEGER, SubType INTEGER, "
        "IsSender INTEGER, CreateTime INTEGER, Sequence INTEGER, StrTalker TEXT, "
        "StrContent TEXT, DisplayContent TEXT, BytesExtra BLOB)"
    )
    connection.execute(
        "INSERT INTO MSG VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("talker", value, 1, 0, 0, 1, 1, "talker", "message", "", b""),
    )
    connection.commit()
    connection.close()


class DiagnosabilityTests(unittest.TestCase):
    def test_decorator_redacts_key_and_message_and_reraises(self):
        @log
        def failing(key, message):
            raise ValueError("bad database input")

        self.assertEqual(safe_log_object({"key": "secret", "message": "chat"}), {
            "key": "<present>",
            "message": "<hash:31e06f7d89fe>",
        })
        with self.assertRaisesRegex(ValueError, "bad database input"):
            failing("secret-key", "private message")

    def test_public_merge_rejects_existing_target_mutation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "MSG0.db"
            target = root / "MSG.db"
            missing = root / "MSG1.db"
            create_message_db(source, 1)
            create_message_db(target, 0)

            with self.assertRaisesRegex(RuntimeError, "direct database merge is disabled"):
                merge_databases([str(source), str(missing)], str(target), run_id="run-1")

    def test_atomic_build_merges_each_shard_once(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "one.db"
            second = root / "two.db"
            temporary = root / ".result.tmp"
            create_message_db(first, 1)
            create_message_db(second, 2)

            receipt = build_merged_database([str(first), str(second)], str(temporary), run_id="atomic-1")

            self.assertEqual(receipt, {"integrity": "ok", "row_count": 2})
            self.assertEqual(read_message_receipt(str(temporary))["row_count"], 2)

    def test_atomic_build_failure_leaves_existing_target_unchanged(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.db"
            target = root / "MSG.db"
            temporary = root / ".result.tmp"
            create_message_db(source, 1)
            create_message_db(target, 99)
            before = target.read_bytes()

            with self.assertRaises(RuntimeError):
                build_merged_database([str(source), str(root / "missing.db")], str(temporary), run_id="atomic-2")

            self.assertEqual(target.read_bytes(), before)
            self.assertFalse(temporary.exists())


if __name__ == "__main__":
    unittest.main()
