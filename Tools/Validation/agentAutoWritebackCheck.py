"""Native Windows/POSIX checks for Agent automatic writeback and repair."""
from __future__ import annotations

import json
import multiprocessing
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ModuleFolders.Service.Agent.ExternalAgentBatch import ExternalAgentBatchService, ExternalAgentBatchError
from ModuleFolders.Service.Agent.ExternalAgentBatchResult import ExternalAgentBatchResultService
from ModuleFolders.Service.Agent.ExternalAgentBatchResult import ExternalAgentBatchResultError
from ModuleFolders.Service.Agent.ExternalAgentBatchWriter import ExternalAgentBatchWriter
from ModuleFolders.Service.Agent.ExternalAgentWorkflow import ExternalAgentWorkflow
from ModuleFolders.Service.Agent.ExternalAgentWriterLease import ExternalAgentWriterLeaseRegistry


def services(root, batch_size=2):
    batches = ExternalAgentBatchService(root, state_root=root / "ledger", batch_size=batch_size, batch_limit_provider=lambda: 8)
    results = ExternalAgentBatchResultService(root, state_root=root / "results")
    leases = ExternalAgentWriterLeaseRegistry(state_path=root / "leases.json")
    return batches, results, leases, ExternalAgentWorkflow(batches, results, leases)


def process_submit(root, batch_id):
    root = Path(root)
    batches, _, _, flow = services(root)
    batch = batches.claim_batch("task", "session", batch_id)["batch"]
    result = flow.submit("task", "session", batch_id, batch["source_hash"], batch["revision"], batch_id,
                         [{"index": i["index"], "translation": "Translated [P1]"} for i in batch["items"]])
    if result["status"] != "committed":
        raise RuntimeError(result)


class AutoWritebackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cache = self.root / "AinieeCacheData.json"
        self.cache.write_text(json.dumps({"project_id": "test", "files": {"book.txt": {"items": [
            {"text_index": i, "source_text": f"Source {i} [P1]", "translated_text": "", "translation_status": 0}
            for i in range(6)
        ]}}}), encoding="utf-8")
        self.batches, self.results, self.leases, self.flow = services(self.root)
        self.batches.prepare_cache_project(self.cache, "task", "session", "external_agent")
        self.claims = self.batches.claim_batches("task", "session")["batches"]

    def items(self, batch):
        return [{"index": i["index"], "translation": "Translated [P1]"} for i in batch["items"]]

    def submit(self, batch, items=None, key=None, **kwargs):
        return self.flow.submit("task", "session", batch["batch_id"], batch["source_hash"], batch["revision"],
                                key or batch["batch_id"], self.items(batch) if items is None else items, **kwargs)

    def test_auto_commit_out_of_order_and_compact_receipts(self):
        for batch in reversed(self.claims):
            result = self.submit(batch)
            self.assertEqual(result["status"], "committed")
            self.assertNotIn("items", result)
            self.assertNotIn("Source", json.dumps(result))
            self.assertLess(len(json.dumps(result)), 1800)
        self.assertTrue(self.flow.pending_work("task", "session")["all_committed"])
        saved = json.loads(self.cache.read_text())
        self.assertTrue(all(i["translated_text"] == "Translated [P1]" for i in saved["files"]["book.txt"]["items"]))

    def test_invalid_candidate_does_not_write_then_patch_and_retry(self):
        batch = self.claims[0]
        before = self.cache.read_bytes()
        items = self.items(batch)
        items[1]["translation"] = "Lost placeholder"
        receipt = self.submit(batch, items)
        self.assertEqual(receipt["status"], "repair_required")
        self.assertEqual(receipt["issues"][0]["index"], 1)
        self.assertEqual(self.cache.read_bytes(), before)
        self.assertEqual(self.results.read_staged("task")["results"], [])
        detail = self.flow.get_repair("task", "session", batch["batch_id"])
        self.assertEqual(len(detail["items"]), 1)
        self.assertEqual(detail["items"][0]["candidate_translation"], "Lost placeholder")
        patch_items = [{"index": 1, "translation": "Fixed [P1]"}]
        receipt = self.submit(batch, patch_items, key="repair-1", repair=True)
        self.assertEqual(receipt["status"], "committed")
        replay = self.submit(batch, patch_items, key="repair-1", repair=True)
        self.assertTrue(replay["replayed"])
        self.assertEqual(len(list((self.root / "backups").glob("*.json"))), 1)

    def test_missing_empty_and_newline_are_actionable(self):
        for items, expected in [([], "MISSING_ITEM"),
                                ([{"index": 0, "translation": ""}], "EMPTY_TRANSLATION"),
                                ([{"index": 0, "translation": "Line\n[P1]"}], "NEWLINE_MISMATCH")]:
            receipt = self.submit(self.claims[0], items, key=expected)
            self.assertIn(expected, {i["code"] for i in receipt["issues"]})
        self.assertEqual(receipt["status"], "needs_review")
        self.assertFalse(self.flow.pending_work("task", "session")["all_committed"])

    def test_rejected_retry_does_not_consume_attempt_and_other_batches_continue(self):
        result = self.submit(self.claims[0], [])
        self.assertEqual(self.submit(self.claims[0], [])["repair_attempts"], 1)
        self.assertEqual(self.submit(self.claims[1])["status"], "committed")
        self.assertEqual(self.flow.get_repair("task", "session", self.claims[0]["batch_id"])["status"], result["status"])

    def test_cache_edit_conflict_does_not_overwrite(self):
        document = json.loads(self.cache.read_text())
        document["files"]["book.txt"]["items"][0]["translated_text"] = "Manual edit"
        self.cache.write_text(json.dumps(document), encoding="utf-8")
        before = self.cache.read_bytes()
        result = self.submit(self.claims[0])
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(result["write_error"]["code"], "ITEM_CONFLICT")
        self.assertEqual(self.cache.read_bytes(), before)
        self.assertEqual(self.submit(self.claims[1])["status"], "committed")

    def test_committed_retry_is_idempotent_and_changed_payload_rejected(self):
        batch = self.claims[0]
        self.submit(batch)
        before = self.cache.read_bytes()
        self.assertTrue(self.submit(batch)["replayed"])
        with self.assertRaises(ExternalAgentBatchError):
            self.submit(batch, [{"index": i["index"], "translation": "Changed [P1]"} for i in batch["items"]])
        self.assertEqual(self.cache.read_bytes(), before)

    def test_manual_staging_uses_same_commit_path(self):
        for b in self.claims:
            self.assertEqual(self.submit(b, auto_commit=False)["status"], "submitted")
        for b in reversed(self.claims):
            self.assertEqual(self.flow.commit("task", "session", b["batch_id"])["status"], "committed")

    def test_write_failure_retries_without_retranslation(self):
        before = self.cache.read_bytes()
        with patch.object(ExternalAgentBatchWriter, "_backup", side_effect=OSError("disk unavailable")):
            result = self.submit(self.claims[0])
        self.assertEqual(result["write_error"]["code"], "WRITE_IO_ERROR")
        self.assertEqual(self.cache.read_bytes(), before)
        self.assertEqual(self.flow.commit("task", "session", self.claims[0]["batch_id"])["status"], "committed")

    def test_staging_failure_recovers_from_durable_submission(self):
        with patch.object(self.results, "_write_document", side_effect=OSError("staging unavailable")):
            result = self.submit(self.claims[0])
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(result["write_error"]["code"], "WRITE_IO_ERROR")
        self.assertEqual(self.submit(self.claims[0])["status"], "committed")

    def test_staging_only_retry_restages_after_interruption(self):
        with patch.object(self.results, "_write_document", side_effect=OSError("staging unavailable")):
            with self.assertRaises(OSError):
                self.submit(self.claims[0], auto_commit=False)
        self.assertTrue(self.submit(self.claims[0], auto_commit=False)["replayed"])
        self.assertEqual(len(self.results.read_staged("task")["results"]), 1)

    def test_low_level_invalid_submit_does_not_poison_idempotency(self):
        batch = self.claims[0]
        args = ("task", "session", batch["batch_id"], batch["source_hash"], batch["revision"], "key")
        with self.assertRaises(ExternalAgentBatchResultError):
            self.batches.submit_translation_batch(*args, [{"index":i["index"], "translation":"Missing"} for i in batch["items"]])
        self.assertEqual(self.batches.claim_batch("task", "session", batch["batch_id"])["batch"]["status"], "claimed")
        self.assertEqual(self.batches.submit_translation_batch(*args, self.items(batch))["status"], "accepted")

    def test_after_crash_manual_cache_change_is_not_misidentified_as_our_write(self):
        with patch.object(self.batches, "mark_batch_committed", side_effect=RuntimeError("crash")):
            with self.assertRaises(RuntimeError):
                self.submit(self.claims[0])
        document = json.loads(self.cache.read_text())
        document["files"]["book.txt"]["items"][0]["polished_text"] = "Human edit"
        self.cache.write_text(json.dumps(document), encoding="utf-8")
        before = self.cache.read_bytes()
        result = self.submit(self.claims[0])
        self.assertEqual(result["write_error"]["code"], "ITEM_CONFLICT")
        self.assertEqual(self.cache.read_bytes(), before)

    def test_missing_hash_cannot_enable_cache_rebase(self):
        batch = self.claims[0]
        self.submit(batch, auto_commit=False)
        staged = self.results.read_staged("task")
        record = staged["results"][0]
        record["cache_revision"] = "0" * 64
        for item in record["items"]:
            item.pop("current_line_hash")
        before = self.cache.read_bytes()
        with self.assertRaises(ValueError):
            ExternalAgentBatchWriter(self.root).apply_staged_result(self.cache, staged, writer_lease_id="test")
        self.assertEqual(self.cache.read_bytes(), before)

    def test_crash_after_cache_replace_reconciles_before_later_batch(self):
        with patch.object(self.batches, "mark_batch_committed", side_effect=RuntimeError("simulated crash")):
            with self.assertRaises(RuntimeError):
                self.submit(self.claims[0])
        self.assertEqual(self.batches.get_project("task", "session")["committed_batches"], 0)
        self.assertEqual(self.submit(self.claims[1])["status"], "committed")
        self.assertEqual(self.batches.get_project("task", "session")["committed_batches"], 2)
        self.assertEqual(len(list((self.root / "backups").glob("*.json"))), 2)

    def test_thread_and_process_writers_do_not_lose_updates(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            receipts = list(pool.map(lambda b: services(self.root)[3].submit(
                "task", "session", b["batch_id"], b["source_hash"], b["revision"], b["batch_id"], self.items(b)
            ), self.claims))
        self.assertTrue(all(r["status"] == "committed" for r in receipts))

    def test_independent_processes_share_task_and_cache_locks(self):
        ctx = multiprocessing.get_context("spawn")
        processes = [ctx.Process(target=process_submit, args=(str(self.root), b["batch_id"])) for b in self.claims]
        for proc in processes:
            proc.start()
        for proc in processes:
            proc.join(20)
            if proc.is_alive():
                proc.terminate()
                proc.join()
            self.assertEqual(proc.exitcode, 0)
        self.assertTrue(self.flow.pending_work("task", "session")["all_committed"])

    def test_unauthorized_session_cannot_repair_or_commit(self):
        before = self.cache.read_bytes()
        for op in (lambda: self.flow.pending_work("task", "other"),
                   lambda: self.flow.get_repair("task", "other", self.claims[0]["batch_id"]),
                   lambda: self.flow.commit("task", "other", self.claims[0]["batch_id"])):
            with self.assertRaises(ExternalAgentBatchError):
                op()
        self.assertEqual(self.cache.read_bytes(), before)

    def test_repair_survives_service_restart_and_session_resume(self):
        batch = self.claims[0]
        self.submit(batch, [])
        batches, _, _, flow = services(self.root)
        batches.resume_task("task", "session", "new-session")
        self.assertEqual(flow.get_repair("task", "new-session", batch["batch_id"])["status"], "repair_required")
        result = flow.submit("task", "new-session", batch["batch_id"], batch["source_hash"], batch["revision"],
                             "fix", self.items(batch), repair=True)
        self.assertEqual(result["status"], "committed")

    def test_adapter_auto_commit_and_export_only_after_all_committed(self):
        from Tools.MCPServer import server
        from Tools.Skills.skills.agent_skill import AgentSkill

        class Capture:
            def __init__(self, *args, **kwargs):
                self.tools = {}
            def tool(self):
                def register(f):
                    self.tools[f.__name__] = f
                    return f
                return register

        registry = Mock()
        registry.status.return_value = {"state": "registered"}
        registry.has_external_mode.return_value = True
        with patch("mcp.server.fastmcp.FastMCP", Capture), patch.object(server, "_patch_streamable_http_shutdown_for_windows"):
            app = server._build_mcp_app(Mock(), SimpleNamespace(app=SimpleNamespace(routes=[])), "127.0.0.1", 8765, "/mcp")
        with patch.object(server, "AGENT_SESSION_REGISTRY", registry), \
             patch.object(server, "get_external_agent_batch_service", return_value=self.batches), \
             patch.object(server, "get_external_agent_batch_result_service", return_value=self.results), \
             patch.object(server, "get_external_agent_writer_lease_registry", return_value=self.leases), \
             patch.object(server, "_finalize_external_agent_output", return_value={"status": "exported"}) as export:
            b = self.claims[0]
            result = app.tools["agent_submit_translation_batch"]("task", "session", b["batch_id"], b["source_hash"], b["revision"], "a", self.items(b))
            self.assertEqual(result["status"], "committed")
            export.assert_not_called()
            skill = AgentSkill(registry, batch_service=self.batches, result_service=self.results, writer_lease_registry=self.leases)
            b = self.claims[1]
            result = skill.execute({"action": "submit_translation_batch", "task_id": "task", "session_id": "session",
                                    "batch_id": b["batch_id"], "source_hash": b["source_hash"], "revision": b["revision"],
                                    "idempotency_key": "b", "items": self.items(b)})
            self.assertTrue(result.success)
            self.assertEqual(result.data["status"], "committed")
            b = self.claims[2]
            args = ("task", "session", b["batch_id"], b["source_hash"], b["revision"], "c", self.items(b))
            result = app.tools["agent_submit_translation_batch"](*args)
            self.assertEqual(result["export"]["status"], "exported")
            app.tools["agent_submit_translation_batch"](*args)
            export.assert_called_once()


if __name__ == "__main__":
    unittest.main()
