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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class AgentFacade:
    def __init__(self, project_root: str | os.PathLike[str] | None = None,
                 event_sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.project_root = Path(project_root or Path(__file__).resolve().parents[3]).resolve()
        self.event_sink = event_sink

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
        path = self.project_root / "tmp" / "agent_runs" / task_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def inspect_input(self, input_path: str) -> dict[str, Any]:
        path = Path(input_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise ValueError(f"Input file does not exist: {path}")
        stat = path.stat()
        sample = path.read_bytes()[:8192]
        return {
            "path": str(path), "name": path.name, "extension": path.suffix.lower(),
            "size": stat.st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
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
        self._emit("plan_ready", task_id=task_id, plan=plan)
        return plan

    def get_state(self, task_id: str) -> dict[str, Any]:
        run_dir = self._workspace(task_id)
        plan_path = run_dir / "plan.json"
        return {"task_id": task_id, "exists": plan_path.exists(),
                "plan": json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else None}

    def run(self, input_path: str, *, yes: bool = False, mode: str = "run") -> int:
        plan = self.build_plan(input_path, mode=mode)
        if not yes:
            self._emit("confirmation_required", task_id=plan["task_id"])
            return 3
        output = Path(plan["output_path"])
        if output.exists():
            index = 2
            while True:
                candidate = output.with_name(f"{output.stem.rsplit('.', 1)[0]}.{index}{output.suffix}")
                if not candidate.exists():
                    output = candidate
                    break
                index += 1
        output_dir = self._workspace(plan["task_id"]) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        self._emit("task_start", task_id=plan["task_id"], output_path=str(output))
        command = [sys.executable, str(self.project_root / "ainiee_cli.py"),
                   "translate", str(input_path), "--yes", "--output", str(output_dir)]
        completed = subprocess.run(command, cwd=str(self.project_root), text=True)
        status = "completed" if completed.returncode == 0 else "failed"
        if completed.returncode == 0:
            candidates = [p for p in output_dir.rglob("*") if p.is_file()]
            if candidates and not output.exists():
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidates[0], output)
            elif not output.exists():
                status, completed = "failed", completed
        self._emit("task_end", task_id=plan["task_id"], status=status,
                   exit_code=completed.returncode)
        return completed.returncode
