"""Task approval checks without starting services or processing user files."""
from __future__ import annotations

import ast
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, Dict, Optional
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, model_validator
from ModuleFolders.Service.Agent.ExternalAgentSession import ExternalAgentSessionRegistry
from Tools.MCPServer import server
from Tools.Skills.skills.agent_skill import AgentSkill


class CapturedMCP:
    def __init__(self, *args, **kwargs):
        self.tools = {}

    def tool(self):
        def register(func):
            self.tools[func.__name__] = func
            return func
        return register


class TaskApprovalTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 27, tzinfo=timezone.utc)
        self.registry = ExternalAgentSessionRegistry(clock=lambda: self.now)
        self.enterContext(patch.object(server, "AGENT_SESSION_REGISTRY", self.registry))
        with patch("mcp.server.fastmcp.FastMCP", CapturedMCP), patch.object(
            server, "_patch_streamable_http_shutdown_for_windows"
        ):
            self.mcp = server._build_mcp_app(
                Mock(), SimpleNamespace(app=SimpleNamespace(routes=[])), "127.0.0.1", 8765, "/mcp"
            ).tools
        self.skills = AgentSkill(self.registry)

    def test_mcp_approval_works_independently_of_tui_without_config_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            with patch.object(server, "ROOT_CONFIG_FILE", str(config)):
                for state in (None, "pending", "declined", "accepted"):
                    config.write_text(json.dumps({"external_agent_onboarding_status": state}))
                    before = config.read_bytes()
                    session = self.mcp["agent_register"](
                        f"mcp-{state}", user_confirmed_external_processing=True
                    )
                    grant = self.mcp["agent_request_external_mode"](session["session_id"], f"task-{state}")
                    self.assertEqual(grant["mode_task_id"], f"task-{state}")
                    self.assertFalse(grant["config_written"])
                    self.assertEqual(config.read_bytes(), before)

    def test_registration_rejects_missing_false_and_coerced_confirmation(self):
        for value in (None, False, 1, "true"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as error:
                    self.mcp["agent_register"]("unapproved", user_confirmed_external_processing=value)
                self.assertEqual(error.exception.code, "EXTERNAL_PROCESSING_NOT_CONFIRMED")
                result = self.skills.execute({
                    "action": "register", "agent_instance_id": "unapproved",
                    "user_confirmed_external_processing": value,
                })
                self.assertEqual(result.error_code, "EXTERNAL_PROCESSING_NOT_CONFIRMED")
        self.assertEqual(len(self.registry), 0)

    def test_accepted_tui_is_not_task_approval(self):
        with patch.object(server, "_safe_load_json", return_value={"external_agent_onboarding_status": "accepted"}):
            with self.assertRaises(ValueError) as error:
                self.mcp["agent_register"]("unapproved")
        self.assertEqual(error.exception.code, "EXTERNAL_PROCESSING_NOT_CONFIRMED")

    def test_skills_approval_and_mode_do_not_read_onboarding_config(self):
        with patch("ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService.load_root_config", side_effect=AssertionError("unexpected config read")):
            session = self.skills.execute({
                "action": "register", "agent_instance_id": "skill-approved",
                "user_confirmed_external_processing": True,
            })
            self.assertTrue(session.success, session.to_dict())
            grant = self.skills.execute({
                "action": "request_external_mode", "session_id": session.data["session_id"], "task_id": "task-a",
            })
            self.assertTrue(grant.success, grant.to_dict())
            self.assertEqual(grant.data["approval_scope"], "current_task")

    def test_same_task_mode_retry_preserves_scope_and_rejects_rebinding(self):
        session = self.mcp["agent_register"]("approved", user_confirmed_external_processing=True)["session_id"]
        self.mcp["agent_request_external_mode"](session)
        self.mcp["agent_request_external_mode"](session, "task-a")
        self.mcp["agent_request_external_mode"](session, "task-a")
        self.assertEqual(self.mcp["agent_request_external_mode"](session)["mode_task_id"], "task-a")
        with self.assertRaisesRegex(ValueError, "TASK_APPROVAL_SCOPE_MISMATCH"):
            self.mcp["agent_request_external_mode"](session, "task-b")
        result = self.skills.execute({"action": "request_external_mode", "session_id": session, "task_id": "task-b"})
        self.assertEqual(result.error_code, "TASK_APPROVAL_SCOPE_MISMATCH")
        self.assertFalse(self.registry.has_external_mode(session, task_id="task-b"))

    def test_renewal_and_recovery_reuse_task_approval_with_valid_session(self):
        old = self.mcp["agent_register"]("approved", user_confirmed_external_processing=True)["session_id"]
        self.mcp["agent_request_external_mode"](old, "task-a")
        self.mcp["agent_heartbeat"](old, "approved")
        self.now += timedelta(hours=1)
        with self.assertRaises(ValueError):
            self.mcp["agent_request_external_mode"](old, "task-a")
        new = self.mcp["agent_register"]("approved", user_confirmed_external_processing=True)["session_id"]
        self.assertEqual(self.mcp["agent_request_external_mode"](new, "task-a")["mode_task_id"], "task-a")


class StructuredTaskApprovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ModuleFolders.Infrastructure.TaskContract import TaskSpec

        # Execute the real payload and endpoint without WebServer startup/import side effects.
        tree = ast.parse((ROOT / "Tools/WebServer/web_server.py").read_text(encoding="utf-8"))
        names = {"TaskPayload", "ExternalAgentTaskPayload", "request_external_agent_mode"}
        nodes = [node for node in tree.body if getattr(node, "name", None) in names]
        for node in nodes:
            node.decorator_list = []
        cls.namespace = {
            **globals(), "TaskSpec": TaskSpec,
            "is_mcp_request": lambda request: request.authorized,
        }
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / "Tools/WebServer/web_server.py"), "exec"), cls.namespace)

    def setUp(self):
        self.run = AsyncMock(return_value={"task_id": "generated-task"})
        self.namespace["run_task"] = self.run
        self.payload = self.namespace["ExternalAgentTaskPayload"]
        self.endpoint = self.namespace["request_external_agent_mode"]

    def test_missing_approval_stops_before_starting_structured_task(self):
        for fields in ({}, {"user_confirmed_external_processing": False}):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(self.endpoint(self.payload(task="translate", input_path="controlled.epub", **fields), SimpleNamespace(authorized=True)))
            self.assertEqual(error.exception.status_code, 409)
            self.assertIn("EXTERNAL_PROCESSING_NOT_CONFIRMED", error.exception.detail)
        self.run.assert_not_called()

    def test_approval_does_not_bypass_bridge_authentication(self):
        with self.assertRaises(HTTPException) as error:
            asyncio.run(self.endpoint(self.payload(task="translate", input_path="controlled.epub", user_confirmed_external_processing=True), SimpleNamespace(authorized=False)))
        self.assertEqual(error.exception.status_code, 403)
        self.run.assert_not_called()

    def test_approved_structured_task_keeps_confirmation_out_of_task_config(self):
        payload = self.payload(task="translate", input_path="controlled.epub", user_confirmed_external_processing=True)
        result = asyncio.run(self.endpoint(payload, SimpleNamespace(authorized=True)))
        self.assertEqual(result["mode_scope"], "task")
        self.assertFalse(result["config_changed"])
        self.assertIsNone(payload.execution_mode)
        forwarded = self.run.call_args.args[0]
        self.assertEqual(forwarded.execution_mode, "external_agent")
        self.assertNotIn("user_confirmed_external_processing", forwarded.model_dump())
        self.assertEqual(forwarded.to_task_spec().execution_mode, "external_agent")

    def test_confirmation_requires_a_json_boolean(self):
        for value in (None, 1, "true"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.payload(task="translate", input_path="controlled.epub", user_confirmed_external_processing=value)


if __name__ == "__main__":
    unittest.main()
