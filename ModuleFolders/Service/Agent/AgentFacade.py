"""受限的 headless Agent 门面。

该模块只负责任务画像、计划和会话事件；翻译执行仍委托现有 CLI/TaskExecutor，
因此不会产生第二套缓存、限流或任务状态系统。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import shutil
import uuid
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class AgentFacade:
    def __init__(self, project_root: str | os.PathLike[str] | None = None,
                 event_sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.project_root = Path(project_root or Path(__file__).resolve().parents[3]).resolve()
        self.event_sink = event_sink
        self._state_lock = threading.RLock()
        self._stop_requests: set[str] = set()
        self._pause_requests: set[str] = set()
        self._active_processes: dict[str, Any] = {}

    def _emit(self, event: str, **payload: Any) -> dict[str, Any]:
        item = {"event": event, "ts": datetime.now(timezone.utc).isoformat(), **payload}
        task_id = payload.get("task_id")
        if task_id:
            try:
                path = self._workspace(str(task_id)) / "events.jsonl"
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(item, ensure_ascii=False) + "\n")
            except OSError:
                pass
        if self.event_sink:
            self.event_sink(item)
        return item

    def _workspace(self, task_id: str) -> Path:
        # Task ids are persisted as directory names; reject path components so
        # callers cannot escape ``tmp/agent_runs`` through get_state/events.
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", str(task_id)):
            raise ValueError("Invalid task_id")
        path = self.project_root / "tmp" / "agent_runs" / task_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _state_path(self, task_id: str) -> Path:
        return self._workspace(task_id) / "state.json"

    def _read_state(self, task_id: str) -> dict[str, Any]:
        path = self._state_path(task_id)
        if not path.exists():
            return {"task_id": task_id, "agent_status": "unknown", "task_status": "unknown"}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"task_id": task_id, "agent_status": "error", "task_status": "error",
                    "error": "state file is unreadable"}
        return value if isinstance(value, dict) else {"task_id": task_id, "agent_status": "error", "task_status": "error"}

    def _write_state(self, task_id: str, **updates: Any) -> dict[str, Any]:
        """Persist agent/task lifecycle state inside the task workspace only."""
        with self._state_lock:
            state = self._read_state(task_id)
            state.setdefault("task_id", task_id)
            state.update(updates)
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            path = self._state_path(task_id)
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)
            return state

    def inspect_input(self, input_path: str) -> dict[str, Any]:
        path = Path(input_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise ValueError(f"Input file does not exist: {path}")
        stat = path.stat()
        content = path.read_bytes()
        sample = content[:8192]
        return {
            "path": str(path), "name": path.name, "extension": path.suffix.lower(),
            "size": stat.st_size, "sha256": hashlib.sha256(content).hexdigest(),
            "sample_chars": len(sample.decode("utf-8", errors="replace")),
            "line_count": sample.count(b"\n") + (1 if sample else 0),
        }

    def inspect_task_config(self) -> dict[str, Any]:
        """Expose a redacted snapshot of the active config for planning."""
        try:
            from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import load_effective_config, load_root_config
            config = load_effective_config(root_config=load_root_config())
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        redacted = {}
        for key, value in config.items():
            name = str(key).lower()
            redacted[key] = "[configured]" if any(token in name for token in ("api_key", "token", "secret", "password")) else value
        return redacted

    def estimate_cost(self, input_info: dict[str, Any]) -> dict[str, Any]:
        """Return a transparent planning estimate without making a model call."""
        chars = max(0, int(input_info.get("size", 0)))
        return {"estimated_input_tokens": max(1, chars // 4), "estimated_requests": max(1, chars // 4000), "currency": "configured provider"}

    def build_plan(self, input_path: str, *, mode: str = "plan") -> dict[str, Any]:
        info = self.inspect_input(input_path)
        task_id = str(uuid.uuid4())
        source = Path(info["path"])
        output = source.with_name(f"{source.stem}.agent-翻译.1{source.suffix}")
        plan = {
            "schema": "ainiee.agent.plan.v1", "task_id": task_id,
            "mode": mode, "input": info,
            "recommended": {"task_type": "translate", "threads": 0,
                             "quality_checks": ["structure", "placeholders", "terminology"]},
            "config_snapshot": self.inspect_task_config(),
            "cost_estimate": self.estimate_cost(info),
            "output_path": str(output), "requires_confirmation": True,
            "actions": ["inspect_input", "propose_config", "run_translation"],
        }
        self._workspace(task_id).joinpath("plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._write_state(task_id, agent_status="waiting_confirmation", task_status="queued",
                          plan_path="plan.json", input_path=info["path"], output_path=str(output),
                          stop_requested=False, pause_requested=False)
        self._emit("plan_ready", task_id=task_id, plan=plan)
        return plan

    def get_state(self, task_id: str) -> dict[str, Any]:
        run_dir = self._workspace(task_id)
        plan_path = run_dir / "plan.json"
        state = self._read_state(task_id)
        return {"task_id": task_id, "exists": plan_path.exists(),
                "plan": json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else None,
                "state": state, **state}

    def get_agent_translation_state(self, task_id: str) -> dict[str, Any]:
        """Return resumable state without exposing files outside the workspace."""
        return self.get_state(task_id)

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        state = self._read_state(task_id)
        return {"task_id": task_id, "status": state.get("task_status", "unknown"),
                "agent_status": state.get("agent_status", "unknown"),
                "updated_at": state.get("updated_at"),
                "stop_requested": bool(state.get("stop_requested", False)),
                "pause_requested": bool(state.get("pause_requested", False))}

    def pause_agent_translation(self, task_id: str) -> dict[str, Any]:
        self._pause_requests.add(task_id)
        state = self._write_state(task_id, agent_status="paused", task_status="paused",
                                  pause_requested=True)
        self._emit("task_paused", task_id=task_id)
        return state

    def resume_agent_translation(self, task_id: str) -> dict[str, Any]:
        self._pause_requests.discard(task_id)
        state = self._write_state(task_id, agent_status="running", task_status="running",
                                  pause_requested=False,
                                  resume_count=int(self._read_state(task_id).get("resume_count", 0)) + 1)
        self._emit("task_resumed", task_id=task_id)
        return state

    def stop_agent_translation(self, task_id: str) -> dict[str, Any]:
        self._stop_requests.add(task_id)
        process = self._active_processes.get(task_id)
        if process is not None and hasattr(process, "terminate"):
            try:
                process.terminate()
            except OSError:
                pass
        state = self._write_state(task_id, agent_status="stopped", task_status="stopped",
                                  stop_requested=True, pause_requested=False)
        self._emit("task_stop_requested", task_id=task_id)
        return state

    stop_task = stop_agent_translation

    def rerun_failed_segment(self, task_id: str, chunk_id: str) -> dict[str, Any]:
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("chunk_id is required")
        state = self._read_state(task_id)
        failed = set(state.get("failed_chunks", []))
        failed.discard(chunk_id)
        pending = set(state.get("pending_chunks", []))
        pending.add(chunk_id)
        state = self._write_state(task_id, failed_chunks=sorted(failed), pending_chunks=sorted(pending),
                                  task_status="queued", agent_status="waiting_confirmation")
        self._emit("segment_rerun_requested", task_id=task_id, chunk_id=chunk_id)
        return state

    def run(self, input_path: str, *, yes: bool = False, mode: str = "run",
            capture_output: bool = False) -> int:
        plan = self.build_plan(input_path, mode=mode)
        if not yes:
            self._emit("confirmation_required", task_id=plan["task_id"])
            return 3
        task_id = plan["task_id"]
        if task_id in self._stop_requests:
            self._write_state(task_id, agent_status="stopped", task_status="stopped", stop_requested=True)
            return 130
        output = Path(plan["output_path"])
        if output.exists():
            index = 2
            while True:
                candidate = output.with_name(f"{output.stem.rsplit('.', 1)[0]}.{index}{output.suffix}")
                if not candidate.exists():
                    output = candidate
                    break
                index += 1
        # Keep the persisted plan in sync with collision-safe output selection.
        if output != Path(plan["output_path"]):
            plan["output_path"] = str(output)
            self._workspace(plan["task_id"]).joinpath("plan.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        output_dir = self._workspace(plan["task_id"]) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        self._write_state(task_id, agent_status="running", task_status="running",
                          output_path=str(output), started_at=datetime.now(timezone.utc).isoformat())
        self._emit("task_start", task_id=task_id, output_path=str(output))
        command = [sys.executable, str(self.project_root / "ainiee_cli.py"),
                   "translate", str(Path(plan["input"]["path"])), "--yes",
                   "--output", str(output_dir)]
        try:
            run_kwargs = {"cwd": str(self.project_root), "text": True}
            if capture_output:
                run_kwargs["capture_output"] = True
            completed = subprocess.run(command, **run_kwargs)
        except Exception as exc:
            self._write_state(task_id, agent_status="error", task_status="failed", error=str(exc))
            self._emit("task_end", task_id=task_id, status="failed", exit_code=1)
            return 1
        status = "stopped" if task_id in self._stop_requests else ("completed" if completed.returncode == 0 else "failed")
        if completed.returncode == 0:
            candidates = [p for p in output_dir.rglob("*") if p.is_file()]
            if candidates and not output.exists():
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidates[0], output)
            elif not output.exists():
                status, completed = "failed", completed
        self._write_state(task_id, agent_status="ended" if status == "completed" else status,
                          task_status=status, exit_code=completed.returncode,
                          finished_at=datetime.now(timezone.utc).isoformat())
        self._emit("task_end", task_id=task_id, status=status,
                   exit_code=completed.returncode)
        return completed.returncode
