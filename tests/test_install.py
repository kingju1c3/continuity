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

    def test_claude_global_hooks_are_minimal_and_skill_hooks_are_scoped(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            claude = root / ".claude" / "settings.json"
            claude.parent.mkdir(parents=True)
            claude.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "Stop": [
                                {
                                    "hooks": [
                                        {"type": "command", "command": "echo foreign"}
                                    ]
                                }
                            ]
                        }
                    }
                )
            )
            with patch.dict(os.environ, {"HOME": home}):
                install_repo(root, ["claude"])

            data = json.loads(claude.read_text())
            self.assertIn("SessionStart", data["hooks"])
            self.assertIn("SessionEnd", data["hooks"])
            self.assertNotIn("PreCompact", data["hooks"])
            self.assertNotIn("PostToolUse", data["hooks"])
            self.assertNotIn("UserPromptSubmit", data["hooks"])
            self.assertTrue(any("echo foreign" in str(x) for x in data["hooks"]["Stop"]))
            self.assertFalse(any("continuity hook --host claude" in str(x) for x in data["hooks"]["Stop"]))
            start = [
                x
                for x in data["hooks"]["SessionStart"]
                if "continuity hook --host claude" in str(x)
            ]
            self.assertEqual(start[0]["hooks"][0]["timeout"], 10)

            skill = (
                root / ".claude" / "skills" / "continuity" / "SKILL.md"
            ).read_text()
            self.assertIn("hooks:", skill)
            self.assertIn("PreCompact:", skill)
            self.assertIn("statusMessage:", skill)
            self.assertIn("continuity arm", skill)
            self.assertIn("-m continuity hook --host claude", skill)
            self.assertTrue(
                (
                    root
                    / ".claude"
                    / "skills"
                    / "continuity"
                    / "protocol"
                    / "passive-mode.md"
                ).exists()
            )

    def test_codex_dispatchers_include_precompact_but_no_stop_nag(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            codex_dir = Path(home) / ".codex"
            codex_dir.mkdir()
            hooks = codex_dir / "hooks.json"
            hooks.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "Stop": [
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "echo foreign-codex",
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                )
            )
            with patch.dict(os.environ, {"HOME": home}):
                install_repo(root, ["codex"])

            data = json.loads(hooks.read_text())
            self.assertIn("SessionStart", data["hooks"])
            self.assertIn("PreCompact", data["hooks"])
            self.assertIn("PostCompact", data["hooks"])
            self.assertIn("UserPromptSubmit", data["hooks"])
            self.assertIn("PostToolUse", data["hooks"])
            self.assertTrue(
                any("echo foreign-codex" in str(x) for x in data["hooks"]["Stop"])
            )
            self.assertFalse(
                any("continuity hook --host codex" in str(x) for x in data["hooks"]["Stop"])
            )
            pre = [
                x
                for x in data["hooks"]["PreCompact"]
                if "continuity hook --host codex" in str(x)
            ][0]
            handler = pre["hooks"][0]
            self.assertEqual(handler["timeout"], 25)
            self.assertIn("compaction boundary", handler["statusMessage"])

    def test_refuses_project_local_symlink_redirection(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project, TemporaryDirectory() as outside:
            root = Path(project)
            (root / ".claude").symlink_to(Path(outside), target_is_directory=True)
            with patch.dict(os.environ, {"HOME": home}):
                with self.assertRaises(InstallError):
                    install_repo(root, ["claude"])
            self.assertEqual(list(Path(outside).iterdir()), [])

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
                data["hooks"].setdefault("Stop", []).append(
                    {
                        "hooks": [
                            {"type": "command", "command": "echo keep"}
                        ]
                    }
                )
                settings.write_text(json.dumps(data))
                uninstall_repo(root, ["claude", "codex"])

            after = json.loads(settings.read_text())
            self.assertTrue(any("echo keep" in str(x) for x in after["hooks"]["Stop"]))
            self.assertFalse(
                any(
                    "continuity hook --host" in str(x)
                    for xs in after["hooks"].values()
                    for x in xs
                )
            )
            self.assertFalse((root / ".continuity" / "enabled.json").exists())
