import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from continuity.install import InstallError, install_repo, uninstall_repo


class InstallTests(unittest.TestCase):
    def test_refuses_malformed_existing_claude_settings(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            settings = root / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text("{bad")
            with patch.dict(os.environ, {"HOME": home}):
                with self.assertRaises(InstallError):
                    install_repo(root, ["claude"])
            self.assertEqual(settings.read_text(), "{bad")
            self.assertFalse((root / ".continuity" / "enabled.json").exists())

    def test_install_preserves_foreign_hooks_and_uses_seconds(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            claude = root / ".claude" / "settings.json"
            claude.parent.mkdir(parents=True)
            claude.write_text(json.dumps({
                "hooks": {
                    "Stop": [{"hooks": [{"type": "command", "command": "echo foreign"}]}]
                }
            }))
            codex_dir = Path(home) / ".codex"
            codex_dir.mkdir()
            (codex_dir / "hooks.json").write_text(json.dumps({
                "hooks": {
                    "Stop": [{"hooks": [{"type": "command", "command": "echo foreign-codex"}]}]
                }
            }))
            with patch.dict(os.environ, {"HOME": home}):
                install_repo(root, ["claude", "codex"])
            c = json.loads(claude.read_text())
            stop = c["hooks"]["Stop"]
            self.assertTrue(any("echo foreign" in str(x) for x in stop))
            ours = [x for x in stop if "continuity hook --host claude" in str(x)]
            self.assertEqual(ours[0]["hooks"][0]["timeout"], 10)
            self.assertIn("PostCompact", c["hooks"])
            codex = json.loads((codex_dir / "hooks.json").read_text())
            self.assertTrue(any("echo foreign-codex" in str(x) for x in codex["hooks"]["Stop"]))
            self.assertEqual(
                [x for x in codex["hooks"]["SessionStart"] if "continuity hook --host codex" in str(x)][0]["hooks"][0]["timeout"],
                10,
            )
            self.assertTrue((root / ".continuity" / "enabled.json").exists())
            self.assertTrue((root / ".claude" / "skills" / "continuity" / "protocol" / "session-open.md").exists())
            self.assertTrue((root / ".agents" / "skills" / "continuity" / "schemas" / "checkpoint.schema.json").exists())

    def test_uninstall_removes_only_continuity_owned_entries(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            codex_dir = Path(home) / ".codex"
            codex_dir.mkdir()
            (codex_dir / "hooks.json").write_text(json.dumps({"hooks": {}}))
            with patch.dict(os.environ, {"HOME": home}):
                install_repo(root, ["claude", "codex"])
                settings = root / ".claude" / "settings.json"
                data = json.loads(settings.read_text())
                data["hooks"]["Stop"].append({"hooks": [{"type": "command", "command": "echo keep"}]})
                settings.write_text(json.dumps(data))
                uninstall_repo(root, ["claude", "codex"])
            after = json.loads(settings.read_text())
            self.assertTrue(any("echo keep" in str(x) for x in after["hooks"]["Stop"]))
            self.assertFalse(any("continuity hook --host" in str(x) for xs in after["hooks"].values() for x in xs))
            self.assertFalse((root / ".continuity" / "enabled.json").exists())
