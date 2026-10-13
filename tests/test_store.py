import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from continuity.store import Store

class StoreTests(unittest.TestCase):
    def test_topic_upsert_and_search(self):
        with TemporaryDirectory() as d:
            p=Path(d); s=Store(p / "c.db"); s.ensure_project("p", str(p))
            a=s.save_memory("p", "Auth v1", "JWT", "decision", "architecture/auth")
            b=s.save_memory("p", "Auth v2", "sessions", "decision", "architecture/auth")
            self.assertEqual(a,b)
            rows=s.search_memory("p", "sessions")
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["title"], "Auth v2")
            s.close()

    def test_duplicate_index_rows_do_not_crash(self):
        # one source line can yield the same import edge twice; the index rebuild must not abort
        with TemporaryDirectory() as d:
            p=Path(d); s=Store(p / "c.db"); s.ensure_project("p", str(p))
            f={"path":"a.ts","lang":"typescript","digest":"x","mtime_ns":1,"summary":""}
            e={"src":"a.ts","dst":"./b","kind":"imports","evidence":"a.ts:1"}
            y={"path":"a.ts","symbol":"A","kind":"symbol","line":1}
            self.assertEqual(s.replace_index("p",[f],[y,y],[e,e]),(1,2,2))
            s.close()

