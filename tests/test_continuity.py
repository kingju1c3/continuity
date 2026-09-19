import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from continuity_core.store import Store, source, canonical, digest
from continuity_core.graph import index, graph_query, graph_path
from continuity_core.adapters import import_engram, import_graph, import_second_brain


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / "vault", "demo")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def write(self, name, content):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def test_durable_across_processes(self):
        rid = self.store.remember("Decision", "Use SQLite for the first release", topic="database")["id"]
        output = subprocess.check_output([sys.executable, str(ROOT / "scripts/continuity.py"), "--store", str(self.root / "vault"), "--scope", "demo", "get", rid], text=True)
        self.assertEqual(json.loads(output)["body"], "Use SQLite for the first release")

    def test_source_dedup_ignores_observation_clock(self):
        p = self.write("proof.md", "The measured result is 8.")
        first = self.store.remember("Result", "Eight", sources=[source(p)])
        second = self.store.remember("Result", "Eight", sources=[source(p)])
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["duplicate"])

    def test_scope_isolation(self):
        rid = self.store.remember("Secret project", "alpha")["id"]
        other = Store(self.root / "vault", "other")
        try:
            self.assertEqual(other.search("alpha"), [])
            with self.assertRaises(ValueError):
                other.get(rid)
            with self.assertRaises(ValueError):
                other.remember("new", "new", supersedes=rid)
        finally:
            other.close()

    def test_conflicts_and_explicit_supersession(self):
        a = self.store.remember("DB", "Use Postgres", topic="database")["id"]
        b = self.store.remember("DB", "Use SQLite", topic="database")["id"]
        self.assertIn("Possible topic conflicts", self.store.resume())
        self.store.retire(b)
        c = self.store.remember("DB", "Use SQLite", topic="database", supersedes=a)["id"]
        self.assertEqual(self.store.get(a)["status"], "superseded")
        self.assertEqual(self.store.get(c)["status"], "active")
        self.assertNotIn("Possible topic conflicts", self.store.resume())
        self.assertTrue(self.store.audit()["ok"])

    def test_freshness_changed_and_missing(self):
        p = self.write("evidence.md", "original")
        rid = self.store.remember("Evidence", "claim", sources=[source(p)])["id"]
        self.assertEqual(self.store.get(rid)["sources"][0]["state"], "current")
        p.write_text("revised")
        self.assertEqual(self.store.get(rid)["sources"][0]["state"], "changed")
        p.unlink()
        self.assertEqual(self.store.get(rid)["sources"][0]["state"], "missing")

    def test_checkpoint_resume_budget_and_record_status(self):
        rid = self.store.remember("Old decision", "stale decision", topic="design")["id"]
        self.store.checkpoint({"goal": "Ship demo", "summary": "One task remains", "next_actions": ["Run smoke test"], "record_ids": [rid]})
        self.store.retire(rid)
        output = self.store.resume(budget=800)
        self.assertLessEqual(len(output), 800)
        self.assertIn("Run smoke test", output)
        self.assertIn("retired", self.store.resume())

    def test_checkpoint_validation(self):
        with self.assertRaises(ValueError):
            self.store.checkpoint({"goal": "x", "summary": "x", "next_actions": []})
        with self.assertRaises(ValueError):
            self.store.checkpoint({"goal": "x", "summary": "x", "next_actions": ["go"], "record_ids": ["missing"]})

    def test_search_literal_punctuation(self):
        self.store.remember("SQLite", "quote punctuation OR NEAR!")
        self.assertEqual(len(self.store.search('SQLite" OR NEAR(*)')), 1)

    def test_class_a_requires_provenance(self):
        with self.assertRaises(ValueError):
            self.store.remember("claim", "assertion", epistemic="A")

    def test_credentials_tripwire(self):
        with self.assertRaises(ValueError):
            self.store.remember("key", "-----BEGIN PRIVATE KEY-----")

    def test_review_date(self):
        rid = self.store.remember("Review", "check again", review_after="2000-01-01T00:00:00Z")["id"]
        self.assertTrue(self.store.get(rid)["review_due"])
        with self.assertRaises(ValueError):
            self.store.remember("Review", "invalid", review_after="2000-01-01")

    def test_snapshot_roundtrip_and_checksum(self):
        self.store.remember("One", "body")
        self.store.checkpoint({"goal": "goal", "summary": "summary", "next_actions": ["next"]})
        snapshot = self.store.snapshot()
        target = Store(self.root / "restored", "demo")
        try:
            self.assertTrue(target.restore(snapshot)["ok"])
            self.assertEqual(target.search()[0]["title"], "One")
            with self.assertRaises(ValueError):
                target.restore(snapshot)
        finally:
            target.close()
        bad = copy.deepcopy(snapshot)
        bad["data"]["payload"]["records"][0]["body"] = "tampered"
        empty = Store(self.root / "empty", "demo")
        try:
            with self.assertRaises(ValueError):
                empty.restore(bad)
            bad["sha256"] = digest(canonical(bad["data"]))
            with self.assertRaises(ValueError):
                empty.restore(bad)
            self.assertEqual(empty.search(), [])
        finally:
            empty.close()

    def test_audit_detects_projection_edit(self):
        rid = self.store.remember("One", "body")["id"]
        self.store.db.execute("UPDATE records SET body='changed' WHERE id=?", (rid,))
        self.store.db.commit()
        self.assertFalse(self.store.audit()["ok"])

    def test_audit_detects_search_index_loss(self):
        self.store.remember("One", "body")
        self.store.db.execute("DELETE FROM search")
        self.store.db.commit()
        self.assertFalse(self.store.audit()["ok"])

    def test_concurrent_writers(self):
        def write(i):
            s = Store(self.root / "vault", "demo")
            try:
                s.remember(f"Title {i}", f"Observation {i}")
            finally:
                s.close()
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(write, range(12)))
        self.assertEqual(len(self.store.search(limit=20)), 12)
        self.assertTrue(self.store.audit()["ok"])

    def test_index_hashes_deletions_and_source_provenance(self):
        p = self.write("project/main.py", "import json\n\ndef work():\n    return 1\n")
        self.write("project/README.md", "# Demo\n[Code](main.py)\n")
        self.write("project/.env", "TOKEN=secret")
        self.write("project/vendor/other.py", "def excluded(): pass")
        first = index(self.store, p.parent)
        self.assertEqual(first["files"], 2)
        self.assertEqual(index(self.store, p.parent)["changed"], 0)
        matches = graph_query(self.store, "work")
        self.assertEqual(matches[0]["freshness"], "current")
        path = graph_path(self.store, first["origin"], "README.md", "main.py#work@3")
        self.assertTrue(path["found"])
        self.assertEqual([e["relation"] for e in path["path"]], ["links", "contains"])
        p.write_text("changed\n")
        self.assertEqual(graph_query(self.store, "work")[0]["freshness"], "changed")
        p.unlink()
        self.assertEqual(index(self.store, p.parent)["removed"], 1)
        self.assertEqual(graph_query(self.store, "work"), [])

    def test_symlink_outside_project_excluded(self):
        outside = self.write("outside.py", "secret = 42")
        project = self.root / "project"
        project.mkdir()
        (project / "link.py").symlink_to(outside)
        self.assertEqual(index(self.store, project)["files"], 0)

    def test_engram_import_filters_projects_and_deleted(self):
        data = {"version": "0.1.0", "sessions": [{"id": "s", "project": "alpha", "summary": "Work done"}], "observations": [
            {"id": 1, "session_id": "s", "project": None, "title": "Decision", "content": "Use SQLite", "topic_key": "db"},
            {"id": 2, "session_id": "s", "project": "beta", "title": "Other", "content": "private"},
            {"id": 3, "session_id": "s", "title": "Deleted", "content": "old", "deleted_at": "yesterday"},
            {"id": 4, "session_id": "s", "project": "alpha", "scope": "personal", "title": "Personal", "content": "private"}], "prompts": []}
        p = self.write("engram.json", json.dumps(data))
        result = import_engram(self.store, p, "alpha")
        self.assertEqual(result["imported"], 2)
        self.assertEqual(result["skipped"], 3)
        self.assertEqual(self.store.search("private"), [])
        self.assertEqual(self.store.search("SQLite")[0]["class"], "C")
        import_engram(self.store, p, "alpha")
        self.assertEqual(len(self.store.search()), 2)

    def test_graph_adapters_preserve_labels_and_dangling_targets(self):
        for engine, edge_key, label in (("graft", "edges", "inferred"), ("graphify", "links", "AMBIGUOUS")):
            p = self.write(engine + ".json", json.dumps({"nodes": [{"id": "a", "label": "Alpha"}], edge_key: [{"source": "a", "target": "external", "relation": "calls", "confidence": label}]}))
            result = import_graph(self.store, engine, p)
            path = graph_path(self.store, result["origin"], "a", "external")
            self.assertEqual(path["path"][0]["confidence"], label)
            self.assertEqual(result["nodes"], 2)
            p.write_text("changed export")
            self.assertEqual(graph_query(self.store, "Alpha")[-1]["export_source"]["state"], "changed")

    def test_second_brain_import_is_explicit_and_idempotent(self):
        p = self.write("memory/MEMORY.md", "# Context\nA synthetic decision.")
        import_second_brain(self.store, p.parent)
        import_second_brain(self.store, p.parent)
        self.assertEqual(len(self.store.search()), 1)
        self.assertEqual(self.store.search()[0]["class"], "C")


if __name__ == "__main__":
    unittest.main()
