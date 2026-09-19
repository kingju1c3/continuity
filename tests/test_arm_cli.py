import io
import os
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from continuity.boundary import get_arm
from continuity.cli import cmd_arm, cmd_disarm
from continuity.project import identity
from continuity.store import Store


class ArmCliTests(unittest.TestCase):
    def setup_owned(self, root: Path, home: str, sid="s1", host="claude"):
        with patch.dict(os.environ, {"HOME": home}):
            st = Store.default()
            ident = identity(root)
            st.ensure_project(ident.key, str(root))
            st.start_session(sid, ident.key, host, str(root))
            st.acquire_lease(ident.key, sid, host)
            st.close()

    def test_arm_uses_exact_active_lease_and_persists_goal(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.setup_owned(root, home)
            args = Namespace(
                path=str(root),
                session=None,
                host="auto",
                goal="finish feature",
                instructions="keep compatibility",
                no_auto_successor=False,
            )
            out = io.StringIO()
            with patch.dict(os.environ, {"HOME": home}), redirect_stdout(out):
                rc = cmd_arm(args)
            self.assertEqual(rc, 0)
            self.assertIn("remain passive", out.getvalue())
            with patch.dict(os.environ, {"HOME": home}):
                st = Store.default()
                arm = get_arm(st, identity(root).key, "s1")
                self.assertEqual(arm["host"], "claude")
                self.assertEqual(arm["goal"], "finish feature")
                self.assertTrue(arm["auto_successor"])
                st.close()

    def test_arm_rejects_host_mismatch(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.setup_owned(root, home, host="claude")
            args = Namespace(
                path=str(root),
                session=None,
                host="codex",
                goal="x",
                instructions="",
                no_auto_successor=False,
            )
            err = io.StringIO()
            with patch.dict(os.environ, {"HOME": home}), redirect_stderr(err):
                rc = cmd_arm(args)
            self.assertEqual(rc, 3)
            self.assertIn("host mismatch", err.getvalue())

    def test_disarm_turns_off_boundary_mode(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.setup_owned(root, home)
            arm_args = Namespace(
                path=str(root),
                session=None,
                host="auto",
                goal="x",
                instructions="",
                no_auto_successor=False,
            )
            disarm_args = Namespace(path=str(root), session=None)
            with patch.dict(os.environ, {"HOME": home}), redirect_stdout(io.StringIO()):
                self.assertEqual(cmd_arm(arm_args), 0)
                self.assertEqual(cmd_disarm(disarm_args), 0)
            with patch.dict(os.environ, {"HOME": home}):
                st = Store.default()
                self.assertEqual(get_arm(st, identity(root).key, "s1")["status"], "disarmed")
                st.close()
