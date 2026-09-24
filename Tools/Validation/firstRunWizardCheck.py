"""Exercise first-run choices without opening editors or calling provider APIs."""

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rich.console import Console

import ainiee_cli as cli
from ModuleFolders.Infrastructure.TaskConfig import ConfigProfileService as profiles


class FirstRunWizardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.root_config_path = self.root / "config.json"
        self.output = io.StringIO()
        self.events = []
        for target, values in (
            (profiles, {
                "ROOT_CONFIG_FILE": str(self.root_config_path),
                "PROFILES_PATH": str(self.root / "profiles"),
                "RULES_PROFILES_PATH": str(self.root / "rules"),
            }),
            (cli, {
                "console": Console(file=self.output, force_terminal=False, width=120),
                "current_lang": cli.current_lang,
                "i18n": cli.i18n,
                "detect_system_language": lambda: "zh_CN",
            }),
            (cli.Base, {"i18n": cli.Base.i18n}),
        ):
            self.enterContext(patch.multiple(target, **values))
        self.enterContext(patch.object(cli.time, "sleep"))

        self.host = cli.CLIMenu.__new__(cli.CLIMenu)
        self.host.root_config = {"wizard_completed": False}
        self.host.config = {
            "wizard_completed": False,
            "source_language": "Japanese",
            "target_language": "Chinese",
            "translation_execution_mode": "default_api",
            "enable_auto_update": False,
            "enable_github_status_bar": False,
        }
        self.host.active_profile_name = "default"
        self.host.active_rules_profile_name = "None"
        self.host.display_banner = Mock()
        self.host._api_manager = Mock()
        self.host._api_manager.select_api_menu.side_effect = lambda **_: self.events.append("api")
        self.host._api_manager.validate_api.side_effect = lambda: self.events.append("validate")
        self.host._open_external_agent_prompt = Mock(side_effect=lambda: self.events.append("handoff"))
        self.host._check_terminal_compatibility = Mock()
        self.host._maybe_start_background_prewarm = Mock()
        self.host._show_flat_main_menu = Mock(return_value=False)

    def run_wizard(self, choices, *, main_menu=False):
        choices = iter(choices)

        def choose(prompt, **kwargs):
            if prompt.startswith("\nSelect"):
                self.events.append("language")
            elif prompt == cli.i18n.get("external_agent_onboarding_confirm"):
                self.assertEqual(self.host.config["interface_language"], "zh_CN")
                self.events.append("mode")
            else:
                self.events.append("api_type")
            return next(choices)

        def language(prompt, **kwargs):
            if prompt == cli.i18n.get("prompt_source_lang"):
                self.events.append("source")
                return "auto"
            self.assertEqual(prompt, cli.i18n.get("prompt_target_lang"))
            self.events.append("target")
            return "Chinese"

        with patch.object(cli.IntPrompt, "ask", side_effect=choose), patch.object(
            cli.Prompt, "ask", side_effect=language
        ):
            if main_menu:
                self.host.main_menu()
            else:
                self.host.run_wizard()

    def assert_saved(self, status):
        root = json.loads(self.root_config_path.read_text(encoding="utf-8"))
        profile = json.loads((self.root / "profiles" / "default.json").read_text(encoding="utf-8"))
        self.assertIs(root["wizard_completed"], True)
        self.assertIs(root["external_agent_onboarding"], False)
        self.assertEqual(root["external_agent_onboarding_status"], status)
        self.assertEqual(profile["interface_language"], "zh_CN")
        self.assertEqual(profile["translation_execution_mode"], "default_api")
        self.assertNotIn("external_agent_onboarding_status", profile)

    def test_agent_choice_skips_language_and_api_setup_and_persists_completion(self):
        self.run_wizard([1, 1], main_menu=True)
        self.assertEqual(self.events, ["language", "mode", "handoff"])
        self.assertEqual(self.host._api_manager.mock_calls, [])
        self.assertEqual(self.host.config["source_language"], "Japanese")
        self.assertNotIn(cli.i18n.get("menu_api_settings"), self.output.getvalue())
        self.assert_saved("accepted")

    def test_traditional_choice_configures_and_validates_online_or_local_api(self):
        for api_type in (1, 2):
            with self.subTest(api_type=api_type):
                self.host.root_config = {"wizard_completed": False}
                self.host.config["wizard_completed"] = False
                self.host.config["external_agent_onboarding"] = True
                self.host.config["external_agent_onboarding_status"] = "pending"
                self.events.clear()
                self.run_wizard([1, 2, api_type], main_menu=True)
                self.assertEqual(self.events, ["language", "mode", "source", "target", "api_type", "api", "validate"])
                self.host._api_manager.select_api_menu.assert_called_with(online=api_type == 1)
                self.host._open_external_agent_prompt.assert_not_called()
                self.assert_saved("declined")

    def test_saved_agent_choice_skips_api_when_resuming_incomplete_wizard(self):
        self.host.root_config.update(external_agent_onboarding=False, external_agent_onboarding_status="accepted")
        self.run_wizard([1])
        self.assertEqual(self.events, ["language", "handoff"])
        self.assert_saved("accepted")

    def test_saved_traditional_choice_resumes_without_asking_for_mode_again(self):
        self.host.root_config.update(external_agent_onboarding=False, external_agent_onboarding_status="declined")
        self.run_wizard([1, 1])
        self.assertEqual(self.events, ["language", "source", "target", "api_type", "api", "validate"])
        self.assert_saved("declined")

    def test_disabled_onboarding_preserves_manual_setup(self):
        self.host.root_config["external_agent_onboarding"] = False
        self.run_wizard([1, 1])
        self.assertNotIn("mode", self.events)
        self.host._api_manager.validate_api.assert_called_once()

    def test_restart_after_completion_does_not_ask_or_open_handoff_again(self):
        self.run_wizard([1, 1])
        self.events.clear()
        self.host.root_config = json.loads(self.root_config_path.read_text(encoding="utf-8"))
        with patch.object(cli.IntPrompt, "ask", side_effect=AssertionError("unexpected prompt")):
            self.host.main_menu()
        self.assertEqual(self.events, [])

    def test_existing_install_gets_pending_onboarding_without_api_wizard(self):
        self.host.root_config["wizard_completed"] = True
        self.host.config["wizard_completed"] = True
        with patch.object(cli.IntPrompt, "ask", return_value=1) as ask:
            self.host.main_menu()
        ask.assert_called_once()
        self.assertEqual(self.events, ["handoff"])
        self.assertEqual(self.host._api_manager.mock_calls, [])

    def test_handoff_failure_keeps_completed_wizard_saved(self):
        self.host._open_external_agent_prompt.side_effect = RuntimeError("editor unavailable")
        with self.assertRaisesRegex(RuntimeError, "editor unavailable"):
            self.run_wizard([1, 1])
        self.assert_saved("accepted")


if __name__ == "__main__":
    unittest.main()
