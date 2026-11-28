// DTO projections from Tools/APIServer/{contracts,responses,system_contracts}.py.
export type TaskType = 'translate' | 'polish' | 'all_in_one';
export interface RuntimeIdentity { runtime_id: string; workspace_id: string; api_version: string }
export interface SystemMode { mode: 'full' | 'monitor' }
export interface RecentProject { path: string; profile: string; rules_profile: string; pinned: boolean }
export interface RecentProjects { projects: RecentProject[]; revision: string }
export interface TaskRequest {
  task_type: TaskType;
  input_path: string;
  profile?: string;
  rules_profile?: string;
  source_lang?: string;
  target_lang?: string;
  output_path?: string;
  output_policy?: 'resume' | 'archive' | 'cancel';
  output_policy_confirmed?: boolean;
}
export interface TaskStart { success: boolean; task_id?: string | null; status: string; running: boolean; message?: string }
export interface SuccessResponse { success: boolean }
export interface TaskPreview {
  valid: boolean;
  missing_prompts: string[];
  resolved_output_path?: string | null;
  output_exists: boolean;
  cache_exists: boolean;
}
export type UploadResult = { path: string; info: string } | {
  status: 'limit_reached'; limit: number; oldest: string; buffer_available: boolean;
};
export interface QueueItem {
  task_id: string;
  revision: string;
  protected: boolean;
  locked: boolean;
  input_path: string;
  output_path: string | null;
  task_type: string;
  profile: string | null;
  source_lang: string | null;
  target_lang: string | null;
  status: string;
  is_actually_processing: boolean;
}
export interface TaskLog { timestamp: number; message: string; type: string; seq: number }
export interface TaskStatus {
  task_id: string | null;
  task_type?: string | null;
  status: string;
  running: boolean;
  started_at?: string | null;
  finished_at?: string | null;
  stats: { totalProgress: number; completedProgress: number; currentFile: string; elapsedTime: number };
  logs: TaskLog[];
  cursors: { logs: number; chart: number; comparison: number };
  cursors_reset: { logs: boolean; chart: boolean; comparison: boolean };
}
