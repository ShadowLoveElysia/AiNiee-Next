export interface MangaOpenProjectSummary {
  project_id: string;
  name: string;
  page_count: number;
  project_path: string;
}

export interface MangaJob {
  job_id: string;
  page_id?: string;
  stage: string;
  status: string;
  progress: number;
  message: string;
  message_key?: string;
  message_args?: any[];
  updated_at?: string;
  page_count?: number;
  result?: Record<string, any>;
  exports?: Record<string, string>;
  export_warnings?: string[];
  error_message?: string;
  cancel_requested?: boolean;
}

export interface MangaOperationResult {
  ok: boolean;
  applied: number;
  history_seq?: number;
  updated_at?: string;
  message?: string;
}

export type MangaExportFormat = 'pdf' | 'epub' | 'cbz' | 'zip' | 'rar' | 'psd';

export interface MangaPsdExportOptions {
  page_ids?: string[];
  script_only?: boolean;
  include_blocked?: boolean;
  package?: boolean;
}

export interface MangaPsdMissingFont {
  page_id: string;
  block_id: string;
  requested: string;
}

export interface MangaExportResult {
  ok: boolean;
  path?: string | null;
  message_key?: string;
  message_args?: any[];
  blocked_pages?: MangaBlockedExportPage[];
  warnings?: string[];
  script_paths?: string[];
  psd_paths?: string[];
  missing_fonts?: MangaPsdMissingFont[];
  layer_manifest_path?: string | null;
  skipped_pages?: string[];
  output_kind?: string;
  output_count?: number;
  output_target_count?: number;
  output_failed_count?: number;
  complete?: boolean;
  progress?: Record<string, any>;
  photoshop?: {
    available: boolean;
    executable_path?: string;
    source?: string;
    checked_at?: string;
    message?: string;
  };
}

export interface MangaQualityIssue {
  code: string;
  stage: string;
  message_key: string;
  message: string;
  message_args?: any[];
  blocks_final: boolean;
}

export interface MangaPageQualityGate {
  exists: boolean;
  ok: boolean;
  final_allowed: boolean;
  blocked_from_final: boolean;
  issue_count: number;
  issues: MangaQualityIssue[];
  metrics: Record<string, any>;
  stage_modes: Record<string, any>;
  artifact_path?: string;
  artifact_url?: string;
  draft_rendered_path?: string;
  draft_rendered_url?: string;
  final_page_path?: string;
  final_page_exists?: boolean;
}

export interface MangaBlockedExportPage {
  page_id: string;
  index: number;
  status: string;
  issue_count: number;
  issues: MangaQualityIssue[];
  draft_rendered_path?: string;
  quality_gate_path?: string;
}

export interface MangaScenePageSummary {
  page_id: string;
  index: number;
  status: string;
  thumbnail_url: string;
  quality_gate?: {
    exists: boolean;
    blocked_from_final: boolean;
    issue_count: number;
    final_allowed: boolean;
  };
}

export interface MangaProjectManifestSummary {
  project_id: string;
  task_id: string;
  name: string;
  source_type: string;
  created_at: string;
  updated_at: string;
  source_lang: string;
  target_lang: string;
  profile_name: string;
  rules_profile_name: string;
  page_count: number;
  status: string;
}

export interface MangaProjectTaskConfigSummary {
  task?: string;
  input_path?: string;
  output_path?: string;
  source_lang?: string;
  target_lang?: string;
  profile_name?: string;
  rules_profile_name?: string;
  platform?: string;
  model?: string;
  api_url?: string;
  manga_ocr_engine?: string;
  manga_detect_engine?: string;
  manga_segment_engine?: string;
  manga_inpaint_engine?: string;
  manga_runtime_device?: string;
  manga_detect_device?: string;
  manga_ocr_device?: string;
  manga_inpaint_device?: string;
  web_mode?: boolean;
  manga?: boolean;
}

export interface MangaProjectSummary {
  project_id: string;
  name: string;
  page_count: number;
  current_page_id: string;
  project_path?: string;
  manifest?: MangaProjectManifestSummary;
  task_config?: MangaProjectTaskConfigSummary;
  scene?: MangaSceneSummary;
}

export interface MangaModelPackageStatus {
  model_id: string;
  stage: string;
  display_name: string;
  repo_id: string;
  repo_url: string;
  source_url?: string;
  description?: string;
  runtime_notes?: string[];
  aliases?: string[];
  hardware_tier?: string;
  quality_tier?: string;
  recommended_for?: string[];
  cautions?: string[];
  available?: boolean;
  storage_root?: string;
  cache_dir?: string;
  snapshot_path?: string;
  downloaded_at?: string;
  revision?: string;
  runtime_supported?: boolean;
  runtime_assets_path?: string;
  runtime_engine_id?: string;
}

export interface MangaModelPresetStatus {
  preset_id: string;
  display_name: string;
  description: string;
  hardware_tier: string;
  quality_tier: string;
  effect_label: string;
  model_ids: string[];
  config_overrides?: Record<string, string>;
  recommended_for?: string[];
  cautions?: string[];
  models?: MangaModelPackageStatus[];
  available_model_ids?: string[];
  missing_model_ids?: string[];
  available?: boolean;
  missing_count?: number;
  model_count?: number;
}

export interface MangaModelManagerManifest {
  default_ocr_model_id: string;
  presets: MangaModelPresetStatus[];
  models: MangaModelPackageStatus[];
}

export interface MangaRuntimeDeviceStatus {
  configured: string;
  resolved: string;
  torch_available?: boolean;
  cuda_available?: boolean;
  cuda_device_count?: number;
  cuda_device_name?: string;
  mps_available?: boolean;
  onnx_available?: boolean;
  onnx_providers?: string[];
  onnx_cuda_available?: boolean;
}

export interface MangaOcrEngineStatus {
  configured_engine_id: string;
  runtime_engine_id: string;
  configured_device?: string;
  resolved_device?: string;
  device?: MangaRuntimeDeviceStatus;
  package?: MangaModelPackageStatus;
}

export interface MangaDetectEngineStatus {
  configured_detector_id: string;
  configured_segmenter_id: string;
  configured_device?: string;
  resolved_device?: string;
  device?: MangaRuntimeDeviceStatus;
  runtime_detector_id: string;
  runtime_segmenter_id: string;
  detector_package?: MangaModelPackageStatus;
  segmenter_package?: MangaModelPackageStatus;
}

export interface MangaInpaintEngineStatus {
  configured_engine_id: string;
  runtime_engine_id: string;
  configured_device?: string;
  resolved_device?: string;
  device?: MangaRuntimeDeviceStatus;
  package?: MangaModelPackageStatus;
}

export interface MangaSceneEngineStatus {
  ocr: MangaOcrEngineStatus;
  detect: MangaDetectEngineStatus;
  inpaint: MangaInpaintEngineStatus;
}

export interface MangaRuntimeReadinessItem {
  stage: string;
  model_id: string;
  display_name?: string;
  status: string;
  blocking: boolean;
  message?: string;
  message_key?: string;
  message_args?: any[];
  action_hint_key?: string;
  action_hint_args?: any[];
  available?: boolean;
  runtime_supported?: boolean;
  runtime_engine_id?: string;
  storage_path?: string;
  snapshot_path?: string;
  required_modules?: string[];
  missing_modules?: string[];
  required_assets?: string[];
  required_asset_paths?: string[];
  missing_asset_paths?: string[];
  device?: MangaRuntimeDeviceStatus;
}

export interface MangaRuntimeReadinessReport {
  ok: boolean;
  checked_at: string;
  model_root: string;
  items: MangaRuntimeReadinessItem[];
  issue_count: number;
  summary: Record<string, any>;
}

export interface MangaSceneSummary {
  project_id: string;
  current_page_id: string;
  render_preset: string;
  export_preset: string;
  engines?: MangaSceneEngineStatus;
  runtime_readiness?: MangaRuntimeReadinessReport;
  pages: MangaScenePageSummary[];
}

export interface MangaRuntimeStatusSummary {
  engines: MangaSceneEngineStatus;
  runtime_readiness: MangaRuntimeReadinessReport;
  checked_at?: string;
  cache_ttl_ms?: number;
  cache_hit?: boolean;
  stale?: boolean;
  refreshing?: boolean;
}

export interface MangaTextBlockStyle {
  font_id?: string;
  font_family: string;
  font_size: number;
  line_spacing: number;
  fill: string;
  stroke_color: string;
  stroke_width: number;
}

export interface MangaTextBlock {
  block_id: string;
  bbox: number[];
  rotation: number;
  source_text: string;
  translation: string;
  ocr_confidence: number;
  source_direction: string;
  rendered_direction: string;
  font_prediction: string;
  source_metrics?: Record<string, any>;
  origin: string;
  placement_mode: string;
  editable: boolean;
  style: MangaTextBlockStyle;
  flags: string[];
}

export interface MangaFontCatalogEntry {
  font_id: string;
  display_name: string;
  css_family: string;
  source: string;
  available: boolean;
  path_or_url?: string;
  scripts?: string[];
  preview_text?: string;
  family?: string;
  style?: string;
  postscript_name?: string;
}

export interface MangaPageDetail {
  page_id: string;
  index: number;
  width: number;
  height: number;
  status: string;
  layers: {
    source_url: string;
    overlay_text_url: string;
    inpainted_url: string;
    rendered_url: string;
  };
  masks: {
    segment_url: string;
    bubble_url: string;
    brush_url: string;
    restore_url: string;
  };
  blocks: MangaTextBlock[];
  quality_gate?: MangaPageQualityGate;
}

export interface MangaRuntimeValidationStage {
  stage: string;
  ok: boolean;
  configured_engine_id: string;
  runtime_engine_id: string;
  used_runtime: boolean;
  execution_mode?: string;
  elapsed_ms: number;
  warning_message?: string;
  error_message?: string;
  fallback_reason?: string;
  metrics: Record<string, any>;
  artifacts: Record<string, string>;
  artifact_urls?: Record<string, string>;
}

export interface MangaRuntimeValidationResult {
  ok: boolean;
  project_id: string;
  page_id: string;
  page_index: number;
  source_path: string;
  output_dir: string;
  created_at: string;
  stages: MangaRuntimeValidationStage[];
  summary: Record<string, any>;
}

export interface MangaRuntimeValidationHistoryItem {
  run_id: string;
  created_at: string;
  ok: boolean;
  output_dir: string;
  runtime_stage_count: number;
  fallback_stage_count: number;
  seed_count: number;
}

export interface MangaRuntimeValidationDiffChange {
  key: string;
  before: any;
  after: any;
}

export interface MangaRuntimeValidationStageDiff {
  stage: string;
  changes: MangaRuntimeValidationDiffChange[];
}

export interface MangaRuntimeValidationDiffResult {
  before_run_id: string;
  after_run_id: string;
  before_created_at: string;
  after_created_at: string;
  summary_changes: MangaRuntimeValidationDiffChange[];
  stage_changes: MangaRuntimeValidationStageDiff[];
}

export interface MangaDeleteRuntimeValidationHistoryResult {
  ok: boolean;
  deleted: string;
}
