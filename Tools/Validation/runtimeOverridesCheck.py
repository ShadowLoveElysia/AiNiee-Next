"""运行参数契约、执行映射、工作流隔离与恢复回归检查。"""

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ModuleFolders.Infrastructure.TaskContract import TaskContractError, TaskSpec, build_cli_args
from ModuleFolders.Infrastructure.TaskConfig.RuntimeOverrides import (
    RuntimeOverrideError, apply_runtime_overrides, normalize_runtime_overrides,
)
from ModuleFolders.Infrastructure.TaskConfig.RuntimeSnapshot import capture_runtime_snapshot, restore_runtime_snapshot
from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
from ModuleFolders.Infrastructure.Automation.WorkflowRunner import WorkflowRunner, normalize_workflow_steps


def config():
    return {
        "platforms": {
            "first": {"model": "a", "api_url": "https://example.invalid/v1", "api_key": "test-only", "api_format": "OpenAI", "temperature": 0.7},
            "second": {"model": "b", "api_url": "https://second.invalid/v1", "api_key": "second-test-only", "api_format": "OpenAI"},
        },
        "api_settings": {"translate": "first", "polish": "second"},
        "model": "", "base_url": "", "api_key": "",
        "prompt_dictionary_switch": True, "prompt_dictionary_data": [{"src": "test", "dst": "example"}],
        "pre_line_counts": 3, "polishing_pre_line_counts": 2,
        "retry_count": 3,
        "response_check_switch": {"reply_format_check": True, "residual_original_text_check": True},
    }


class RuntimeOverridesCheck(unittest.TestCase):
    def setUp(self):
        from ModuleFolders.Base.Base import Base
        Base.work_status = Base.STATUS.IDLE

    def test_false_zero_contract_and_argv_roundtrip(self):
        values = {"think_switch": False, "pre_line_counts": 0, "retry_count": 0, "user_thread_counts": 150}
        spec = TaskSpec.from_mapping({"task_type": "translate", "input_path": "input.txt", "runtime_overrides": values})
        args = build_cli_args(spec)
        self.assertEqual(json.loads(args[args.index("--runtime-overrides") + 1]), values)
        self.assertEqual(spec.to_queue_fields()["runtime_overrides"], values)

    def test_unknown_type_and_conflicting_values_rejected(self):
        for values in ({"api_key": "not-allowed"}, {"think_switch": "false"}, {"retry_count": True}, {"temperature": float("nan")}):
            with self.assertRaises(RuntimeOverrideError):
                normalize_runtime_overrides(values)
        with self.assertRaises(TaskContractError):
            TaskSpec.from_mapping({"task_type": "translate", "input_path": "x", "threads": 8,
                                   "runtime_overrides": {"user_thread_counts": 4}})

    def test_interface_switch_and_polishing_context(self):
        original = config()
        selected = apply_runtime_overrides(original, {"platform": "second", "pre_line_counts": 0, "temperature": 0.2}, "polish")
        runtime = TaskConfig()
        runtime.load_config_from_dict(selected)
        runtime.prepare_for_translation(TaskType.POLISH)
        request = runtime.get_platform_configuration("polishingReq")
        self.assertEqual(request["model_name"], "b")
        self.assertEqual(request["api_key"], "second-test-only")
        self.assertEqual(request["temperature"], 0.2)
        self.assertEqual(runtime.polishing_pre_line_counts, 0)
        self.assertEqual(original["platforms"]["first"]["temperature"], 0.7)

    def test_nested_checks_and_rule_switch_do_not_leak(self):
        original = config()
        changed = apply_runtime_overrides(original, {"reply_format_check": False, "prompt_dictionary_switch": False})
        runtime = TaskConfig()
        runtime.load_config_from_dict(changed)
        runtime.prepare_for_translation(TaskType.TRANSLATION)
        self.assertFalse(runtime.response_check_switch["reply_format_check"])
        self.assertTrue(runtime.response_check_switch["residual_original_text_check"])
        self.assertEqual(runtime.prompt_dictionary_data, [])
        self.assertTrue(original["prompt_dictionary_switch"])

    def test_snapshot_freezes_values_and_rotates_credentials(self):
        original = config()
        snapshot = capture_runtime_snapshot(original)
        encoded = json.dumps(snapshot)
        self.assertNotIn("test-only", encoded)
        original["pre_line_counts"] = 9
        original["platforms"]["first"]["model"] = "changed"
        original["platforms"]["first"]["api_key"] = "rotated-test-only"
        restored = restore_runtime_snapshot(original, snapshot)
        self.assertEqual(restored["pre_line_counts"], 3)
        self.assertEqual(restored["platforms"]["first"]["model"], "a")
        self.assertEqual(restored["platforms"]["first"]["api_key"], "rotated-test-only")

    def test_workflow_step_override_skip_and_restore(self):
        class Host:
            def __init__(self):
                self.config = config()
                self.active_profile_name = "default"
                self.active_rules_profile_name = "default"
                self.root_config = {}
                self.calls = []

            def run_task(self, mode, **kwargs):
                self.calls.append((mode, copy.deepcopy(self.config)))
                return True

        host = Host()
        original = copy.deepcopy(host.config)
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "input.txt")
            Path(source).write_text("test", encoding="utf-8")
            WorkflowRunner(host).run({
                "task": "all_in_one",
                "task_type": "all_in_one", "input_path": source,
                "runtime_overrides": {"user_thread_counts": 20, "think_switch": False},
                "workflow_steps": [
                    {"id": "translation", "type": "translate"},
                    {"id": "polishing", "type": "polish", "runtime_overrides": {"user_thread_counts": 4}},
                    {"id": "off", "type": "translate", "enabled": False},
                ],
                "step_overrides": {"polishing": {"runtime_overrides": {"pre_line_counts": 0}}},
            })
        self.assertEqual(len(host.calls), 2)
        self.assertEqual(host.calls[0][1]["user_thread_counts"], 20)
        self.assertEqual(host.calls[1][1]["user_thread_counts"], 4)
        self.assertEqual(host.calls[1][1]["polishing_pre_line_counts"], 0)
        self.assertEqual(host.config, original)

    def test_step_ids_stable_after_reorder_and_duplicates_rejected(self):
        steps = normalize_workflow_steps([{"type": "translate"}, {"type": "polish"}])
        reversed_steps = normalize_workflow_steps(steps[::-1])
        self.assertEqual(reversed_steps[0]["id"], steps[1]["id"])
        with self.assertRaises(TaskContractError):
            normalize_workflow_steps([{"type": "translate", "id": "same"}, {"type": "polish", "id": "same"}])

    def test_native_request_body_output_and_thinking(self):
        from ModuleFolders.Infrastructure.LLMRequester.AnthropicRequester import AnthropicRequester
        request = AnthropicRequester()._build_params([], "system", {
            "model_name": "test-model", "max_output_tokens": 4096,
            "think_switch": True, "thinking_budget": 2048,
        })
        self.assertEqual(request["max_tokens"], 4096)
        self.assertEqual(request["thinking"]["budget_tokens"], 2048)
        self.assertNotIn("temperature", request)

    def test_request_retry_zero_uses_task_value_not_global_config(self):
        from ModuleFolders.Base.Base import Base
        from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester
        from ModuleFolders.Infrastructure.LLMRequester.OpenaiRequester import OpenaiRequester
        with patch.object(Base, "load_config", return_value={"retry_count": 8}), \
             patch.object(OpenaiRequester, "request_openai", return_value=(True, "API_FAIL", "temporary failure", 0, 0)) as request, \
             patch("time.sleep"):
            LLMRequester().sent_request([], "", {"target_platform": "first", "runtime_overrides": {"retry_count": 0}})
        self.assertEqual(request.call_count, 1)

    def test_watch_scheduler_and_queue_roundtrip(self):
        from ModuleFolders.Infrastructure.Automation.WatchManager import WatchRule
        from ModuleFolders.Infrastructure.Automation.SchedulerManager import ScheduledTask
        from ModuleFolders.Service.TaskQueue.QueueManager import QueueTaskItem
        values = {"retry_count": 0, "character_recall_switch": False}
        rule = WatchRule("test", ".", runtime_overrides=values)
        restored_rule = WatchRule.from_dict(rule.to_dict())
        self.assertEqual(restored_rule.extra["runtime_overrides"], values)
        scheduled = ScheduledTask("test", "test", "0 0 * * *", input_path=".", runtime_overrides=values)
        restored_schedule = ScheduledTask.from_dict(scheduled.to_dict())
        self.assertEqual(restored_schedule.extra["runtime_overrides"], values)
        with patch("ModuleFolders.Infrastructure.TaskConfig.RuntimeSnapshot.snapshot_for_task", return_value=capture_runtime_snapshot(config())):
            queued = QueueTaskItem("translate", "input.txt", runtime_overrides=values)
            restored = QueueTaskItem.from_dict(queued.to_persistent_dict())
        self.assertEqual(restored.runtime_overrides, values)
        self.assertEqual(restored.workflow_steps[0]["id"], "translate")
        self.assertEqual(restored.extra["runtime_snapshot"], queued.extra["runtime_snapshot"])

    def test_credentials_and_url_survive_repeated_runtime_mapping(self):
        selected = apply_runtime_overrides(config(), {"platform": "second", "think_switch": False})
        selected["api_key"] = "ephemeral-test-only"
        selected["base_url"] = "https://custom.invalid/v1"
        runtime = TaskConfig()
        runtime.load_config_from_dict(selected)
        runtime.prepare_for_translation(TaskType.TRANSLATION)
        request = runtime.get_platform_configuration("translationReq")
        self.assertEqual(request["api_key"], "ephemeral-test-only")
        self.assertEqual(request["api_url"], "https://custom.invalid/v1")

    def test_independent_world_building_override_keeps_content(self):
        original = config()
        original.update(prompt_dictionary_switch=False, world_building_content="example setting")
        selected = apply_runtime_overrides(original, {"world_building_switch": True})
        runtime = TaskConfig()
        runtime.load_config_from_dict(selected)
        runtime.prepare_for_translation(TaskType.TRANSLATION)
        self.assertTrue(runtime.world_building_switch)
        self.assertEqual(runtime.world_building_content, "example setting")

    def test_openai_request_explicit_defaults_and_output(self):
        from ModuleFolders.Infrastructure.TaskConfig.RuntimeOverrides import apply_openai_runtime_request
        request = {"temperature": 0.1, "response_format": {"type": "json_object"}, "max_completion_tokens": 100}
        apply_openai_runtime_request(request, {"runtime_overrides": {
            "temperature": 1, "top_p": 1, "think_switch": False,
            "max_output_tokens": 200, "structured_output_mode": 0,
        }})
        self.assertEqual(request["temperature"], 1)
        self.assertEqual(request["top_p"], 1)
        self.assertEqual(request["reasoning_effort"], "none")
        self.assertEqual(request["max_completion_tokens"], 200)
        self.assertNotIn("response_format", request)
        self.assertNotIn("max_tokens", request)

    def test_smart_round_iterator_observes_updated_limit(self):
        from types import SimpleNamespace
        from ModuleFolders.Service.TaskExecutor.TaskExecutor import _runtime_rounds
        settings = SimpleNamespace(round_limit=1)
        iterator = _runtime_rounds(settings)
        self.assertEqual(next(iterator), 0)
        self.assertEqual(next(iterator), 1)
        settings.round_limit = 2
        self.assertEqual(next(iterator), 2)
        with self.assertRaises(StopIteration):
            next(iterator)

    def test_proofread_is_noninteractive_report_only(self):
        from ModuleFolders.Infrastructure.Cache.CacheItem import TranslationStatus
        from ModuleFolders.Service.Proofreader.AutomationProofread import run_automation_proofread
        from ModuleFolders.Service.Proofreader.ProofreaderTask import ProofreaderTask
        with tempfile.TemporaryDirectory() as folder:
            cache_path = Path(folder, "cache", "AinieeCacheData.json")
            cache_path.parent.mkdir()
            cache_path.write_text(json.dumps({"project_id": "test", "files": {"test.txt": {"items": {
                "1": {"text_index": 1, "source_text": "source", "translated_text": "translation", "translation_status": TranslationStatus.TRANSLATED}
            }}}}), encoding="utf-8")
            original = cache_path.read_bytes()
            with patch.object(ProofreaderTask, "run", return_value={"skip": False, "issues": {}, "corrections": {}}) as request:
                report = run_automation_proofread(config(), folder)
            self.assertTrue(Path(report).is_file())
            self.assertEqual(request.call_count, 1)
            self.assertEqual(cache_path.read_bytes(), original)

    def test_async_polishing_observes_concurrency_and_own_result_path(self):
        from types import SimpleNamespace
        import threading
        import time
        from ModuleFolders.Service.TaskExecutor.TaskExecutor import TaskExecutor
        active = 0
        maximum = 0
        lock = threading.Lock()
        results = []
        def run(task):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.01)
            with lock:
                active -= 1
            return {"polished": task}
        host = SimpleNamespace(config=SimpleNamespace(actual_thread_counts=2), _gated_run=run,
                               task_done_callback=lambda future: results.append(future.result()))
        TaskExecutor._execute_polishing_async(host, list(range(6)))
        self.assertEqual(len(results), 6)
        self.assertLessEqual(maximum, 2)
        self.assertTrue(all("polished" in result for result in results))


if __name__ == "__main__":
    unittest.main()
