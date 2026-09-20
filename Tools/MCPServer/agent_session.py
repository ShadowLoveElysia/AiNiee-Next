"""Compatibility import for the shared external Agent session registry.

MCP and Skills must observe one process-local session registry. The canonical
implementation lives in the transport-independent Agent service module.
"""
from ModuleFolders.Service.Agent.ExternalAgentSession import (
    DEFAULT_LEASE_SECONDS,
    MAX_LEASE_SECONDS,
    MIN_LEASE_SECONDS,
    ExternalAgentSessionError,
    ExternalAgentSessionRegistry,
    SessionError,
    get_external_agent_session_registry,
)

AgentSessionRegistry = ExternalAgentSessionRegistry

__all__ = [
    "DEFAULT_LEASE_SECONDS",
    "MAX_LEASE_SECONDS",
    "MIN_LEASE_SECONDS",
    "ExternalAgentSessionError",
    "ExternalAgentSessionRegistry",
    "SessionError",
    "AgentSessionRegistry",
    "get_external_agent_session_registry",
]
