import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.DataBase.merge import merge_databases
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

    def test_merge_reports_missing_fragments_without_silent_success(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "MSG0.db"
            target = root / "MSG.db"
            missing = root / "MSG1.db"
            create_message_db(source, 1)
            create_message_db(target, 0)

            summary = merge_databases([str(source), str(missing)], str(target), run_id="run-1")

            self.assertEqual(summary["status"], "partial")
            self.assertEqual(summary["merged_count"], 1)
            self.assertEqual(summary["missing"], [str(missing)])
            self.assertEqual(summary["run_id"], "run-1")


if __name__ == "__main__":
    unittest.main()
