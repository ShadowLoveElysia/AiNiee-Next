"""External Agent session and batch lifecycle Skill.

The adapter deliberately contains no translation or cache business logic. It
only authenticates the active Agent session, applies the Skills workspace path
policy, and delegates batch/result/commit operations to the shared services
used by MCP.
"""
from __future__ import annotations

from typing import Any, Dict

from ModuleFolders.Service.Agent.ExternalAgentWorkflow import ExternalAgentWorkflow
from ModuleFolders.Service.Agent.ExternalAgentBatch import (
    ExternalAgentBatchError,
    ExternalAgentBatchService,
    get_external_agent_batch_service,
)
from ModuleFolders.Service.Agent.ExternalAgentBatchResult import (
    ExternalAgentBatchResultError,
    ExternalAgentBatchResultService,
    get_external_agent_batch_result_service,
)
from ModuleFolders.Service.Agent.ExternalAgentBatchWriter import (
    ExternalAgentBatchWriterError,
)
from ModuleFolders.Service.Agent.ExternalAgentSession import (
    ExternalAgentSessionError,
    ExternalAgentSessionRegistry,
    get_external_agent_session_registry,
)
from ModuleFolders.Service.Agent.ExternalAgentWriterLease import (
    ExternalAgentWriterLeaseError,
    ExternalAgentWriterLeaseRegistry,
    get_external_agent_writer_lease_registry,
)
from Tools.Skills.skill_base import (
    Skill,
    SkillMeta,
    SkillParameter,
    SkillResult,
    normalize_skill_action,
    reject_unknown_skill_fields,
)
from Tools.Skills.skills.common import SkillPathError, validate_skill_path
from Tools.MCPServer.file_tools import (
    FileToolError,
    get_agent_read_batch_service,
)


class AgentSkill(Skill):
    """Expose session and controlled external-Agent batch operations."""

    def __init__(
        self,
        registry: ExternalAgentSessionRegistry | None = None,
        *,
        batch_service: ExternalAgentBatchService | None = None,
        result_service: ExternalAgentBatchResultService | None = None,
        writer_lease_registry: ExternalAgentWriterLeaseRegistry | None = None,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._batch_service = batch_service
        self._result_service = result_service
        self._writer_lease_registry = writer_lease_registry

    @property
    def registry(self) -> ExternalAgentSessionRegistry:
        if self._registry is None:
            self._registry = get_external_agent_session_registry()
        return self._registry

    @property
    def batch_service(self) -> ExternalAgentBatchService:
        if self._batch_service is None:
            self._batch_service = get_external_agent_batch_service()
        return self._batch_service

    @property
    def result_service(self) -> ExternalAgentBatchResultService:
        if self._result_service is None:
            self._result_service = get_external_agent_batch_result_service()
        return self._result_service

    @property
    def writer_lease_registry(self) -> ExternalAgentWriterLeaseRegistry:
        if self._writer_lease_registry is None:
            self._writer_lease_registry = get_external_agent_writer_lease_registry()
        return self._writer_lease_registry

    @property
    def meta(self) -> SkillMeta:
        return SkillMeta(
            name="agent_session",
            description=(
                "Register, renew, recover, inspect, or disconnect an external Agent session; "
                "prepare and exchange controlled translation and read-analysis batches. "
                "Results are validated and automatically committed by the guarded writer; "
                "repair_required needs corrected items, write_error needs commit retry. "
                "TXT without cache stays staged; this adapter does not export final files."
            ),
            category="agent",
            parameters=[
                SkillParameter(
                    name="action",
                    description=(
                        "Operation: register, heartbeat, status, unregister, prepare_project, "
                        "prepare_cache_project, project_status, claim_batch, claim_batches, submit_translation_batch, pending_work, get_batch_repair, "
                        "release_batch, resume_task, recover_task, acquire_writer_lease, commit_cache_batch, or request_external_mode."
                    ),
                    type="string",
                    required=True,
                    enum=[
                        "register", "heartbeat", "status", "unregister",
                        "prepare_project", "prepare_cache_project", "project_status",
                        "claim_batch", "claim_batches", "submit_translation_batch", "release_batch", "pending_work", "get_batch_repair",
                        "acquire_writer_lease", "commit_cache_batch", "request_external_mode", "resume_task", "recover_task",
                        "prepare_read_batches", "claim_read_batch", "read_batch_status", "complete_read_batch",
                        "release_read_batch",
                    ],
                ),
                SkillParameter(name="session_id", description="Session lease id.", type="string"),
                SkillParameter(name="agent_instance_id", description="Stable external Agent instance id.", type="string"),
                SkillParameter(name="protocol_version", description="Agent session protocol version.", type="string"),
                SkillParameter(name="client_name", description="External client name.", type="string"),
                SkillParameter(name="client_version", description="External client version.", type="string"),
                SkillParameter(name="capabilities", description="Declared capabilities.", type="array"),
                SkillParameter(name="supported_modes", description="Supported AiNiee execution modes.", type="array"),
                SkillParameter(name="transport", description="Transport label (for diagnostics only).", type="string"),
                SkillParameter(name="requested_lease_seconds", description="Requested session lease in seconds (default 120, maximum 3600 / 60 minutes).", type="integer"),
                SkillParameter(name="user_confirmed_external_processing", description="User confirmed sending work to the external Agent.", type="boolean"),
                SkillParameter(name="active_only", description="Only return a live session for status.", type="boolean"),
                SkillParameter(name="last_task_id", description="Optional task id carried by heartbeat.", type="string"),
                SkillParameter(name="active_batch_id", description="Optional batch id carried by heartbeat.", type="string"),
                SkillParameter(name="reason", description="Disconnect reason.", type="string"),
                SkillParameter(name="input_path", description="Controlled ordinary TXT file for a direct line batch; Web-prewarmed structured tasks use their cache path.", type="string"),
                SkillParameter(name="cache_path", description="Controlled AinieeCacheData.json for a cache-backed project.", type="string"),
                SkillParameter(name="task_id", description="Stable external Agent task id.", type="string"),
                SkillParameter(name="batch_id", description="Batch id returned by claim_batch.", type="string"),
                SkillParameter(name="batch_ids", description="Optional batch ids for bounded parallel fan-out; ids may be out of order.", type="array"),
                SkillParameter(name="max_batches", description="Omit to use the TUI external_agent_max_batches setting (default 8, configurable above 8). A smaller request is allowed; changing the setting requires explicit user consent.", type="integer"),
                SkillParameter(name="execution_mode", description="Must be external_agent for this protocol.", type="string", default="external_agent", enum=["external_agent"]),
                SkillParameter(name="source_hash", description="SHA-256 hash returned for the claimed batch.", type="string"),
                SkillParameter(name="revision", description="Task revision returned for the claimed batch.", type="integer"),
                SkillParameter(name="idempotency_key", description="Stable key for safe submission retries.", type="string"),
                SkillParameter(name="items", description="Array of {index: claimed index, translation: translated text}. Complete batch, or corrected indexes when repair=true.", type="array"),
                SkillParameter(name="auto_commit", description="Automatically validate and commit cache results; default true.", type="boolean", default=True),
                SkillParameter(name="repair", description="Merge corrected indexes into a rejected candidate; use a new idempotency key for changes.", type="boolean", default=False),
                SkillParameter(name="writer_lease_id", description="Lease returned by acquire_writer_lease.", type="string"),
                SkillParameter(name="mode_task_id", description="Optional task scope for request_external_mode.", type="string"),
                SkillParameter(name="previous_session_id", description="Previous disconnected session id for resume_task.", type="string"),
                SkillParameter(name="expected_input_hash", description="Optional source hash for recovery validation.", type="string"),
                SkillParameter(name="expected_cache_revision", description="Optional cache hash for recovery validation.", type="string"),
                SkillParameter(name="path", description="Controlled source file for read-only Agent analysis batches.", type="string"),
                SkillParameter(name="project_type", description="Optional format-aware source project type.", type="string", default="auto"),
            ],
            examples=[
                {"action": "register", "agent_instance_id": "desktop-1", "supported_modes": ["external_agent"], "capabilities": ["translation"], "user_confirmed_external_processing": True},
                {"action": "prepare_project", "input_path": "Resource/input.txt", "task_id": "task_1", "session_id": "sess_example"},
                {"action": "claim_batch", "task_id": "task_1", "session_id": "sess_example"},
                {"action": "claim_batches", "task_id": "task_1", "session_id": "sess_example"},
                {"action": "submit_translation_batch", "task_id": "task_1", "session_id": "sess_example", "batch_id": "batch_000001", "source_hash": "<sha256>", "revision": 1, "idempotency_key": "task_1_batch_1", "items": []},
            ],
        )

    @staticmethod
    def _error(exc: Exception) -> SkillResult:
        return SkillResult.fail(str(exc), getattr(exc, "code", "SKILL_ERROR"))

    @staticmethod
    def _onboarding_accepted() -> bool:
        try:
            from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import load_root_config

            return load_root_config().get("external_agent_onboarding_status") == "accepted"
        except Exception:
            return False

    def _require_session(self, session_id: Any) -> SkillResult | None:
        if not isinstance(session_id, str) or not session_id.strip():
            return SkillResult.fail("session_id is required.", "MISSING_PARAM")
        try:
            if hasattr(self.registry, "status"):
                record = self.registry.status(session_id)
            else:
                record = self.registry.get(session_id, active_only=True)
        except ExternalAgentSessionError as exc:
            return self._error(exc)
        if not isinstance(record, dict) or record.get("state") != "registered":
            return SkillResult.fail("Agent session is not registered or has expired.", "AGENT_SESSION_REQUIRED")
        return None

    def _require_external_mode(self, session_id: Any, task_id: Any = None) -> SkillResult | None:
        session_error = self._require_session(session_id)
        if session_error:
            return session_error
        try:
            checker = getattr(self.registry, "has_external_mode", None)
            if not callable(checker) or not checker(session_id, task_id=task_id):
                return SkillResult.fail(
                    "Call request_external_mode through the Skills port before task operations.",
                    "EXTERNAL_MODE_REQUIRED",
                )
        except ExternalAgentSessionError as exc:
            return self._error(exc)
        return None

    @staticmethod
    def _required(args: Dict[str, Any], *names: str) -> SkillResult | None:
        missing = [name for name in names if not isinstance(args.get(name), str) or not args[name].strip()]
        if missing:
            return SkillResult.fail(f"Missing required parameter: {', '.join(missing)}", "MISSING_PARAM")
        return None

    @staticmethod
    def _safe_input_path(value: Any, *, field_name: str = "input_path") -> str:
        return validate_skill_path(value, field_name=field_name, must_exist=True, expect_file=True)

    def _execute_batch(self, action: str, args: Dict[str, Any]) -> SkillResult:
        session_id = args.get("session_id")
        missing = self._required(args, "session_id")
        if missing:
            return missing
        session_error = self._require_external_mode(session_id, args.get("task_id"))
        if session_error:
            return session_error

        try:
            if action == "prepare_project":
                missing = self._required(args, "input_path", "task_id")
                if missing:
                    return missing
                input_path = self._safe_input_path(args["input_path"])
                return SkillResult.ok(self.batch_service.prepare_project(
                    input_path, args["task_id"], session_id, args.get("execution_mode", "external_agent")
                ))

            if action == "prepare_cache_project":
                missing = self._required(args, "cache_path", "task_id")
                if missing:
                    return missing
                cache_path = self._safe_input_path(args["cache_path"], field_name="cache_path")
                return SkillResult.ok(self.batch_service.prepare_cache_project(
                    cache_path, args["task_id"], session_id, args.get("execution_mode", "external_agent")
                ))

            if action == "project_status":
                missing = self._required(args, "task_id")
                if missing:
                    return missing
                return SkillResult.ok(self.batch_service.get_project(args["task_id"], session_id))

            if action == "claim_batch":
                missing = self._required(args, "task_id")
                if missing:
                    return missing
                return SkillResult.ok(self.batch_service.claim_batch(args["task_id"], session_id, args.get("batch_id")))

            if action == "claim_batches":
                missing = self._required(args, "task_id")
                if missing:
                    return missing
                return SkillResult.ok(self.batch_service.claim_batches(
                    args["task_id"], session_id, args.get("batch_ids"),
                    max_batches=args.get("max_batches"),
                ))

            if action == "release_batch":
                missing = self._required(args, "task_id", "batch_id")
                if missing:
                    return missing
                return SkillResult.ok(self.batch_service.release_batch(args["task_id"], session_id, args["batch_id"]))

            if action == "resume_task":
                missing = self._required(args, "task_id", "previous_session_id")
                if missing:
                    return missing
                previous_session_id = args["previous_session_id"]
                if previous_session_id == session_id:
                    return SkillResult.fail(
                        "a resumed task requires a different session",
                        "SESSION_ALREADY_ACTIVE",
                    )
                previous = self.registry.status(previous_session_id)
                if isinstance(previous, dict) and previous.get("state") == "registered":
                    return SkillResult.fail(
                        "Previous session must be disconnected or expired.",
                        "SESSION_STILL_ACTIVE",
                    )
                # The prior record remains an audit snapshot after disconnect;
                # require that it was granted external mode before takeover.
                if isinstance(previous, dict) and previous.get("mode_status") != "granted":
                    return SkillResult.fail(
                        "Previous session did not hold external-agent mode.",
                        "PREVIOUS_EXTERNAL_MODE_REQUIRED",
                    )
                if isinstance(previous, dict) and previous.get("mode_task_id") not in (None, args["task_id"]):
                    return SkillResult.fail(
                        "Previous session external-agent mode was granted for another task.",
                        "PREVIOUS_MODE_TASK_MISMATCH",
                    )
                mode_error = self._require_external_mode(session_id, args["task_id"])
                if mode_error:
                    return mode_error
                resumed = self.batch_service.resume_task(
                    args["task_id"], previous_session_id, session_id
                )
                resumed["released_writer_leases"] = self.writer_lease_registry.release_task(
                    args["task_id"], previous_session_id
                )
                resumed["writer_lease_required"] = True
                return SkillResult.ok(resumed)

            if action == "recover_task":
                missing = self._required(args, "task_id")
                if missing:
                    return missing
                return SkillResult.ok(self.batch_service.recover_task(
                    args["task_id"], session_id,
                    expected_input_hash=args.get("expected_input_hash"),
                    expected_cache_revision=args.get("expected_cache_revision"),
                ))

            if action == "submit_translation_batch":
                missing = self._required(args, "task_id", "batch_id", "source_hash", "idempotency_key")
                if missing:
                    return missing
                for field in ("revision", "items"):
                    if field not in args:
                        return SkillResult.fail(f"Missing required parameter: {field}", "MISSING_PARAM")
                result = ExternalAgentWorkflow(self.batch_service, self.result_service, self.writer_lease_registry).submit(
                    args["task_id"], session_id, args["batch_id"], args["source_hash"],
                    args["revision"], args["idempotency_key"], args["items"],
                    auto_commit=args.get("auto_commit", True), repair=args.get("repair", False),
                )
                return SkillResult.ok(result)

            if action in {"pending_work", "get_batch_repair"}:
                missing = self._required(args, "task_id", *(["batch_id"] if action == "get_batch_repair" else []))
                if missing:
                    return missing
                workflow = ExternalAgentWorkflow(self.batch_service, self.result_service, self.writer_lease_registry)
                return SkillResult.ok(
                    workflow.pending_work(args["task_id"], session_id) if action == "pending_work" else
                    workflow.get_repair(args["task_id"], session_id, args["batch_id"])
                )

            if action == "acquire_writer_lease":
                missing = self._required(args, "task_id")
                if missing:
                    return missing
                return SkillResult.ok(self.writer_lease_registry.acquire(args["task_id"], session_id))

            if action == "commit_cache_batch":
                missing = self._required(args, "task_id", "batch_id")
                if missing:
                    return missing
                return SkillResult.ok(ExternalAgentWorkflow(
                    self.batch_service, self.result_service, self.writer_lease_registry
                ).commit(args["task_id"], session_id, args["batch_id"], args.get("writer_lease_id")))

            return SkillResult.fail(f"Unknown agent batch action: {action}", "INVALID_ACTION")
        except (ExternalAgentSessionError, ExternalAgentBatchError, ExternalAgentBatchResultError, ExternalAgentBatchWriterError, ExternalAgentWriterLeaseError, SkillPathError, ValueError) as exc:
            return self._error(exc)

    def execute(self, args: Dict[str, Any]) -> SkillResult:
        allowed = {
            "action", "session_id", "agent_instance_id", "protocol_version", "client_name", "client_version",
            "capabilities", "supported_modes", "transport", "requested_lease_seconds",
            "user_confirmed_external_processing", "active_only", "last_task_id", "active_batch_id", "reason",
            "input_path", "cache_path", "task_id", "batch_id", "batch_ids", "max_batches", "execution_mode", "source_hash", "revision",
            "idempotency_key", "items", "writer_lease_id", "mode_task_id", "previous_session_id", "expected_input_hash", "expected_cache_revision",
            "path", "project_type", "auto_commit", "repair",
        }
        invalid = reject_unknown_skill_fields(args, allowed, skill_name="agent_session")
        if invalid:
            return invalid
        action = normalize_skill_action(args)
        if action is None:
            return SkillResult.fail("action must be a string.", "INVALID_ACTION")

        if action in {
            "prepare_project", "prepare_cache_project", "project_status", "claim_batch", "claim_batches", "submit_translation_batch",
            "release_batch", "resume_task", "recover_task", "acquire_writer_lease", "commit_cache_batch", "pending_work", "get_batch_repair",
        }:
            return self._execute_batch(action, args)

        if action in {
            "prepare_read_batches", "claim_read_batch", "read_batch_status", "complete_read_batch", "release_read_batch",
        }:
            missing = self._required(args, "session_id")
            if missing:
                return missing
            mode_error = self._require_external_mode(args["session_id"], args.get("task_id"))
            if mode_error:
                return mode_error
            try:
                service = get_agent_read_batch_service()
                if action == "prepare_read_batches":
                    required = self._required(args, "path", "task_id")
                    if required:
                        return required
                    return SkillResult.ok(service.prepare(
                        validate_skill_path(args["path"], field_name="path", must_exist=True, expect_file=True),
                        args["task_id"], args["session_id"], project_type=args.get("project_type", "auto"),
                    ))
                if action == "claim_read_batch":
                    required = self._required(args, "task_id")
                    if required:
                        return required
                    return SkillResult.ok(service.claim(args["task_id"], args["session_id"], args.get("batch_id")))
                if action == "read_batch_status":
                    required = self._required(args, "task_id")
                    if required:
                        return required
                    return SkillResult.ok(service.status(args["task_id"], args["session_id"]))
                if action == "release_read_batch":
                    required = self._required(args, "task_id", "batch_id")
                    if required:
                        return required
                    return SkillResult.ok(service.release(args["task_id"], args["session_id"], args["batch_id"]))
                required = self._required(args, "task_id", "batch_id")
                if required:
                    return required
                return SkillResult.ok(service.complete(args["task_id"], args["session_id"], args["batch_id"]))
            except (FileToolError, SkillPathError, ValueError) as exc:
                return self._error(exc)

        try:
            session_id = args.get("session_id")
            if action == "register":
                if not self._onboarding_accepted():
                    return SkillResult.fail(
                        "External Agent onboarding has not been accepted by the user.",
                        "ONBOARDING_NOT_ACCEPTED",
                    )
                fields = {
                    key: args[key]
                    for key in (
                        "agent_instance_id", "protocol_version", "client_name", "client_version",
                        "capabilities", "supported_modes", "transport", "requested_lease_seconds",
                        "user_confirmed_external_processing",
                    )
                    if key in args
                }
                return SkillResult.ok(self.registry.register(fields))

            if action == "request_external_mode":
                if not self._onboarding_accepted():
                    return SkillResult.fail(
                        "External Agent onboarding has not been accepted by the user.",
                        "ONBOARDING_NOT_ACCEPTED",
                    )
                missing = self._required(args, "session_id")
                if missing:
                    return missing
                return SkillResult.ok(
                    self.registry.request_external_mode(
                        session_id,
                        task_id=args.get("mode_task_id") or args.get("task_id"),
                    )
                )

            if action == "heartbeat":
                if "agent_instance_id" not in args:
                    return SkillResult.fail("Missing required parameter: agent_instance_id", "MISSING_PARAM")
                fields = {key: args[key] for key in ("last_task_id", "active_batch_id") if key in args}
                return SkillResult.ok(self.registry.heartbeat(session_id, agent_instance_id=args.get("agent_instance_id"), **fields))

            if action == "unregister":
                return SkillResult.ok(self.registry.unregister(session_id, agent_instance_id=args.get("agent_instance_id"), reason=args.get("reason", "client_shutdown")))

            if action == "status":
                active_only = args.get("active_only", False)
                if not isinstance(active_only, bool):
                    return SkillResult.fail("active_only must be a boolean.", "INVALID_ARGUMENTS")
                if session_id is not None:
                    if not isinstance(session_id, str) or not session_id.strip():
                        return SkillResult.fail("session_id must be a non-empty string.", "INVALID_ARGUMENTS")
                    result = self.registry.get(session_id, active_only=active_only)
                    if result is None:
                        return SkillResult.fail("session does not exist", "SESSION_NOT_FOUND")
                    return SkillResult.ok(result)
                if hasattr(self.registry, "status"):
                    result = self.registry.status()
                    if isinstance(result, dict):
                        return SkillResult.ok(result)
                return SkillResult.ok({"sessions": [], "count": 0, "active_count": len(self.registry)})

            return SkillResult.fail(f"Unknown agent_session action: {action}", "INVALID_ACTION")
        except (ExternalAgentSessionError, TypeError, ValueError) as exc:
            return self._error(exc)


__all__ = ["AgentSkill"]
