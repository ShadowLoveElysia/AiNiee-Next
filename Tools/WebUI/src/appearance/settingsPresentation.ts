import type { SettingDescription } from '../api/settingsContracts';

// Presentation choices belong to WebUI; the shared registry and TUI levels remain authoritative.
const advancedKeys = new Set([
  'language_filter_minority_ratio_threshold',
  'chunk_soft_limit_extra_lines', 'line_split_optimization_mode', 'retry_split_min_lines',
  'sparse_completion_previous_lines', 'sparse_completion_lookahead_lines', 'term_translation_rounds',
  'character_recall_context_lines', 'character_recall_lookahead_lines',
  'few_shot_and_example_switch', 'auto_process_text_code_segment',
  'enable_stream_api', 'enable_async_mode',
  'api_failover_threshold', 'critical_error_threshold',
  'newline_character_count_check',
  'return_to_original_text_check', 'residual_original_text_check', 'reply_format_check',
  'proofread_context_lines', 'proofread_batch_size', 'proofread_confidence_threshold',
  'proofread_report_mode', 'proofread_archive_limit', 'proofread_save_raw_responses',
  'cache_save_interval', 'cache_backup_limit', 'enable_session_logging',
  'enable_operation_logging',
  'epub_language_update_mode', 'epub_language_follow_source',
  'sync_output_metadata_title', 'sync_export_metadata_title', 'keep_original_encoding',
  'media_device', 'media_context_segments', 'media_cache_ram_mib', 'media_recognition_device',
  'media_asr_endpoint', 'media_video_encoder',
  'external_agent_max_batches',
]);

export const batchKeys = new Set(['lines_limit', 'tokens_limit_switch', 'tokens_limit']);
export const isAdvancedSetting = (field: Pick<SettingDescription, 'key'>): boolean => advancedKeys.has(field.key);

const tuiOnlyKeys = new Set([
  'interface_language', 'main_menu_layout', 'external_agent_onboarding',
  'enable_background_prewarm', 'enable_github_status_bar', 'enable_github_promotion', 'enable_auto_update',
]);
export const isGuiSetting = (field: Pick<SettingDescription, 'key'>): boolean => !tuiOnlyKeys.has(field.key);
