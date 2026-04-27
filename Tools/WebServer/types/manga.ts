export interface MangaProjectSummary {
  project_id: string;
  name: string;
  page_count: number;
  current_page_id: string;
}

export interface MangaJob {
  job_id: string;
  page_id?: string;
  stage: string;
  status: string;
  progress: number;
  message: string;
  updated_at?: string;
  page_count?: number;
  result?: Record<string, any>;
  error_message?: string;
}

export interface MangaOperationResult {
  ok: boolean;
  applied: number;
  history_seq?: number;
  updated_at?: string;
  message?: string;
}

export interface MangaExportResult {
  ok: boolean;
  path?: string | null;
}

export interface MangaScenePageSummary {
  page_id: string;
  index: number;
  status: string;
  thumbnail_url: string;
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

export interface MangaOcrEngineStatus {
  configured_engine_id: string;
  runtime_engine_id: string;
  package?: MangaModelPackageStatus;
}

export interface MangaDetectEngineStatus {
  configured_detector_id: string;
  configured_segmenter_id: string;
  runtime_detector_id: string;
  runtime_segmenter_id: string;
  detector_package?: MangaModelPackageStatus;
  segmenter_package?: MangaModelPackageStatus;
}

export interface MangaInpaintEngineStatus {
  configured_engine_id: string;
  runtime_engine_id: string;
  package?: MangaModelPackageStatus;
}

export interface MangaSceneEngineStatus {
  ocr: MangaOcrEngineStatus;
  detect: MangaDetectEngineStatus;
  inpaint: MangaInpaintEngineStatus;
}

export interface MangaSceneSummary {
  project_id: string;
  current_page_id: string;
  render_preset: string;
  export_preset: string;
  engines?: MangaSceneEngineStatus;
  pages: MangaScenePageSummary[];
}

export interface MangaTextBlockStyle {
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
  origin: string;
  placement_mode: string;
  editable: boolean;
  style: MangaTextBlockStyle;
  flags: string[];
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
  };
  blocks: MangaTextBlock[];
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
  metrics: Record<string, any>;
  artifacts: Record<string, string>;
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
