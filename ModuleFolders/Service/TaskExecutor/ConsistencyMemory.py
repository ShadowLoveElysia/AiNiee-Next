"""A bounded checkpoint committed with the translated sequential prefix."""

import hashlib
import json

from ModuleFolders.Infrastructure.Cache.CacheItem import TranslationStatus
from ModuleFolders.Infrastructure.TaskConfig.RuntimeSnapshot import capture_runtime_snapshot


KEY = "translation_consistency_checkpoint"


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


class ConsistencyMemory:
    def __init__(self, project, config, resume):
        self.project = project
        self.rows = [(path, item) for path, file in project.files.items() for item in file.items
                     if item.translation_status != TranslationStatus.EXCLUDED]
        self.positions = {id(item): index for index, (_, item) in enumerate(self.rows)}
        self.config = config
        self.config_hash = self._config_hash()
        self.cursor, self.prefix = 0, _digest([])
        self.state = {"story_summary": "", "character_info": ""}
        self.warning = ""
        saved = project.extra.get(KEY) if resume else None
        if saved:
            self._restore(saved)
        elif resume and any(item.translation_status != TranslationStatus.UNTRANSLATED for _, item in self.rows):
            self.warning = "No consistency checkpoint exists; earlier memory cannot be reconstructed automatically."
        if self.warning or not resume:
            project.extra.pop(KEY, None)
        if not saved or self.warning:
            # Old caches may already have a completed prefix; start new memory there.
            self.cursor, self.prefix = 0, _digest([])
            for path, item in self.rows:
                if item.translation_status == TranslationStatus.UNTRANSLATED:
                    break
                self.prefix = self._next_hash(self.prefix, path, item)
                self.cursor += 1

        if any(item.translation_status != TranslationStatus.UNTRANSLATED for _, item in self.rows[self.cursor:]):
            raise ValueError(
                "Consistency recovery found completed rows after a pending gap. "
                "Use a contiguous cache prefix or disable consistency enhancement for this recovery."
            )

    def _config_hash(self):
        snapshot = capture_runtime_snapshot(self.config.get_vars())
        # Retrying smaller batches or changing throughput must not invalidate story memory.
        scheduling = {
            "user_thread_counts", "enable_async_mode", "enable_rate_limit", "custom_rpm_limit",
            "custom_tpm_limit", "request_timeout", "tokens_limit_switch", "lines_limit", "tokens_limit",
            "chunk_soft_limit_extra_lines", "line_split_optimization_mode", "retry_split_min_lines",
            "retry_count", "round_limit", "enable_smart_round_limit", "smart_round_max_limit",
            "untranslated_retry_limit", "untranslated_reduction_rate", "enable_retry_backoff",
            "enable_api_failover", "api_failover_threshold", "strict_export",
        }
        values = {key: value for key, value in snapshot["values"].items() if key not in scheduling}
        return _digest([values, snapshot["interfaces"], getattr(self.config, "model", ""),
                        getattr(self.config, "target_platform", "")])

    @staticmethod
    def _next_hash(prefix, path, item):
        return _digest([prefix, path, item.text_index, item.source_text,
                        item.translated_text, item.polished_text, item.translation_status])

    def _restore(self, saved):
        try:
            cursor = saved["cursor"]
            if (saved.get("version") != 1 or saved.get("config_hash") != self.config_hash
                    or type(cursor) is not int or not 0 <= cursor <= len(self.rows)):
                raise ValueError("checkpoint settings or boundary changed")
            prefix = _digest([])
            for path, item in self.rows[:cursor]:
                if item.translation_status == TranslationStatus.UNTRANSLATED:
                    raise ValueError("checkpoint contains pending rows")
                prefix = self._next_hash(prefix, path, item)
            if prefix != saved["prefix"]:
                raise ValueError("completed source or translation changed")
            state = saved["state"]
            if set(state) != set(self.state) or any(not isinstance(v, str) for v in state.values()):
                raise ValueError("invalid memory state")
            if sum(map(len, state.values())) > 65536:
                raise ValueError("memory state exceeds budget")
            self.cursor, self.prefix, self.state = cursor, prefix, dict(state)
        except (KeyError, TypeError, ValueError):
            self.warning = "Consistency checkpoint is stale; previous memory was discarded."

    def commit(self, items, summary, characters):
        if self._config_hash() != self.config_hash:
            raise ValueError("Consistency settings changed during the task; resume with compatible settings")
        selected = [item for item in items if id(item) in self.positions]
        positions = [self.positions[id(item)] for item in selected]
        if not positions or positions != list(range(self.cursor, self.cursor + len(positions))):
            raise ValueError("Consistency memory requires the next contiguous pending batch")
        state = dict(self.state)
        for key, value in (("story_summary", summary), ("character_info", characters)):
            if value:
                state[key] = str(value).strip()
        if sum(map(len, state.values())) > 65536:
            raise ValueError("Consistency memory exceeds the 65536 character budget")
        prefix = self.prefix
        for position in positions:
            path, item = self.rows[position]
            prefix = self._next_hash(prefix, path, item)
        cursor = self.cursor + len(positions)
        self.project.extra[KEY] = {"version": 1, "config_hash": self.config_hash,
                                   "cursor": cursor, "prefix": prefix, "state": state}
        self.cursor, self.prefix, self.state = cursor, prefix, state
        return dict(state)
