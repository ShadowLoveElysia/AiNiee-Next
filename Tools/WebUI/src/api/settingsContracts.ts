export interface SettingDescription {
  key: string;
  default: unknown;
  level: string;
  type: 'string' | 'int' | 'float' | 'bool' | 'list' | 'dict' | 'path' | 'choice';
  category: string;
  label_key: string;
  description_key: string;
  choices: unknown[];
  minimum: number | null;
  maximum: number | null;
  depends_on: string | null;
  submenu: string;
  online_only: boolean;
}

export interface SettingsValidation { valid: boolean; errors: Record<string, string> }
export type SettingValues = Record<string, unknown>;
export interface SettingsDocument { values: SettingValues; revision: string; profile?: string }
export interface MediaSettingsDocument { values: SettingValues; revision: string }
