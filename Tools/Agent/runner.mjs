#!/usr/bin/env node
/**
 * Headless JSONL transport skeleton for the optional Pi Agent core.
 * AiNiee remains the authority for domain tools and task execution.
 */
import readline from "node:readline";

const emit = (value) => process.stdout.write(JSON.stringify(value) + "\n");
let agent = null;
try {
  const core = await import("@earendil-works/pi-agent-core");
  agent = core.Agent;
} catch (error) {
  emit({ type: "error", code: "PI_CORE_UNAVAILABLE", message: String(error?.message || error) });
}

emit({ type: "agent_start", runtime: "pi-agent-core", available: Boolean(agent) });
const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of input) {
  if (!line.trim()) continue;
  let command;
  try { command = JSON.parse(line); } catch { emit({ type: "error", code: "INVALID_JSON" }); continue; }
  const requestId = command.request_id;
  if (!["prompt", "steer", "follow_up", "abort", "get_state", "new_session"].includes(command.type)) {
    emit({ type: "error", request_id: requestId, code: "UNSUPPORTED_COMMAND" });
    continue;
  }
  if (command.type === "abort") {
    emit({ type: "agent_end", request_id: requestId, status: "aborted" });
  } else if (command.type === "get_state") {
    emit({ type: "state", request_id: requestId, available: Boolean(agent), status: "idle" });
  } else {
    emit({ type: "message_update", request_id: requestId, status: "accepted" });
  }
}
