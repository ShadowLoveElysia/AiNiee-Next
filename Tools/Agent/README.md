# AiNiee headless Agent

`AgentFacade` is an optional orchestration layer. Planning reads the selected input and a redacted active configuration, then writes `tmp/agent_runs/<task_id>/plan.json` and `events.jsonl`. It never writes profiles, cache files, source files, or existing output files.

```bash
python -m Tools.Agent INPUT.txt
python -m Tools.Agent INPUT.txt --mode run --yes
ainiee agent INPUT.txt --mode plan --format jsonl
```

`Tools/Agent/runner.mjs` is a JSONL sidecar boundary for the pinned Pi packages (`@earendil-works/pi-agent-core` and `@earendil-works/pi-ai` 0.85.1). Install its package dependencies separately; when unavailable, the runner emits a structured `PI_CORE_UNAVAILABLE` event and keeps stdout valid JSONL.
