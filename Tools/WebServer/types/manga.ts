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

export interface MangaSceneSummary {
  project_id: string;
  current_page_id: string;
  render_preset: string;
  export_preset: string;
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
