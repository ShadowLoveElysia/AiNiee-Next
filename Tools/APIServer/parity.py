"""Map interactive entry points to their public business operations."""

_FEATURES = (
    ("translation_polishing_export", "CLIMenu.run_task/run_export_only", ["/api/task/preview", "/api/task/run", "/api/task/status", "/api/task/stop"]),
    ("runtime_controls", "CLIMenu.run_task keyboard controls", ["/api/task/control", "/api/task/control/{command_id}"]),
    ("manga_translation", "CLIMenu.run_manga_translation", ["/api/task/run", "/api/manga"]),
    ("video_and_live", "CLIMenu.start_live_translation/start_video_translation", ["/api/media/sessions/{mode}", "/api/media/sessions/status"]),
    ("media_configuration", "Media.tui_settings/desktop setup", ["/api/media/settings", "/api/media/models", "/api/media/runtime/{action}"]),
    ("editor_and_proofread", "EditorMenu/AIProofreadMenu", ["/api/cache/items", "/api/review/cache/items", "/api/review/proofread/check", "/api/proofread/suggestions"]),
    ("glossary", "GlossaryMenu.run_glossary_analysis_task", ["/api/review/glossary/scan", "/api/review/glossary/analyze", "/api/review/glossary/translate"]),
    ("rules_and_prompts", "GlossaryMenu.prompt_menu", ["/api/review/rules/preview", "/api/review/rules/import", "/api/review/rules/export", "/api/review/prompt/test"]),
    ("configuration", "SettingsMenu/APIManager", ["/api/config", "/api/system/settings-schema", "/api/system/platforms/validate", "/api/system/platforms/models"]),
    ("profiles", "ProfileMenu/GlossaryMenu.rules_profiles_menu", ["/api/profiles", "/api/system/profile-documents/{name}", "/api/review/rules/create"]),
    ("queue", "TaskQueueMenu", ["/api/queue", "/api/queue/raw", "/api/queue/reorder", "/api/queue/run"]),
    ("automation", "AutomationMenu", ["/api/automation/configuration", "/api/automation/scheduler/start", "/api/automation/watch/start", "/api/automation/workflows/start"]),
    ("recent_projects", "RecentProjectsMenu", ["/api/system/recent-projects", "/api/system/recent-projects/activate"]),
    ("plugins", "PluginSettingsMenu", ["/api/plugins", "/api/plugins/toggle"]),
    ("diagnostics", "DiagnosticMenu", ["/api/system/diagnostics/knowledge", "/api/system/diagnostics/run"]),
    ("updates_and_manga_runtime", "UpdateManager/MangaRuntimeMenu", ["/api/maintenance/updates", "/api/maintenance/updates/start", "/api/maintenance/manga/runtime/install", "/api/maintenance/manga/defaults"]),
    ("services", "WebRuntimeBridge/MCPRuntimeBridge/SkillsRuntimeBridge", ["/api/system/web", "/api/system/services", "/api/system/services/{name}/start", "/api/system/services/{name}/stop"]),
)


def capability_matrix():
    return [{"feature": feature, "tui_entry": entry, "api_paths": paths, "availability": "runtime-dependent"}
            for feature, entry, paths in _FEATURES]
