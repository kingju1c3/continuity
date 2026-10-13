import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from continuity.boundary import claim_generation, session_label
from continuity.store import Store


class SessionLabelTests(unittest.TestCase):
    def test_label_format(self):
        self.assertEqual(session_label("FE", "1.2"), "Session FE 1.2")

    def test_every_instance_gets_a_unique_sequential_number(self):
        with TemporaryDirectory() as d:
            st = Store(Path(d) / "c.db")
            try:
                claim = lambda label, wanted: claim_generation(st, "proj", label, wanted)
                self.assertEqual(claim("FE", "1.0"), "1.0")  # first instance
                self.assertEqual(claim("FE", "1.0"), "1.1")  # a second chain under FE never reuses 1.0
                self.assertEqual(claim("FE", "1.1"), "1.2")  # a successor that wanted 1.1 moves past it
                self.assertEqual(claim("fe", "1.0"), "1.3")  # labels match case-insensitively
                self.assertEqual(claim("FE", "1.9"), "1.9")  # a later wanted number is honoured
                self.assertEqual(claim("FE", "1.4"), "1.10")  # ...and never reissued below it
                self.assertEqual(claim("BE", "1.0"), "1.0")  # labels are independent
            finally:
                st.close()


if __name__ == "__main__":
    unittest.main()
