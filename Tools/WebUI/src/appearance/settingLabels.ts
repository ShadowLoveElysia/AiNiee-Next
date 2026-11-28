import type { SettingDescription } from '../api/settingsContracts';
import { t } from '../i18n';

export const translateSetting = (key: string, fallback = key): string => t(key, undefined, fallback);
export const settingLabel = (field: Pick<SettingDescription, 'label_key' | 'key'>): string => t(`gui.fields.${field.key}`, undefined, translateSetting(field.label_key, field.key));
export const settingDescription = (field: Pick<SettingDescription, 'description_key'>): string => translateSetting(field.description_key, '');
export const settingCategory = (category: string): string => translateSetting(`label_category_${category}`, category);
export const settingChoiceLabel = (key: string, value: unknown): string => translateSetting(`choice_${key}_${String(value)}`, translateSetting(`choice_${String(value)}`, String(value)));
