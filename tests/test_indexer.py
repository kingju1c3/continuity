import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from continuity.indexer import build_index

class IndexerTests(unittest.TestCase):
    def test_python_symbols_and_imports(self):
        with TemporaryDirectory() as d:
            p=Path(d)
            (p / "a.py").write_text("import json\nclass A:\n    pass\ndef f():\n    return 1\n")
            files,symbols,edges=build_index(p)
            self.assertTrue(any(x["symbol"]=="A" for x in symbols))
            self.assertTrue(any(x["symbol"]=="f" for x in symbols))
            self.assertTrue(any(x["dst"]=="json" for x in edges))
            self.assertEqual(files[0]["path"], "a.py")
