import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from continuity.handoff import checkpoint_payload, validate_handoff
from continuity.store import LeaseConflict, Store


class PremiumContinuityTests(unittest.TestCase):
    def test_memory_topic_keeps_revision_history(self):
        with TemporaryDirectory() as d:
            p = Path(d)
            st = Store(p / "c.db")
            st.ensure_project("p", str(p))
            first = st.save_memory("p", "Auth", "JWT", "architecture", "architecture/auth", "s1")
            second = st.save_memory("p", "Auth", "sessions", "architecture", "architecture/auth", "s1")
            self.assertEqual(first, second)
            hist = st.memory_history("p", "architecture/auth")
            self.assertGreaterEqual(len(hist), 3)
            self.assertTrue(any(r["content"] == "JWT" for r in hist))
            self.assertEqual(hist[0]["content"], "sessions")
            st.close()

    def test_lease_conflict_and_explicit_recovery(self):
        with TemporaryDirectory() as d:
            p = Path(d)
            st = Store(p / "c.db")
            st.ensure_project("p", str(p))
            st.acquire_lease("p", "s1", "claude")
            with self.assertRaises(LeaseConflict):
                st.acquire_lease("p", "s2", "codex")
            with self.assertRaises(LeaseConflict):
                st.recover_lease("p", "s2", "codex", expected_owner="wrong")
            st.recover_lease("p", "s2", "codex", expected_owner="s1")
            self.assertEqual(st.active_lease("p")["session_id"], "s2")
            st.close()

    def test_handoff_detects_git_drift(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            (root / "a.txt").write_text("one")
            subprocess.run(["git", "add", "a.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "one"], cwd=root, check=True, capture_output=True)
            handoff = checkpoint_payload(root, session_id="s1", host="test", relevant_files="a.txt")
            (root / "a.txt").write_text("two")
            warnings = validate_handoff(root, handoff)
            self.assertTrue(any("working-tree status differs" in w for w in warnings))


class SkillFrontmatterTests(unittest.TestCase):
    def test_description_is_valid_for_claude_ai_upload(self):
        # claude.ai rejects descriptions containing anything that looks like an XML tag (e.g. "<name>").
        import re
        text = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8")
        front = text.split("---", 2)[1]
        m = re.search(r'^description: "((?:[^"\\]|\\.)*)"\s*$', front, re.M)
        self.assertIsNotNone(m, "description must be one double-quoted line with no bare inner double quotes")
        self.assertNotRegex(m.group(1), r"<[^>]*>")
        self.assertLessEqual(len(m.group(1)), 1024)
