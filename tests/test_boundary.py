import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from continuity.boundary import MAX_TRANSCRIPT_CHARS, transcript_tail


class BoundaryTests(unittest.TestCase):
    def test_transcript_tail_extracts_structured_text(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "transcript.jsonl"
            rows = [
                {"role": "user", "message": {"content": "implement the retry policy"}},
                {"role": "assistant", "content": [{"type": "text", "text": "I changed retry.py and added tests."}]},
            ]
            p.write_text("\n".join(json.dumps(x) for x in rows))
            result = transcript_tail(str(p))
            self.assertTrue(result["available"])
            self.assertIn("implement the retry policy", result["text"])
            self.assertIn("retry.py", result["text"])
            self.assertIn("Best-effort", result["warning"])

    def test_transcript_tail_fails_soft_on_unparseable_input(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "transcript.txt"
            p.write_text("not-json\nnot-json")
            result = transcript_tail(str(p))
            self.assertFalse(result["available"])
            self.assertIn("no parseable", result["reason"])

    def test_transcript_tail_is_bounded(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "transcript.jsonl"
            giant = "x" * (MAX_TRANSCRIPT_CHARS * 3)
            p.write_text(json.dumps({"role": "assistant", "text": giant}))
            result = transcript_tail(str(p))
            self.assertTrue(result["available"])
            self.assertLessEqual(len(result["text"]), MAX_TRANSCRIPT_CHARS)

    def test_transcript_tail_redacts_common_secret_patterns(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "transcript.jsonl"
            p.write_text(
                json.dumps(
                    {
                        "role": "user",
                        "text": "api_key=supersecretvalue123 and Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
                    }
                )
            )
            result = transcript_tail(str(p))
            self.assertTrue(result["available"])
            self.assertTrue(result["redacted"])
            self.assertNotIn("supersecretvalue123", result["text"])
            self.assertNotIn("abcdefghijklmnopqrstuvwxyz", result["text"])
            self.assertIn("REDACTED", result["text"])

    def test_missing_transcript_is_not_error(self):
        result = transcript_tail(None)
        self.assertFalse(result["available"])
        self.assertIn("unavailable", result["reason"])
