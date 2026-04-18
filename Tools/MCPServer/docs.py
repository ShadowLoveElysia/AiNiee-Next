from __future__ import annotations

import os
from typing import Any, Dict, List


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "Tools", "MCPServer", "MCP_CLIENT_GUIDE.md")

DEFAULT_GUIDE = """# AiNiee CLI MCP Client Guide

## Overview

AiNiee CLI MCP exposes most WebServer `/api/*` capabilities as MCP tools.

Recommended first steps for any LLM client:
1. Call `get_mcp_usage_manual`
2. Call `get_mcp_security_policy`
3. Call `get_mcp_tool_catalog`
4. Then use named `api_*` tools or `upload_file`

## Security Policy

- Never bypass MCP by making direct HTTP requests to the Web UI, localhost ports, or LAN MCP/WebServer ports.
- Use MCP tools only.
- Sensitive fields such as `api_key`, `access_key`, and `secret_key` are intentionally redacted for MCP/LLM access.
- If a redacted placeholder is returned, do not treat it as a real secret.
- When changing advanced MCP settings, ask the user for a second confirmation.

## Validation Checklist

1. Read config through MCP and confirm secrets are redacted.
2. Read queue and queue raw content through MCP and confirm secrets are redacted.
3. Change a non-secret setting through MCP and confirm existing secrets are preserved.
4. Attempt to save a redacted placeholder as a new queue secret and confirm the server rejects it.
"""

SECTION_ALIASES = {
    "overview": "Overview",
    "first_steps": "First Steps",
    "security": "Security Policy",
    "security_policy": "Security Policy",
    "core_tools": "Core Tools",
    "calling_patterns": "Calling Patterns",
    "validation": "Validation Checklist",
    "validation_checklist": "Validation Checklist",
}

CATEGORY_DESCRIPTIONS = {
    "system": "System and runtime metadata.",
    "version": "Version information.",
    "config": "Current profile configuration and settings persistence.",
    "profiles": "Profile create/switch/rename/delete operations.",
    "rules_profiles": "Rules profile selection and management.",
    "glossary": "Glossary and terminology data.",
    "prompts": "Prompt template listing, reading, and saving.",
    "plugins": "Plugin status and enable toggles.",
    "task": "Task run / stop / monitor operations.",
    "queue": "Queue list, edit, run, and raw queue JSON operations.",
    "files": "File upload and temporary file management.",
    "proofread": "Proofread flows and proofread status data.",
    "analysis": "Glossary analysis and analysis status data.",
}

EXACT_ROUTE_PURPOSES = {
    "/api/config": "Read or save the active profile configuration.",
    "/api/version": "Read the current application version.",
    "/api/system/mode": "Read the current runtime mode.",
    "/api/profiles": "List available profiles.",
    "/api/profiles/switch": "Switch the active profile.",
    "/api/rules_profiles": "List available rules profiles.",
    "/api/rules_profiles/switch": "Switch the active rules profile.",
    "/api/queue": "Read or modify queue tasks.",
    "/api/queue/raw": "Read or replace the raw queue JSON document.",
    "/api/task/run": "Start a translation / polish / export task.",
    "/api/task/stop": "Stop the current running task.",
    "/api/task/status": "Read live task status, logs, and metrics.",
    "/api/files/upload": "Upload a local file to the project staging area.",
}

PREFIX_ROUTE_PURPOSES = {
    "/api/profiles/": "Manage profiles and profile files.",
    "/api/rules_profiles/": "Manage rules profiles.",
    "/api/prompts/": "List, read, or save prompt files.",
    "/api/glossary": "Read or update glossary content.",
    "/api/plugins": "Read or update plugin configuration.",
    "/api/queue/": "Operate on queue state or queue files.",
    "/api/task/": "Operate on task runtime state.",
    "/api/files/": "Operate on uploaded files or temporary files.",
    "/api/proofread": "Run or inspect proofread operations.",
    "/api/analysis": "Run or inspect analysis operations.",
}


def load_mcp_manual(section: str = "all") -> str:
    """Load the MCP client guide, optionally returning one section."""
    content = _read_guide_text()
    normalized = _normalize_section(section)

    if normalized in ("all", "*"):
        return content

    parsed = _parse_markdown_sections(content)
    target_heading = SECTION_ALIASES.get(normalized, section)

    for heading, body in parsed:
        if heading.lower() == target_heading.lower():
            return f"# AiNiee CLI MCP Client Guide\n\n## {heading}\n\n{body}".strip() + "\n"

    available = ", ".join(sorted(SECTION_ALIASES))
    return (
        f"Section '{section}' was not found.\n"
        f"Available sections: {available}\n\n"
        f"{content}"
    )


def build_security_policy() -> Dict[str, Any]:
    """Return the MCP-side security policy that LLM clients must follow."""
    return {
        "must_do": [
            "Use MCP tools only for AiNiee operations.",
            "Call get_mcp_usage_manual and get_mcp_tool_catalog before large edits when the client has no file-reading ability.",
            "Ask for a second confirmation before changing advanced MCP settings.",
            "Treat redacted secret placeholders as non-readable and non-usable values.",
        ],
        "forbidden": [
            "Do not bypass MCP by sending direct HTTP requests to the Web UI, localhost, LAN WebServer ports, or MCP HTTP endpoints.",
            "Do not try to recover, reconstruct, or infer redacted secrets from placeholders.",
            "Do not save a redacted placeholder as if it were a real API key or cloud secret.",
            "Do not use internal-only routes such as /api/internal/*.",
        ],
        "secret_behavior": {
            "redacted_fields": ["api_key", "access_key", "secret_key"],
            "placeholder": "[MCP_SECRET_REDACTED]",
            "writeback_rule": "Existing stored secrets are preserved when an MCP write payload still contains the placeholder.",
        },
    }


def build_validation_checklist() -> Dict[str, Any]:
    """Return the four security validation scenarios for MCP clients."""
    return {
        "items": [
            {
                "id": 1,
                "title": "Config Redaction",
                "goal": "Read current config through MCP and verify api_key/access_key/secret_key are redacted.",
                "recommended_tools": ["api_get_api_config"],
            },
            {
                "id": 2,
                "title": "Queue Redaction",
                "goal": "Read queue data and queue raw JSON through MCP and verify secrets are redacted.",
                "recommended_tools": ["api_get_api_queue", "api_get_api_queue_raw"],
            },
            {
                "id": 3,
                "title": "Non-Secret Save",
                "goal": "Change a non-secret setting through MCP and verify existing secrets remain intact after save.",
                "recommended_tools": ["api_get_api_config", "api_post_api_config"],
            },
            {
                "id": 4,
                "title": "Placeholder Rejection",
                "goal": "Attempt to save a redacted placeholder as a new queue API key and verify the request is rejected.",
                "recommended_tools": ["api_post_api_queue"],
            },
        ]
    }


def build_tool_catalog(
    routes: List[Dict[str, str]],
    *,
    category: str = "all",
    include_examples: bool = True,
) -> Dict[str, Any]:
    """Build a structured tool catalog for clients that cannot inspect source files."""
    normalized_category = (category or "all").strip().lower()
    route_groups = _group_routes(routes)

    categories: List[Dict[str, Any]] = []
    for group_name, group_routes in route_groups.items():
        if normalized_category not in ("all", "*") and group_name != normalized_category:
            continue

        tools = []
        for route in group_routes:
            entry = {
                "tool_name": route["tool_name"],
                "route": f'{route["method"]} {route["path"]}',
                "purpose": _describe_route(route["path"], route["method"]),
                "how_to_call": _build_call_pattern(route),
                "notes": _build_route_notes(route["path"]),
            }
            if include_examples:
                entry["example_arguments"] = _build_example_args(route)
            tools.append(entry)

        categories.append(
            {
                "category": group_name,
                "description": CATEGORY_DESCRIPTIONS.get(group_name, "Route group."),
                "tools": tools,
            }
        )

    return {
        "recommended_first_calls": [
            "get_mcp_usage_manual",
            "get_mcp_security_policy",
            "get_mcp_tool_catalog",
        ],
        "core_tools": [
            {
                "tool_name": "get_mcp_usage_manual",
                "purpose": "Read the built-in MCP usage manual. Call this first if the client cannot inspect repo files.",
            },
            {
                "tool_name": "get_mcp_security_policy",
                "purpose": "Read the no-bypass and secret-handling policy.",
            },
            {
                "tool_name": "get_mcp_tool_catalog",
                "purpose": "Read the detailed tool catalog with call patterns and examples.",
            },
            {
                "tool_name": "get_mcp_validation_checklist",
                "purpose": "Read the four MCP security validation scenarios.",
            },
            {
                "tool_name": "list_web_api_routes",
                "purpose": "Lightweight route index. Use get_mcp_tool_catalog for richer descriptions.",
            },
            {
                "tool_name": "call_web_api",
                "purpose": "Raw MCP escape hatch for public /api/* routes when no named tool is enough.",
            },
            {
                "tool_name": "upload_file",
                "purpose": "Upload a local file through the multipart file endpoint.",
            },
        ],
        "security_policy": build_security_policy(),
        "category_count": len(categories),
        "route_tool_count": sum(len(category_item["tools"]) for category_item in categories),
        "categories": categories,
    }


def get_startup_hint_text() -> str:
    """Short startup hint shown to operators for self-describing MCP clients."""
    return (
        "Guide tools: get_mcp_usage_manual / get_mcp_security_policy / "
        "get_mcp_tool_catalog / get_mcp_validation_checklist"
    )


def _read_guide_text() -> str:
    try:
        with open(GUIDE_PATH, "r", encoding="utf-8") as handle:
            return handle.read().strip() + "\n"
    except Exception:
        return DEFAULT_GUIDE


def _normalize_section(section: str) -> str:
    return (section or "all").strip().lower().replace(" ", "_")


def _parse_markdown_sections(content: str) -> List[tuple[str, str]]:
    sections: List[tuple[str, str]] = []
    current_heading = ""
    current_lines: List[str] = []

    for line in content.splitlines():
        if line.startswith("## "):
            if current_heading:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = line[3:].strip()
            current_lines = []
            continue

        if current_heading:
            current_lines.append(line)

    if current_heading:
        sections.append((current_heading, "\n".join(current_lines).strip()))

    return sections


def _group_routes(routes: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    groups: Dict[str, List[Dict[str, str]]] = {}
    for route in routes:
        category = _route_category(route["path"])
        groups.setdefault(category, []).append(route)

    return dict(sorted(groups.items(), key=lambda item: item[0]))


def _route_category(path: str) -> str:
    stripped = path.strip("/")
    parts = stripped.split("/")
    if len(parts) < 2:
        return "misc"
    return parts[1]


def _describe_route(path: str, method: str) -> str:
    if path in EXACT_ROUTE_PURPOSES:
        return EXACT_ROUTE_PURPOSES[path]

    for prefix, description in PREFIX_ROUTE_PURPOSES.items():
        if path.startswith(prefix):
            return description

    return f"Public MCP proxy for {method.upper()} {path}."


def _build_call_pattern(route: Dict[str, str]) -> Dict[str, Any]:
    path = route["path"]
    method = route["method"].upper()
    has_path_params = "{" in path and "}" in path
    uses_body = method in {"POST", "PUT", "DELETE"}

    pattern: Dict[str, Any] = {
        "path_params": "required when the route path contains {...}" if has_path_params else "not required",
        "query": "optional URL query parameters",
        "body": "JSON body object" if uses_body else "usually omitted",
    }

    if path == "/api/config":
        pattern["confirm_advanced_change"] = (
            "set to true only after the user explicitly confirms MCP host/port changes"
        )

    return pattern


def _build_route_notes(path: str) -> List[str]:
    notes = [
        "Use MCP tools only. Do not send direct HTTP requests to the Web UI or localhost ports.",
    ]

    if path == "/api/config":
        notes.append("Secrets are redacted for MCP reads. Saving a non-secret change preserves existing stored secrets.")
    if path.startswith("/api/queue"):
        notes.append("Queue API keys are redacted for MCP reads.")
    if path == "/api/queue/raw":
        notes.append("This route returns serialized JSON text; secret fields inside it are still redacted for MCP.")

    return notes


def _build_example_args(route: Dict[str, str]) -> Dict[str, Any]:
    path = route["path"]
    method = route["method"].upper()
    example: Dict[str, Any] = {}

    if "{" in path and "}" in path:
        example["path_params"] = {
            part.strip("{}"): "<value>"
            for part in path.split("/")
            if part.startswith("{") and part.endswith("}")
        }

    if method in {"POST", "PUT", "DELETE"}:
        example["body"] = _build_example_body(path)

    return example


def _build_example_body(path: str) -> Any:
    if path == "/api/config":
        return {"target_platform": "openai", "model": "gpt-4o-mini"}
    if path == "/api/profiles/switch":
        return {"profile": "default"}
    if path == "/api/rules_profiles/switch":
        return {"profile": "default"}
    if path == "/api/queue":
        return {
            "task_type": 1,
            "input_path": "/abs/path/input.txt",
            "output_path": "/abs/path/output",
            "platform": "openai",
            "model": "gpt-4o-mini",
        }
    if path == "/api/task/run":
        return {
            "task": "translate",
            "input_path": "/abs/path/input.txt",
            "output_path": "/abs/path/output",
        }
    return {"example": "fill in the JSON body required by this route"}
