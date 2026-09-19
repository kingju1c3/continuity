import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from continuity.handoff import checkpoint_payload, render_markdown

class HandoffTests(unittest.TestCase):
    def test_sections(self):
        with TemporaryDirectory() as d:
            p=checkpoint_payload(Path(d), session_id="s", host="test", goal="g", next_steps="n")
            t=render_markdown(p)
            self.assertIn("## Goal", t)
            self.assertIn("## Next Steps", t)
