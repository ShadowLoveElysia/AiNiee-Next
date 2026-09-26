"""Submit, validate, repair and commit through one transport-independent workflow."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

from .ExternalAgentBatch import ExternalAgentBatchError, ExternalAgentBatchService
from .ExternalAgentBatchResult import ExternalAgentBatchResultError, ExternalAgentBatchResultService
from .ExternalAgentBatchWriter import ExternalAgentBatchWriter, ExternalAgentBatchWriterError
from .ExternalAgentWriterLease import ExternalAgentWriterLeaseError, ExternalAgentWriterLeaseRegistry


class ExternalAgentWorkflow:
    def __init__(self, batches: ExternalAgentBatchService, results: ExternalAgentBatchResultService,
                 leases: ExternalAgentWriterLeaseRegistry):
        self.batches, self.results, self.leases = batches, results, leases

    def _state(self, task_id: str, session_id: str):
        state = self.batches._read(task_id)
        self.batches._validate_session(state, session_id)
        return state

    @staticmethod
    def _batch(state, batch_id):
        batch = next((b for b in state["batches"] if b["batch_id"] == batch_id), None)
        if batch is None:
            raise ExternalAgentBatchError("batch does not exist", "BATCH_NOT_FOUND")
        return batch

    def _save(self, state):
        self.batches._refresh_status(state)
        state["updated_at"] = self.batches._clock()
        self.batches._write(state)

    def _receipt(self, state, batch, *, replayed=False):
        view = self.batches._project_view(state, include_batches=False)
        progress = {k: v for k, v in view.items() if k.endswith("_batches") or k in {"status", "max_batches"}}
        result = {
            "task_id": state["task_id"], "batch_id": batch["batch_id"],
            "status": batch["status"], "replayed": replayed,
            "item_count": len(batch["items"]), "progress": progress,
            "repair_attempts": batch.get("repair_attempts", 0),
            "issues": deepcopy(batch.get("issues", [])),
        }
        if batch.get("write_error"):
            result["write_error"] = deepcopy(batch["write_error"])
        result["next_action"] = (
            "resolve_write_error_then_retry_commit" if batch.get("write_error") else
            "get_batch_repair_then_submit_patch" if batch["status"] == "repair_required" else
            "report_unresolved_items" if batch["status"] == "needs_review" else
            "check_pending_work_then_export" if state["status"] == "completed" else
            "continue_other_batches" if batch["status"] == "committed" else
            "commit_cache_batch" if state.get("cache_path") else "staging_only"
        )
        return result

    def pending_work(self, task_id, session_id):
        with self.batches.transaction(task_id):
            state = self._state(task_id, session_id)
            return {
                "task_id": task_id, "status": state["status"],
                "remaining": [
                    {"batch_id": b["batch_id"], "status": b["status"],
                     "issue_count": len(b.get("issues", [])), "write_error": b.get("write_error")}
                    for b in state["batches"] if b["status"] != "committed"
                ],
                "all_committed": all(b["status"] == "committed" for b in state["batches"]),
            }

    def get_repair(self, task_id, session_id, batch_id):
        with self.batches.transaction(task_id):
            state = self._state(task_id, session_id)
            batch = self._batch(state, batch_id)
            result = self._receipt(state, batch)
            indexes = {issue.get("index") for issue in batch.get("issues", [])}
            candidates = {item["index"]: item["translation"] for item in batch.get("candidate_items", [])}
            result.update({
                "source_hash": batch["source_hash"], "revision": batch["revision"],
                "items": [
                    {**deepcopy(item), "candidate_translation": candidates.get(item["index"])}
                    for item in batch["items"] if item["index"] in indexes or None in indexes
                ],
            })
            return result

    def _inspect_items(self, batch, items):
        expected = {item["index"]: item for item in batch["items"]}
        by_id = {item.get("item_id"): item["index"] for item in batch["items"] if item.get("item_id")}
        candidates, issues, seen = {}, [], set()
        if not isinstance(items, list):
            return [], [{"code": "INVALID_RESULT_ITEMS", "message": "items must be an array of {index, translation}"}]
        for position, item in enumerate(items):
            index = item.get("index") if isinstance(item, dict) else None
            if isinstance(item, dict) and index is None and isinstance(item.get("item_id"), str):
                index = by_id.get(item["item_id"])
            if isinstance(index, bool) or not isinstance(index, int) or index not in expected:
                issues.append({"code": "INVALID_INDEX", "position": position, "message": "use an index returned by claim"})
                continue
            if index in seen:
                issues.append({"code": "DUPLICATE_INDEX", "index": index, "message": "send this item once"})
                continue
            seen.add(index)
            if isinstance(item.get("translation"), str):
                candidates[index] = {"index": index, "translation": item["translation"]}
            try:
                normalized = self.batches._validate_result_items([expected[index]], [item])
                target = self.results._expected_items({"items": [expected[index]]})
                self.results._validate_items(target, normalized)
            except (ExternalAgentBatchError, ExternalAgentBatchResultError) as exc:
                issues.append({"code": exc.code, "index": index, "message": str(exc), "field": "translation"})
        for index in expected.keys() - seen:
            issues.append({"code": "MISSING_ITEM", "index": index, "message": "supply this item's translation"})
        return list(candidates.values()), issues

    def submit(self, task_id, session_id, batch_id, source_hash, revision, idempotency_key, items,
               *, auto_commit=True, repair=False):
        if not isinstance(auto_commit, bool) or not isinstance(repair, bool):
            raise ExternalAgentBatchError("auto_commit and repair must be booleans", "INVALID_ARGUMENTS")
        if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > 256:
            raise ExternalAgentBatchError("idempotency_key is required", "INVALID_IDEMPOTENCY_KEY")
        with self.batches.transaction(task_id):
            state = self._state(task_id, session_id)
            batch = self._batch(state, batch_id)
            if batch["source_hash"] != source_hash:
                raise ExternalAgentBatchError("source hash differs from claim", "SOURCE_HASH_MISMATCH")
            if isinstance(revision, bool) or not isinstance(revision, int) or batch["revision"] != revision:
                raise ExternalAgentBatchError("revision differs from claim", "REVISION_CONFLICT")
            if batch["status"] not in {"claimed", "repair_required", "needs_review", "submitted", "committed"}:
                raise ExternalAgentBatchError("claim this batch first", "BATCH_NOT_CLAIMED")
            if batch.get("claimed_session_id") != session_id:
                raise ExternalAgentBatchError("session does not own this batch", "SESSION_MISMATCH")
            request_hash = hashlib.sha256(json.dumps(
                [idempotency_key, items, repair], ensure_ascii=False, sort_keys=True
            ).encode()).hexdigest()
            if batch.get("accepted_request") == request_hash and batch["status"] in {"submitted", "committed"}:
                if batch["status"] == "submitted" and auto_commit and state.get("cache_path"):
                    return self.commit(task_id, session_id, batch_id)
                if batch["status"] == "submitted":
                    self.results.validate_and_stage(state, batch["submission"], idempotency_key=batch["idempotency_key"])
                return self._receipt(state, batch, replayed=True)
            if repair:
                if batch["status"] not in {"repair_required", "needs_review"}:
                    raise ExternalAgentBatchError("batch has no repair candidate", "BATCH_NOT_REPAIRABLE")
                if not isinstance(items, list):
                    raise ExternalAgentBatchError("repair items must be an array", "INVALID_RESULT_ITEMS")
                merged = {x["index"]: x for x in batch.get("candidate_items", [])}
                patch_indexes = set()
                expected_indexes = {x["index"] for x in batch["items"]}
                for item in items:
                    index = item.get("index") if isinstance(item, dict) else None
                    if isinstance(index, bool) or not isinstance(index, int) or index not in expected_indexes or index in patch_indexes:
                        raise ExternalAgentBatchError("repair patch requires unique claimed indexes", "INVALID_RESULT_ITEMS")
                    patch_indexes.add(index)
                    merged[index] = item
                items = list(merged.values())
            if batch["status"] in {"claimed", "repair_required", "needs_review"}:
                candidates, issues = self._inspect_items(batch, items)
                if issues:
                    fingerprint = hashlib.sha256(json.dumps(
                        [idempotency_key, items], sort_keys=True, ensure_ascii=False
                    ).encode()).hexdigest()
                    replayed = fingerprint == batch.get("failed_request")
                    attempts = batch.get("repair_attempts", 0) + (0 if replayed else 1)
                    batch.update({"status": "needs_review" if attempts >= 3 else "repair_required",
                                  "candidate_items": candidates, "issues": issues,
                                  "repair_attempts": attempts, "failed_request": fingerprint})
                    self._save(state)
                    return self._receipt(state, batch, replayed=replayed)
            result = self.batches.submit_translation_batch(
                task_id, session_id, batch_id, source_hash, revision, idempotency_key, items,
                request_fingerprint=request_hash,
            )
            state = self._state(task_id, session_id)
            batch = self._batch(state, batch_id)
            if batch["status"] == "committed":
                return self._receipt(state, batch, replayed=True)
            if auto_commit and state.get("cache_path"):
                return self.commit(task_id, session_id, batch_id)
            staged = self.results.validate_and_stage(state, result, idempotency_key=idempotency_key)
            receipt = self._receipt(state, batch, replayed=result["replayed"])
            receipt["staging_status"] = "replayed" if staged.get("replayed") else "staged"
            return receipt

    def _commit_one(self, task_id, session_id, batch_id, lease_id):
        state = self._state(task_id, session_id)
        batch = self._batch(state, batch_id)
        if batch["status"] == "committed":
            return self._receipt(state, batch, replayed=True)
        if batch["status"] != "submitted":
            raise ExternalAgentBatchError("batch has not passed validation", "BATCH_NOT_SUBMITTED")
        # Restage from the durable accepted submission after an interrupted staging write.
        self.results.validate_and_stage(state, batch["submission"], idempotency_key=batch["idempotency_key"])
        writer = ExternalAgentBatchWriter(
            self.batches.project_root,
            writer_lease_validator=lambda record, lease: self.leases.validate(lease, task_id, session_id),
        )
        result = writer.apply_staged_result(
            self.batches.cache_path_for_writer(task_id, session_id), self.results.read_staged(task_id),
            writer_lease_id=lease_id, batch_id=batch_id,
            receipt_path=self.batches.state_root / task_id / f"{batch_id}.commit.json",
        )
        self.batches.mark_batch_committed(task_id, session_id, batch_id, lease_id, result)
        state = self._state(task_id, session_id)
        return self._receipt(state, self._batch(state, batch_id), replayed=result.get("replayed", False))

    def commit(self, task_id, session_id, batch_id, writer_lease_id=None):
        with self.batches.transaction(task_id):
            state = self._state(task_id, session_id)
            batch = self._batch(state, batch_id)
            if batch["status"] == "committed":
                return self._receipt(state, batch, replayed=True)
            if batch["status"] != "submitted":
                raise ExternalAgentBatchError("batch has not passed validation", "BATCH_NOT_SUBMITTED")
            self.batches.cache_path_for_writer(task_id, session_id)
            lease_id = writer_lease_id
            try:
                if lease_id is None:
                    lease_id = self.leases.acquire(task_id, session_id)["writer_lease_id"]
                if not self.leases.validate(lease_id, task_id, session_id):
                    raise ExternalAgentWriterLeaseError("writer lease is invalid or expired", "WRITER_LEASE_UNAUTHORIZED")
                # Reconcile earlier interrupted replacements before changing the cache again.
                for other in state["batches"]:
                    if other["batch_id"] != batch_id and other["status"] == "submitted" and (
                        self.batches.state_root / task_id / f'{other["batch_id"]}.commit.json'
                    ).exists():
                        self._commit_one(task_id, session_id, other["batch_id"], lease_id)
                return self._commit_one(task_id, session_id, batch_id, lease_id)
            except (ExternalAgentBatchWriterError, ExternalAgentWriterLeaseError, ExternalAgentBatchResultError, OSError) as exc:
                state = self._state(task_id, session_id)
                batch = self._batch(state, batch_id)
                code = getattr(exc, "code", "WRITE_IO_ERROR")
                batch["write_error"] = {
                    "code": code,
                    "message": "Cache conflict: inspect controlled state; do not overwrite or retranslate."
                    if code in {"ITEM_CONFLICT", "SOURCE_MISMATCH", "SOURCE_HASH_MISMATCH", "REVISION_CONFLICT", "COMMIT_RECEIPT_CONFLICT"}
                    else "Write not acknowledged; retry commit with the same accepted translation after resolving the error.",
                }
                self._save(state)
                return self._receipt(state, batch)
            finally:
                if lease_id is not None:
                    self.leases.release(lease_id, task_id, session_id)
