import { AppConfig, TaskPayload, TaskStats, LogEntry, ChartDataPoint, QueueTaskItem, TaskLifecycle } from '../types';
import type { MangaBrushStrokePayload } from '../components/manga/shared';
import { MangaDeleteRuntimeValidationHistoryResult, MangaExportFormat, MangaExportResult, MangaFontCatalogEntry, MangaJob, MangaModelManagerManifest, MangaModelPackageStatus, MangaOpenProjectSummary, MangaOperationResult, MangaPageDetail, MangaPageQualityGate, MangaProjectSummary, MangaPsdExportOptions, MangaRuntimeReadinessReport, MangaRuntimeStatusSummary, MangaRuntimeValidationDiffResult, MangaRuntimeValidationHistoryItem, MangaRuntimeValidationResult, MangaSceneSummary } from '../types/manga';

// Base API URL
const API_BASE = '/api';
const queueRevisionQuery = (revision: string) => `?expected_revision=${encodeURIComponent(revision)}`;
const queueRevision = (response: Response) => {
    const revision = response.headers.get('X-Queue-Revision');
    if (!revision) throw new Error('Missing queue revision; reload before editing');
    return revision;
};
const AUTH_REQUIRED_HEADER = 'X-AiNiee-Auth-Required';
const WEB_SESSION_AUTH_REQUIRED = 'web-session';

export class ApiRequestError extends Error {
    constructor(message: string, public readonly status: number) {
        super(message);
        this.name = 'ApiRequestError';
    }
}

const responseError = async (response: Response, fallback: string): Promise<ApiRequestError> => {
    const payload = await response.json().catch(() => ({}));
    const detail = typeof payload.detail === 'string' ? payload.detail :
        Array.isArray(payload.detail) ? payload.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join('; ') : '';
    return new ApiRequestError(detail || fallback, response.status);
};

type DraftKind = 'pre_translation' | 'post_translation' | 'glossary' | 'exclusion' |
    'characterization' | 'world_building' | 'writing_style' | 'translation_example';

const saveDraft = async (kind: DraftKind, value: unknown): Promise<void> => {
    const response = await fetch(`${API_BASE}/draft/${kind}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(value),
    });
    if (!response.ok) throw await responseError(response, 'Failed to save draft');
};

export interface TaskPreviewResponse {
    valid: boolean;
    missing_prompts: string[];
    task_type: string;
    argv: string[];
    steps: Record<string, unknown>;
    request_fingerprint?: string;
}

let webSessionBootstrap: Promise<void> | null = null;
const nativeFetch = window.fetch.bind(window);

const isProtectedApiRequest = (input: RequestInfo | URL, init?: RequestInit): boolean => {
    const requestUrl = input instanceof Request ? input.url : String(input);
    const url = new URL(requestUrl, window.location.href);
    if (url.origin !== window.location.origin) return false;
    if (url.pathname !== API_BASE && !url.pathname.startsWith(`${API_BASE}/`)) return false;

    const method = String(init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    if (method === 'OPTIONS') return false;
    if (method === 'POST' && url.pathname === `${API_BASE}/session/bootstrap`) return false;
    if (method === 'GET' && (url.pathname === `${API_BASE}/version` || url.pathname === `${API_BASE}/system/mode`)) {
        return false;
    }
    return true;
};

const bootstrapWebSession = async (force = false): Promise<void> => {
    if (!webSessionBootstrap || force) {
        // Explicit credentials and cache policy matter when the SPA is served through
        // an HTTPS reverse proxy. The browser otherwise may retain a stale bootstrap
        // response or omit the session cookie when a Request was constructed by a
        // caller with different defaults.
        webSessionBootstrap = nativeFetch(`${API_BASE}/session/bootstrap`, {
            method: 'POST',
            credentials: 'same-origin',
            cache: 'no-store',
            headers: { Accept: 'application/json' },
        }).then(async response => {
            if (!response.ok) {
                const error = await responseError(response, 'Failed to establish Web UI session');
                console.warn('Web UI session bootstrap failed', {
                    status: error.status,
                    detail: error.message,
                    origin: window.location.origin,
                });
                throw error;
            }
        });
    }
    try {
        await webSessionBootstrap;
    } catch (error) {
        webSessionBootstrap = null;
        throw error;
    }
};

export const installAuthenticatedApiFetch = (): void => {
    if (window.fetch === authenticatedApiFetch) return;
    window.fetch = authenticatedApiFetch;
};

const authenticatedApiFetch: typeof window.fetch = async (input, init) => {
    if (!isProtectedApiRequest(input, init)) {
        return nativeFetch(input, init);
    }

    await bootstrapWebSession();
    // Protected endpoints are same-origin by construction. Force cookie handling
    // even when a caller passes a Request created with `credentials: omit`.
    const preparedRequest = new Request(input, {
        ...init,
        credentials: 'same-origin',
    });
    const retryRequest = preparedRequest.clone();
    let response = await nativeFetch(preparedRequest);
    if (
        response.status !== 403
        || response.headers.get(AUTH_REQUIRED_HEADER) !== WEB_SESSION_AUTH_REQUIRED
    ) {
        return response;
    }

    await bootstrapWebSession(true);
    response = await nativeFetch(retryRequest);
    return response;
};

export interface TaskStatusCursors {
    logs: number;
    chart: number;
    comparison: number;
}

export interface TaskStatusResponse extends TaskLifecycle {
    stats: TaskStats;
    logs: Array<Omit<LogEntry, 'id' | 'timestamp'> & { id?: string; timestamp: string | number; seq?: number }>;
    chart_data?: ChartDataPoint[];
    comparison?: {
        source: string;
        translation: string;
    } | null;
    cursors?: TaskStatusCursors;
    cursors_reset?: Partial<Record<keyof TaskStatusCursors, boolean>>;
    comparison_updated_at?: number;
}

interface TaskStatusState {
    stats: TaskStats;
    logs: LogEntry[];
    chartData: ChartDataPoint[];
    isRunning: boolean;
    comparison?: { source: string; translation: string };
}

export const isTaskActive = (task: TaskLifecycle & { stats?: TaskStats }): boolean =>
    task.running ?? ['starting', 'running', 'stopping', 'waiting_for_agent', 'agent_disconnected', 'committed']
        .includes(task.status ?? task.stats?.status ?? 'idle');

export const mergeTaskStatus = <T extends TaskStatusState>(
    previous: T,
    data: TaskStatusResponse,
    requested: TaskStatusCursors,
    reset = false,
): T => {
    const next = data.cursors ?? requested;
    const resetLogs = reset || data.cursors_reset?.logs || next.logs < requested.logs;
    const resetChart = reset || data.cursors_reset?.chart || next.chart < requested.chart;
    const resetComparison = reset || data.cursors_reset?.comparison || next.comparison < requested.comparison;
    const logs = (data.logs || []).filter(Boolean).map((entry, index): LogEntry => ({
        id: entry.id || `backend-${data.task_id ?? 'current'}-${entry.seq ?? `${entry.timestamp}-${index}`}`,
        timestamp: typeof entry.timestamp === 'number'
            ? new Date(entry.timestamp * 1000).toLocaleTimeString()
            : entry.timestamp,
        message: String(entry.message || ''),
        type: entry.type || 'info',
    }));
    return {
        ...previous,
        stats: data.stats,
        logs: (resetLogs ? logs : [...previous.logs, ...logs]).slice(-500),
        chartData: (resetChart ? data.chart_data || [] : [...previous.chartData, ...(data.chart_data || [])]).slice(-120),
        isRunning: isTaskActive(data),
        comparison: data.comparison ?? (resetComparison ? undefined : previous.comparison),
    };
};

export const DataService = {
    // --- Config & System ---

    async getVersion(): Promise<{ version: string }> {
        try {
            const res = await fetch(`${API_BASE}/version`);
            if (!res.ok) throw new Error('Failed to fetch version');
            return await res.json();
        } catch (error) {
            console.error("API Error: getVersion", error);
            return { version: "Unknown (Connection Error)" };
        }
    },

    async getSystemMode(): Promise<{ mode: 'full' | 'monitor' }> {
        try {
            const controller = new AbortController();
            const timeout = window.setTimeout(() => controller.abort(), 2000);
            const res = await fetch(`${API_BASE}/system/mode`, { signal: controller.signal });
            window.clearTimeout(timeout);
            if (!res.ok) throw new Error('Failed to fetch system mode');
            return await res.json();
        } catch (error) {
            console.error("API Error: getSystemMode", error);
            return { mode: 'full' };
        }
    },

    async getConfig(): Promise<AppConfig> {
        try {
            const res = await fetch(`${API_BASE}/config`);
            if (!res.ok) throw await responseError(res, 'Failed to fetch config');
            return await res.json();
        } catch (error) {
            console.error("API Error: getConfig", error);
            throw error;
        }
    },

    async saveConfig(config: AppConfig): Promise<void> {
        try {
            const res = await fetch(`${API_BASE}/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            if (!res.ok) throw await responseError(res, 'Failed to save config');
            const receipt = await res.json();
            if (typeof receipt.revision === 'string') config._config_revision = receipt.revision;
        } catch (error) {
            console.error("API Error: saveConfig", error);
            throw error;
        }
    },

    async getProfiles(): Promise<string[]> {
        try {
            const res = await fetch(`${API_BASE}/profiles`);
            if (!res.ok) return ['default'];
            return await res.json();
        } catch (error) {
            console.error("API Error: getProfiles", error);
            return ['default'];
        }
    },

    async switchProfile(profileName: string): Promise<AppConfig> {
        try {
            const res = await fetch(`${API_BASE}/profiles/switch`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ profile: profileName })
            });
            if (!res.ok) throw new Error('Failed to switch profile');
            return await res.json();
        } catch (error) {
            console.error("API Error: switchProfile", error);
            throw error;
        }
    },

    async createProfile(name: string, baseProfile?: string): Promise<void> {
        try {
            const res = await fetch(`${API_BASE}/profiles/create`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, base: baseProfile })
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Failed to create profile');
            }
        } catch (error) {
            console.error("API Error: createProfile", error);
            throw error;
        }
    },

    async renameProfile(oldName: string, newName: string): Promise<void> {
        try {
            const res = await fetch(`${API_BASE}/profiles/rename`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ old_name: oldName, new_name: newName })
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Failed to rename profile');
            }
        } catch (error) {
            console.error("API Error: renameProfile", error);
            throw error;
        }
    },

    async deleteProfile(profileName: string): Promise<void> {
        try {
            const res = await fetch(`${API_BASE}/profiles/delete`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ profile: profileName })
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Failed to delete profile');
            }
        } catch (error) {
            console.error("API Error: deleteProfile", error);
            throw error;
        }
    },

    async createPlatform(name: string, baseConfig?: any): Promise<void> {
        try {
            const res = await fetch(`${API_BASE}/platforms/create`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, base_config: baseConfig })
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Failed to create platform');
            }
        } catch (error) {
            console.error("API Error: createPlatform", error);
            throw error;
        }
    },

    // --- Rules Profiles ---

    async getRulesProfiles(): Promise<string[]> {
        const res = await fetch(`${API_BASE}/rules_profiles`);
        if (!res.ok) return ['default'];
        return await res.json();
    },

    async switchRulesProfile(profileName: string): Promise<AppConfig> {
        const res = await fetch(`${API_BASE}/rules_profiles/switch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile: profileName })
        });
        if (!res.ok) throw new Error('Failed to switch rules profile');
        return await res.json();
    },

    async deleteRulesProfile(profileName: string): Promise<void> {
        const res = await fetch(`${API_BASE}/rules_profiles/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile: profileName })
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to delete rules profile');
        }
    },

    // --- Glossary & Rules ---

    async getGlossary(): Promise<any[]> {
        try {
            const res = await fetch(`${API_BASE}/glossary`);
            if (!res.ok) throw new Error('Failed to fetch glossary');
            return await res.json();
        } catch (error) {
            console.error("API Error: getGlossary", error);
            throw error;
        }
    },

    async saveGlossary(items: any[]): Promise<void> {
        try {
            const res = await fetch(`${API_BASE}/glossary`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(items)
            });
            if (!res.ok) throw new Error('Failed to save glossary');
        } catch (error) {
            console.error("API Error: saveGlossary", error);
            throw error;
        }
    },

    async addGlossaryItem(item: { src: string, dst: string, info?: string }): Promise<void> {
        const res = await fetch(`${API_BASE}/glossary/add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(item)
        });
        if (!res.ok) throw new Error('Failed to add term');
    },

    async batchAddGlossaryItems(terms: { src: string, dst: string, info?: string }[]): Promise<void> {
        const res = await fetch(`${API_BASE}/glossary/batch-add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ terms })
        });
        if (!res.ok) throw new Error('Failed to batch add terms');
    },

    async retryTermTranslation(src: string, type: string, avoid: string[], tempConfig?: any, analysisInfo?: string): Promise<{ dst: string, info: string }> {
        const res = await fetch(`${API_BASE}/term/retry`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ src, type, avoid, temp_config: tempConfig, analysis_info: analysisInfo })
        });
        if (!res.ok) throw new Error('Failed to retry translation');
        return await res.json();
    },

    async getExclusion(): Promise<any[]> {
        try {
            const res = await fetch(`${API_BASE}/exclusion`);
            if (!res.ok) throw new Error('Failed to fetch exclusion list');
            return await res.json();
        } catch (error) {
            console.error("API Error: getExclusion", error);
            throw error;
        }
    },

    async getGlossaryDraft(): Promise<any[]> {
        try {
            const res = await fetch(`${API_BASE}/draft/glossary`);
            if (!res.ok) return [];
            return await res.json();
        } catch (error) {
            return [];
        }
    },

    async getExclusionDraft(): Promise<any[]> {
        try {
            const res = await fetch(`${API_BASE}/draft/exclusion`);
            if (!res.ok) return [];
            return await res.json();
        } catch (error) {
            return [];
        }
    },

    async saveExclusion(items: any[]): Promise<void> {
        try {
            const res = await fetch(`${API_BASE}/exclusion`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(items)
            });
            if (!res.ok) throw new Error('Failed to save exclusion list');
        } catch (error) {
            console.error("API Error: saveExclusion", error);
            throw error;
        }
    },

    async getPreTranslationRules(): Promise<any[]> {
        const res = await fetch(`${API_BASE}/pre_translation`);
        if (!res.ok) throw new Error('Failed to fetch pre-translation rules');
        return await res.json();
    },

    async savePreTranslationRules(items: any[]): Promise<any[]> {
        const res = await fetch(`${API_BASE}/pre_translation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(items)
        });
        if (!res.ok) throw new Error('Failed to save pre-translation rules');
        const data = await res.json();
        return data.items || items;
    },

    async deletePreTranslationRule(index: number, itemId?: string): Promise<{ items: any[]; deleted_index?: number }> {
        let res = itemId
            ? await fetch(`${API_BASE}/pre_translation/by-id/${encodeURIComponent(itemId)}`, { method: 'DELETE' })
            : await fetch(`${API_BASE}/pre_translation/${index}`, { method: 'DELETE' });
        if (!res.ok && itemId) {
            res = await fetch(`${API_BASE}/pre_translation/${index}`, { method: 'DELETE' });
        }
        if (!res.ok) throw new Error('Failed to delete pre-translation rule');
        const data = await res.json();
        return { items: data.items || [], deleted_index: data.deleted_index };
    },

    async getPreTranslationDraft(): Promise<any[]> {
        try {
            const res = await fetch(`${API_BASE}/draft/pre_translation`);
            if (!res.ok) return [];
            return await res.json();
        } catch { return []; }
    },

    async savePreTranslationDraft(items: any[]): Promise<void> {
        await saveDraft('pre_translation', items);
    },

    async getPostTranslationRules(): Promise<any[]> {
        const res = await fetch(`${API_BASE}/post_translation`);
        if (!res.ok) throw new Error('Failed to fetch post-translation rules');
        return await res.json();
    },

    async savePostTranslationRules(items: any[]): Promise<any[]> {
        const res = await fetch(`${API_BASE}/post_translation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(items)
        });
        if (!res.ok) throw new Error('Failed to save post-translation rules');
        const data = await res.json();
        return data.items || items;
    },

    async deletePostTranslationRule(index: number, itemId?: string): Promise<{ items: any[]; deleted_index?: number }> {
        let res = itemId
            ? await fetch(`${API_BASE}/post_translation/by-id/${encodeURIComponent(itemId)}`, { method: 'DELETE' })
            : await fetch(`${API_BASE}/post_translation/${index}`, { method: 'DELETE' });
        if (!res.ok && itemId) {
            res = await fetch(`${API_BASE}/post_translation/${index}`, { method: 'DELETE' });
        }
        if (!res.ok) throw new Error('Failed to delete post-translation rule');
        const data = await res.json();
        return { items: data.items || [], deleted_index: data.deleted_index };
    },

    async getPostTranslationDraft(): Promise<any[]> {
        try {
            const res = await fetch(`${API_BASE}/draft/post_translation`);
            if (!res.ok) return [];
            return await res.json();
        } catch { return []; }
    },

    async savePostTranslationDraft(items: any[]): Promise<void> {
        await saveDraft('post_translation', items);
    },

    async saveGlossaryDraft(items: any[]): Promise<void> {
        await saveDraft('glossary', items);
    },

    async saveExclusionDraft(items: any[]): Promise<void> {
        await saveDraft('exclusion', items);
    },

    // --- New Features ---

    async getCharacterization(): Promise<any[]> {
        const res = await fetch(`${API_BASE}/characterization`);
        if (!res.ok) throw new Error('Failed to fetch characterization');
        return await res.json();
    },

    async saveCharacterization(items: any[]): Promise<void> {
        const res = await fetch(`${API_BASE}/characterization`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(items)
        });
        if (!res.ok) throw new Error('Failed to save characterization');
    },

    async getCharacterizationDraft(): Promise<any[]> {
        try {
            const res = await fetch(`${API_BASE}/draft/characterization`);
            if (!res.ok) return [];
            return await res.json();
        } catch { return []; }
    },

    async saveCharacterizationDraft(items: any[]): Promise<void> {
        await saveDraft('characterization', items);
    },

    async getWorldBuilding(): Promise<string> {
        const res = await fetch(`${API_BASE}/world_building`);
        if (!res.ok) throw new Error('Failed to fetch world building');
        const data = await res.json();
        return data.content || "";
    },

    async saveWorldBuilding(content: string): Promise<void> {
        const res = await fetch(`${API_BASE}/world_building`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
        if (!res.ok) throw new Error('Failed to save world building');
    },

    async getWorldBuildingDraft(): Promise<string> {
        try {
            const res = await fetch(`${API_BASE}/draft/world_building`);
            if (!res.ok) return "";
            const data = await res.json();
            return data.content || "";
        } catch { return ""; }
    },

    async saveWorldBuildingDraft(content: string): Promise<void> {
        await saveDraft('world_building', { content });
    },

    async getWritingStyle(): Promise<string> {
        const res = await fetch(`${API_BASE}/writing_style`);
        if (!res.ok) throw new Error('Failed to fetch writing style');
        const data = await res.json();
        return data.content || "";
    },

    async saveWritingStyle(content: string): Promise<void> {
        const res = await fetch(`${API_BASE}/writing_style`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
        if (!res.ok) throw new Error('Failed to save writing style');
    },

    async getWritingStyleDraft(): Promise<string> {
        try {
            const res = await fetch(`${API_BASE}/draft/writing_style`);
            if (!res.ok) return "";
            const data = await res.json();
            return data.content || "";
        } catch { return ""; }
    },

    async saveWritingStyleDraft(content: string): Promise<void> {
        await saveDraft('writing_style', { content });
    },

    async getTranslationExample(): Promise<any[]> {
        const res = await fetch(`${API_BASE}/translation_example`);
        if (!res.ok) throw new Error('Failed to fetch translation examples');
        return await res.json();
    },

    async saveTranslationExample(items: any[]): Promise<void> {
        const res = await fetch(`${API_BASE}/translation_example`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(items)
        });
        if (!res.ok) throw new Error('Failed to save translation examples');
    },

    async getTranslationExampleDraft(): Promise<any[]> {
        try {
            const res = await fetch(`${API_BASE}/draft/translation_example`);
            if (!res.ok) return [];
            return await res.json();
        } catch { return []; }
    },

    async saveTranslationExampleDraft(items: any[]): Promise<void> {
        await saveDraft('translation_example', items);
    },

    // --- Prompts ---

    async listPromptCategories(): Promise<string[]> {
        const res = await fetch(`${API_BASE}/prompts`);
        if (!res.ok) return [];
        return await res.json();
    },

    async listPrompts(category: string): Promise<string[]> {
        const res = await fetch(`${API_BASE}/prompts/${encodeURIComponent(category)}`);
        if (!res.ok) return [];
        return await res.json();
    },

    async getPromptContent(category: string, filename: string): Promise<string> {
        const res = await fetch(`${API_BASE}/prompts/${encodeURIComponent(category)}/${encodeURIComponent(filename)}`);
        if (!res.ok) throw new Error('Failed to fetch prompt content');
        const data = await res.json();
        return data.content || "";
    },

    async savePromptContent(category: string, filename: string, content: string): Promise<void> {
        const res = await fetch(`${API_BASE}/prompts/${encodeURIComponent(category)}/${encodeURIComponent(filename)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
        if (!res.ok) throw new Error('Failed to save prompt content');
    },

    async openMangaProject(projectPath: string): Promise<MangaProjectSummary> {
        const res = await fetch(`${API_BASE}/manga/projects/open`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_path: projectPath })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to open manga project');
        return data;
    },

    async listOpenMangaProjects(): Promise<MangaOpenProjectSummary[]> {
        const res = await fetch(`${API_BASE}/manga/projects`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to list open manga projects');
        return Array.isArray(data) ? data : [];
    },

    async getMangaScene(projectId: string, options?: { quality?: boolean; runtime?: boolean }): Promise<MangaSceneSummary> {
        const params = new URLSearchParams();
        if (options?.quality === false) params.set('quality', 'false');
        if (options?.runtime === false) params.set('runtime', 'false');
        const suffix = params.toString() ? `?${params.toString()}` : '';
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/scene${suffix}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to fetch manga scene');
        return data;
    },

    async getMangaRuntimeStatus(projectId: string, refresh = false): Promise<MangaRuntimeStatusSummary> {
        const params = new URLSearchParams();
        if (refresh) params.set('refresh', 'true');
        const suffix = params.toString() ? `?${params.toString()}` : '';
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/runtime-status${suffix}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to fetch manga runtime status');
        return data;
    },

    async getMangaPage(projectId: string, pageId: string, options?: { diagnostics?: boolean }): Promise<MangaPageDetail> {
        const params = new URLSearchParams();
        if (options?.diagnostics === false) params.set('diagnostics', 'false');
        const suffix = params.toString() ? `?${params.toString()}` : '';
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}${suffix}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to fetch manga page');
        return data;
    },

    async getMangaPageQuality(projectId: string, pageId: string): Promise<MangaPageQualityGate> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/quality`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to fetch manga page quality');
        return data;
    },

    async listMangaFonts(projectId?: string): Promise<MangaFontCatalogEntry[]> {
        const url = projectId
            ? `${API_BASE}/manga/projects/${projectId}/fonts`
            : `${API_BASE}/manga/fonts`;
        const res = await fetch(url);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to fetch manga fonts');
        return Array.isArray(data) ? data : [];
    },

    async applyMangaBrushMaskStroke(projectId: string, pageId: string, stroke: MangaBrushStrokePayload): Promise<any> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/brush-mask/strokes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...stroke, mode: 'brush' })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to apply manga brush mask stroke');
        return data;
    },

    async applyMangaRestoreMaskStroke(projectId: string, pageId: string, stroke: MangaBrushStrokePayload): Promise<any> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/restore-mask/strokes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...stroke, mode: 'restore' })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to apply manga restore mask stroke');
        return data;
    },

    async saveMangaProject(projectId: string): Promise<MangaOperationResult> {
        const res = await fetch(`${API_BASE}/manga/projects/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_id: projectId })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to save manga project');
        return data;
    },

    async translateMangaPage(projectId: string, pageId: string): Promise<MangaJob> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/translate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ save_after_run: true, refresh_render: true })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to translate manga page');
        return data;
    },

    async detectMangaPage(projectId: string, pageId: string): Promise<MangaJob> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/detect`, {
            method: 'POST'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to detect manga page');
        return data;
    },

    async ocrMangaPage(projectId: string, pageId: string): Promise<MangaJob> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/ocr`, {
            method: 'POST'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to OCR manga page');
        return data;
    },

    async inpaintMangaPage(projectId: string, pageId: string): Promise<MangaJob> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/inpaint`, {
            method: 'POST'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to inpaint manga page');
        return data;
    },

    async renderMangaPage(projectId: string, pageId: string): Promise<MangaJob> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/render`, {
            method: 'POST'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to render manga page');
        return data;
    },

    async validateMangaRuntime(projectId: string, pageId: string): Promise<MangaRuntimeValidationResult> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/runtime-validation`, {
            method: 'POST'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to validate manga runtime');
        return data;
    },

    async startMangaRuntimeValidation(projectId: string, pageId: string): Promise<MangaJob> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/runtime-validation/start`, {
            method: 'POST'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to start manga runtime validation');
        return data;
    },

    async stopMangaRuntimeValidation(projectId: string, pageId: string): Promise<MangaJob> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/runtime-validation/stop`, {
            method: 'POST'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to stop manga runtime validation');
        return data;
    },

    async startMangaRuntimeValidationStageRetry(projectId: string, pageId: string, stage: string): Promise<MangaJob> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/runtime-validation/stages/${encodeURIComponent(stage)}/retry/start`, {
            method: 'POST'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to retry manga runtime validation stage');
        return data;
    },

    async getLatestMangaRuntimeValidation(projectId: string, pageId: string): Promise<MangaRuntimeValidationResult | null> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/runtime-validation/latest`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to fetch latest manga runtime validation');
        return data;
    },

    async listMangaRuntimeValidationHistory(projectId: string, pageId: string): Promise<MangaRuntimeValidationHistoryItem[]> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/runtime-validation/history`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to fetch manga runtime validation history');
        return Array.isArray(data) ? data : [];
    },

    async getMangaRuntimeValidationHistoryItem(projectId: string, pageId: string, runId: string): Promise<MangaRuntimeValidationResult> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/runtime-validation/history/${encodeURIComponent(runId)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to fetch manga runtime validation report');
        return data;
    },

    async diffMangaRuntimeValidationHistory(projectId: string, pageId: string, beforeRunId: string, afterRunId: string): Promise<MangaRuntimeValidationDiffResult> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/runtime-validation/history/${encodeURIComponent(beforeRunId)}/diff/${encodeURIComponent(afterRunId)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to diff manga runtime validation reports');
        return data;
    },

    async deleteMangaRuntimeValidationHistory(projectId: string, pageId: string, runId: string): Promise<MangaDeleteRuntimeValidationHistoryResult> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/pages/${pageId}/runtime-validation/history/${encodeURIComponent(runId)}`, {
            method: 'DELETE'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to delete manga runtime validation report');
        return data;
    },

    async downloadMangaModel(modelId: string): Promise<MangaModelPackageStatus> {
        const res = await fetch(`${API_BASE}/manga/models/${encodeURIComponent(modelId)}/download`, {
            method: 'POST'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to prepare manga model');
        return data;
    },

    async getMangaModelManager(): Promise<MangaModelManagerManifest> {
        const res = await fetch(`${API_BASE}/manga/models/manager`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to fetch manga model manager');
        return data;
    },

    async updateMangaProjectConfig(projectId: string, updates: Record<string, string>): Promise<MangaRuntimeStatusSummary & { ok: boolean; updates: Record<string, string>; task_config?: Record<string, any> }> {
        const res = await fetch(`${API_BASE}/manga/projects/${encodeURIComponent(projectId)}/config`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ updates })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to update manga project config');
        return data;
    },

    async startMangaModelDownload(modelId: string, projectId = ''): Promise<MangaJob> {
        const prefix = projectId
            ? `${API_BASE}/manga/projects/${encodeURIComponent(projectId)}`
            : `${API_BASE}/manga`;
        const res = await fetch(`${prefix}/models/${encodeURIComponent(modelId)}/download/start`, {
            method: 'POST'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to start manga model preparation');
        return data;
    },

    async startMangaModelPresetDownload(presetId: string, projectId = ''): Promise<MangaJob> {
        const prefix = projectId
            ? `${API_BASE}/manga/projects/${encodeURIComponent(projectId)}`
            : `${API_BASE}/manga`;
        const res = await fetch(`${prefix}/model-presets/${encodeURIComponent(presetId)}/download/start`, {
            method: 'POST'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to start manga model preset preparation');
        return data;
    },

    async startMangaAllModelsDownload(projectId = ''): Promise<MangaJob> {
        const prefix = projectId
            ? `${API_BASE}/manga/projects/${encodeURIComponent(projectId)}`
            : `${API_BASE}/manga`;
        const res = await fetch(`${prefix}/models/download-all/start`, {
            method: 'POST'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to start all manga model preparation');
        return data;
    },

    async getMangaRuntimeReadiness(params: Record<string, string> = {}): Promise<MangaRuntimeReadinessReport> {
        const query = new URLSearchParams();
        Object.entries(params).forEach(([key, value]) => {
            if (value) query.set(key, value);
        });
        const suffix = query.toString() ? `?${query.toString()}` : '';
        const res = await fetch(`${API_BASE}/manga/runtime/readiness${suffix}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to fetch manga runtime readiness');
        return data;
    },

    async translateSelectedMangaPages(
        projectId: string,
        pageIds: string[],
        options: { autoInpaint?: boolean; autoRender?: boolean; autoExport?: boolean } = {}
    ): Promise<MangaJob> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/batch/translate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                page_ids: pageIds,
                generate_text_blocks: true,
                auto_inpaint: options.autoInpaint ?? false,
                auto_render: options.autoRender ?? false,
                auto_export: options.autoExport ?? false
            })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to translate selected manga pages');
        return data;
    },

    async planSelectedMangaPages(projectId: string, pageIds: string[]): Promise<MangaJob> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/batch/typesetting-plan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                page_ids: pageIds,
                generate_text_blocks: true,
                auto_inpaint: false,
                auto_render: false,
                auto_export: false
            })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to generate manga text block plans');
        return data;
    },

    async applyMangaOps(projectId: string, ops: any[]): Promise<MangaOperationResult> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/ops`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ops })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to apply manga operations');
        return data;
    },

    async undoMangaOps(projectId: string): Promise<MangaOperationResult> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/undo`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to undo manga operations');
        return data;
    },

    async redoMangaOps(projectId: string): Promise<MangaOperationResult> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/redo`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to redo manga operations');
        return data;
    },

    async getMangaJob(projectId: string, jobId: string): Promise<MangaJob> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/jobs/${jobId}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to fetch manga job');
        return data;
    },

    async getGlobalMangaJob(jobId: string): Promise<MangaJob> {
        const res = await fetch(`${API_BASE}/manga/jobs/${jobId}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to fetch manga job');
        return data;
    },

    async exportMangaProject(
        projectId: string,
        format: MangaExportFormat,
        psdOptions: MangaPsdExportOptions = {},
    ): Promise<MangaExportResult> {
        const init: RequestInit = format === 'psd'
            ? {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    page_ids: psdOptions.page_ids || [],
                    script_only: Boolean(psdOptions.script_only),
                    include_blocked: psdOptions.include_blocked ?? true,
                    package: Boolean(psdOptions.package),
                })
            }
            : { method: 'POST' };
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/export/${format}`, init);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || `Failed to export manga project as ${format}`);
        return data;
    },

    async getMangaPsdPhotoshopStatus(): Promise<NonNullable<MangaExportResult['photoshop']>> {
        const res = await fetch(`${API_BASE}/manga/export/psd/photoshop`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to fetch Photoshop status');
        return data;
    },

    async startMangaPsdExport(projectId: string, psdOptions: MangaPsdExportOptions = {}): Promise<MangaJob> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/export/psd/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                page_ids: psdOptions.page_ids || [],
                script_only: Boolean(psdOptions.script_only),
                include_blocked: psdOptions.include_blocked ?? true,
                package: Boolean(psdOptions.package),
            })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to start PSD export');
        return data;
    },

    async stopMangaPsdExport(projectId: string): Promise<MangaJob> {
        const res = await fetch(`${API_BASE}/manga/projects/${projectId}/export/psd/stop`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to cancel PSD export');
        return data;
    },

    // --- Task Execution ---

    async previewTask(payload: TaskPayload, signal?: AbortSignal): Promise<TaskPreviewResponse> {
        const { api_key: _credential, ...request } = payload;
        const response = await fetch(`${API_BASE}/task/preview`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(request),
            signal,
        });
        if (!response.ok) throw await responseError(response, 'Failed to preview task');
        return await response.json();
    },


    /**
     * Start a new task (Translate, Polish, or Export)
     */
    async startTask(payload: TaskPayload): Promise<{ success: boolean; message: string; task_id?: string; status?: string; running?: boolean }> {
        try {
            const res = await fetch(`${API_BASE}/task/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || data.error || 'Failed to start task');
            return data;
        } catch (error: any) {
            console.error("API Error: startTask", error);
            throw error;
        }
    },

    /**
     * Stop the currently running task
     */
    async stopTask(taskId?: string): Promise<TaskLifecycle> {
        try {
            const res = await fetch(`${API_BASE}/task/stop`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(taskId ? { task_id: taskId } : {}),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || data.error || 'Failed to stop task');
            return data;
        } catch (error) {
            console.error("API Error: stopTask", error);
            throw error;
        }
    },

    /**
     * Get real-time status, logs, and stats from the backend
     */
    async getTaskStatus(
        logCursor = 0,
        chartCursor = 0,
        comparisonCursor = 0,
        taskId?: string,
        signal?: AbortSignal,
    ): Promise<TaskStatusResponse> {
        const params = new URLSearchParams({
            log_cursor: String(logCursor),
            chart_cursor: String(chartCursor),
            comparison_cursor: String(comparisonCursor),
            _t: String(Date.now())
        });
        if (taskId) params.set('task_id', taskId);
        const res = await fetch(`${API_BASE}/task/status?${params.toString()}`, { signal });
        if (!res.ok) throw await responseError(res, 'Failed to get status');
        return await res.json();
    },

    // --- File Management ---

    async listTempFiles(): Promise<{ name: string; path: string; size: number }[]> {
        try {
            const res = await fetch(`${API_BASE}/files/temp`);
            if (!res.ok) return [];
            return await res.json();
        } catch (error) {
            console.error("API Error: listTempFiles", error);
            return [];
        }
    },

    async deleteTempFiles(files: string[]): Promise<any> {
        try {
            const res = await fetch(`${API_BASE}/files/temp`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files })
            });
            if (!res.ok) throw new Error('Failed to delete files');
            return await res.json();
        } catch (error) {
            console.error("API Error: deleteTempFiles", error);
            throw error;
        }
    },

    // --- Plugin Management ---

    async getPlugins(): Promise<any[]> {
        try {
            const res = await fetch(`${API_BASE}/plugins`);
            if (!res.ok) throw new Error('Failed to fetch plugins');
            return await res.json();
        } catch (error) {
            console.error("API Error: getPlugins", error);
            throw error;
        }
    },

    async togglePlugin(name: string, enabled: boolean): Promise<void> {
        try {
            const res = await fetch(`${API_BASE}/plugins/toggle`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, enabled })
            });
            if (!res.ok) throw new Error('Failed to toggle plugin');
        } catch (error) {
            console.error("API Error: togglePlugin", error);
            throw error;
        }
    },

    // --- Task Queue ---

    async getQueue(): Promise<{ items: QueueTaskItem[]; revision: string }> {
        const res = await fetch(`${API_BASE}/queue`);
        if (!res.ok) throw await responseError(res, 'Failed to load queue');
        return { items: await res.json(), revision: queueRevision(res) };
    },

    async addToQueue(item: Partial<QueueTaskItem>): Promise<void> {
        const res = await fetch(`${API_BASE}/queue`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(item)
        });
        if (!res.ok) throw new Error('Failed to add task');
    },

    async removeFromQueue(taskId: string, revision: string): Promise<void> {
        const res = await fetch(`${API_BASE}/queue/${taskId}${queueRevisionQuery(revision)}`, { method: 'DELETE' });
        if (!res.ok) throw await responseError(res, 'Failed to remove task');
    },

    async updateQueueItem(taskId: string, item: Partial<QueueTaskItem>, revision: string): Promise<void> {
        const res = await fetch(`${API_BASE}/queue/${taskId}${queueRevisionQuery(revision)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(item)
        });
        if (!res.ok) throw await responseError(res, 'Failed to update task');
    },

    async clearQueue(revision: string): Promise<void> {
        const res = await fetch(`${API_BASE}/queue/clear${queueRevisionQuery(revision)}`, { method: 'POST' });
        if (!res.ok) throw await responseError(res, 'Failed to clear queue');
    },

    async runQueue(): Promise<void> {
        const res = await fetch(`${API_BASE}/queue/run`, { method: 'POST' });
        if (!res.ok) {
            let detail = 'Failed to start queue';
            try {
                const err = await res.json();
                detail = err?.detail || detail;
            } catch {}
            throw new Error(detail);
        }
    },

    async getQueueRaw(): Promise<{ content: string; revision: string }> {
        const res = await fetch(`${API_BASE}/queue/raw`);
        if (!res.ok) throw await responseError(res, 'Failed to load queue JSON');
        const data = await res.json();
        return { content: data.content, revision: queueRevision(res) };
    },

    async saveQueueRaw(content: string, revision: string): Promise<void> {
        const res = await fetch(`${API_BASE}/queue/raw${queueRevisionQuery(revision)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
        if (!res.ok) throw await responseError(res, 'Failed to save JSON');
    },

    async moveQueueItem(taskId: string, toIndex: number, revision: string): Promise<void> {
        const res = await fetch(`${API_BASE}/queue/${taskId}/move${queueRevisionQuery(revision)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ to_index: toIndex })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Failed to move task');
        }
    },

    async reorderQueue(newOrder: string[], revision: string): Promise<void> {
        const res = await fetch(`${API_BASE}/queue/reorder${queueRevisionQuery(revision)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_order: newOrder })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Failed to reorder queue');
        }
    },

    async uploadFile(file: File, policy: 'default' | 'buffer' | 'overwrite' = 'default'): Promise<any> {
        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch(`${API_BASE}/files/upload?policy=${policy}`, {
                method: 'POST',
                body: formData
            });
            if (!res.ok) throw await responseError(res, 'Failed to upload file');
            return await res.json();
        } catch (error) {
            console.error("API Error: uploadFile", error);
            throw error;
        }
    },

    // --- AI Glossary Analysis ---
    async preflightGlossaryAnalysis(
        inputPath: string,
        percent: number,
        lines?: number
    ): Promise<any> {
        const res = await fetch(`${API_BASE}/glossary/analysis/preflight`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                input_path: inputPath,
                analysis_percent: percent,
                analysis_lines: lines
            })
        });
        if (!res.ok) throw new Error('Failed to preflight analysis');
        return await res.json();
    },

    async startGlossaryAnalysis(
        inputPath: string,
        percent: number,
        lines?: number,
        analysisMode?: string,
        incrementalSplitTargetTokens?: number,
        promptFile?: string,
        useTempConfig?: boolean,
        tempPlatform?: string,
        tempApiKey?: string,
        tempApiUrl?: string,
        tempModel?: string,
        tempThreads?: number
    ): Promise<any> {
        const res = await fetch(`${API_BASE}/glossary/analysis/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                input_path: inputPath,
                analysis_percent: percent,
                analysis_lines: lines,
                analysis_mode: analysisMode,
                incremental_split_target_tokens: incrementalSplitTargetTokens,
                prompt_file: promptFile,
                use_temp_config: useTempConfig,
                temp_platform: tempPlatform,
                temp_api_key: tempApiKey,
                temp_api_url: tempApiUrl,
                temp_model: tempModel,
                temp_threads: tempThreads
            })
        });
        if (!res.ok) throw new Error('Failed to start analysis');
        return await res.json();
    },

    async getAnalysisStatus(): Promise<any> {
        const res = await fetch(`${API_BASE}/glossary/analysis/status`);
        if (!res.ok) throw new Error('Failed to get analysis status');
        return await res.json();
    },

    async stopGlossaryAnalysis(): Promise<any> {
        const res = await fetch(`${API_BASE}/glossary/analysis/stop`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to stop analysis');
        return await res.json();
    },

    async saveAnalysisResults(minFrequency: number, filename: string): Promise<any> {
        const res = await fetch(`${API_BASE}/glossary/analysis/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ min_frequency: minFrequency, filename })
        });
        if (!res.ok) {
            let message = 'Failed to save analysis';
            try {
                const error = await res.json();
                message = error?.detail || error?.message || message;
            } catch {}
            throw new Error(message);
        }
        return await res.json();
    }
};
