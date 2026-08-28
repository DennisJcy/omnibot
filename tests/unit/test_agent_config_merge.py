import platform
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from omnibot.agent_config import generate_config_content, get_config_path, get_config_format


class TestConfigContent(unittest.TestCase):
    def test_hermes_install_command(self):
        self.assertEqual(generate_config_content("hermes"), "omnibot skills install --agent hermes")

    def test_opencode_install_command(self):
        self.assertEqual(generate_config_content("opencode"), "omnibot skills install --agent opencode")

    def test_codex_install_command(self):
        self.assertEqual(generate_config_content("codex"), "omnibot skills install --agent codex")

    def test_claude_install_command(self):
        self.assertEqual(generate_config_content("claude"), "omnibot skills install --agent claude")


class TestConfigPath(unittest.TestCase):
    def test_opencode_path_uses_home_config(self):
        self.assertEqual(get_config_path("opencode"), Path.home() / ".config" / "opencode" / "opencode.json")

    def test_hermes_path_correct(self):
        if platform.system() == "Windows":
            expected = Path(sys.prefix) / "hermes" / "config.yaml"
        else:
            expected = Path.home() / ".hermes" / "config.yaml"
        self.assertEqual(get_config_path("hermes"), expected)

    def test_codex_path(self):
        self.assertEqual(get_config_path("codex"), Path.home() / ".codex" / "config.json")

    def test_claude_path_is_none(self):
        self.assertIsNone(get_config_path("claude"))


class TestConfigFormat(unittest.TestCase):
    def test_opencode_is_command(self):
        self.assertEqual(get_config_format("opencode"), "command")

    def test_hermes_is_command(self):
        self.assertEqual(get_config_format("hermes"), "command")

    def test_codex_is_command(self):
        self.assertEqual(get_config_format("codex"), "command")

    def test_claude_is_command(self):
        self.assertEqual(get_config_format("claude"), "command")


if __name__ == "__main__":
    unittest.main()
