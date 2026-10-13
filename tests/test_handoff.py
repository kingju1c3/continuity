import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from continuity.handoff import checkpoint_payload, render_markdown, write_checkpoint

class HandoffTests(unittest.TestCase):
    def test_sections(self):
        with TemporaryDirectory() as d:
            p=checkpoint_payload(Path(d), session_id="s", host="test", goal="g", next_steps="n")
            t=render_markdown(p)
            self.assertIn("## Goal", t)
            self.assertIn("## Next Steps", t)

    def test_same_second_checkpoints_keep_both_files(self):
        with TemporaryDirectory() as d:
            root=Path(d); p=checkpoint_payload(root, session_id="s", host="claude", goal="g")
            a=write_checkpoint(root, p); b=write_checkpoint(root, {**p, "goal":"g2"})
            self.assertNotEqual(a,b)
            self.assertIn("g\n", a.read_text()); self.assertIn("g2", b.read_text())

