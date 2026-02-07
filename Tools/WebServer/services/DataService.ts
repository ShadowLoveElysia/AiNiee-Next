import { AppConfig, TaskPayload, TaskStats, LogEntry } from '../types';

// Base API URL
const API_BASE = '/api';

interface TaskStatusResponse {
    stats: TaskStats;
    logs: LogEntry[];
}

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
            const res = await fetch(`${API_BASE}/system/mode`);
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
            if (!res.ok) throw new Error('Failed to fetch config');
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
            if (!res.ok) throw new Error('Failed to save config');
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

    async saveGlossaryDraft(items: any[]): Promise<void> {
        try {
            await fetch(`${API_BASE}/draft/glossary`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(items)
            });
        } catch (error) {
            console.error("API Error: saveGlossaryDraft", error);
        }
    },

    async saveExclusionDraft(items: any[]): Promise<void> {
        try {
            await fetch(`${API_BASE}/draft/exclusion`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(items)
            });
        } catch (error) {
            console.error("API Error: saveExclusionDraft", error);
        }
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
        await fetch(`${API_BASE}/draft/characterization`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(items)
        });
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
        await fetch(`${API_BASE}/draft/world_building`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
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
        await fetch(`${API_BASE}/draft/writing_style`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
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
        await fetch(`${API_BASE}/draft/translation_example`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(items)
        });
    },

    // --- Prompts ---

    async listPromptCategories(): Promise<string[]> {
        const res = await fetch(`${API_BASE}/prompts`);
        if (!res.ok) return [];
        return await res.json();
    },

    async listPrompts(category: string): Promise<string[]> {
        const res = await fetch(`${API_BASE}/prompts/${category}`);
        if (!res.ok) return [];
        return await res.json();
    },

    async getPromptContent(category: string, filename: string): Promise<string> {
        const res = await fetch(`${API_BASE}/prompts/${category}/${filename}`);
        if (!res.ok) throw new Error('Failed to fetch prompt content');
        const data = await res.json();
        return data.content || "";
    },

    async savePromptContent(category: string, filename: string, content: string): Promise<void> {
        const res = await fetch(`${API_BASE}/prompts/${category}/${filename}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
        if (!res.ok) throw new Error('Failed to save prompt content');
    },

    // --- Task Execution ---

    /**
     * Start a new task (Translate, Polish, or Export)
     */
    async startTask(payload: TaskPayload): Promise<{ success: boolean; message: string }> {
        try {
            const res = await fetch(`${API_BASE}/task/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Failed to start task');
            return data;
        } catch (error: any) {
            console.error("API Error: startTask", error);
            throw error;
        }
    },

    /**
     * Stop the currently running task
     */
    async stopTask(): Promise<void> {
        try {
            const res = await fetch(`${API_BASE}/task/stop`, { method: 'POST' });
            if (!res.ok) throw new Error('Failed to stop task');
        } catch (error) {
            console.error("API Error: stopTask", error);
        }
    },

    /**
     * Get real-time status, logs, and stats from the backend
     */
    async getTaskStatus(): Promise<TaskStatusResponse> {
        try {
            const res = await fetch(`${API_BASE}/task/status?_t=${Date.now()}`);
            if (!res.ok) throw new Error('Failed to get status');
            return await res.json();
        } catch (error) {
            // Return empty/idle state on error to prevent UI crash
            return {
                stats: {
                    rpm: 0,
                    tpm: 0,
                    totalProgress: 0, // Fixed property name
                    completedProgress: 0, // Fixed property name
                    totalTokens: 0,
                    elapsedTime: 0,
                    status: 'error',
                    currentFile: 'Connection Lost'
                },
                logs: []
            };
        }
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

    async getQueue(): Promise<any[]> {
        const res = await fetch(`${API_BASE}/queue`);
        return await res.json();
    },

    async addToQueue(item: any): Promise<void> {
        await fetch(`${API_BASE}/queue`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(item)
        });
    },

    async removeFromQueue(index: number): Promise<void> {
        await fetch(`${API_BASE}/queue/${index}`, { method: 'DELETE' });
    },

    async updateQueueItem(index: number, item: any): Promise<void> {
        const res = await fetch(`${API_BASE}/queue/${index}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(item)
        });
        if (!res.ok) throw new Error('Failed to update task');
    },

    async clearQueue(): Promise<void> {
        await fetch(`${API_BASE}/queue/clear`, { method: 'POST' });
    },

    async runQueue(): Promise<void> {
        await fetch(`${API_BASE}/queue/run`, { method: 'POST' });
    },

    async editQueueFile(): Promise<void> {
        await fetch(`${API_BASE}/queue/edit_file`);
    },

    async getQueueRaw(): Promise<string> {
        const res = await fetch(`${API_BASE}/queue/raw`);
        const data = await res.json();
        return data.content || "[]";
    },

    async saveQueueRaw(content: string): Promise<void> {
        const res = await fetch(`${API_BASE}/queue/raw`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Failed to save JSON');
        }
    },

    async moveQueueItem(fromIndex: number, toIndex: number): Promise<void> {
        const res = await fetch(`${API_BASE}/queue/${fromIndex}/move`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ to_index: toIndex })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Failed to move task');
        }
    },

    async reorderQueue(newOrder: number[]): Promise<void> {
        const res = await fetch(`${API_BASE}/queue/reorder`, {
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
            // Don't throw on 200 OK even if status is 'limit_reached'
            // The component needs to handle the logic.
            return await res.json();
        } catch (error) {
            console.error("API Error: uploadFile", error);
            throw error;
        }
    },

    // --- Web Editor API ---

    async getEditorFiles(): Promise<any[]> {
        try {
            const res = await fetch(`${API_BASE}/editor/files`);
            if (!res.ok) throw new Error('Failed to fetch editor files');
            return await res.json();
        } catch (error) {
            console.error("API Error: getEditorFiles", error);
            throw error;
        }
    },

    async getEditorStats(): Promise<any> {
        try {
            const res = await fetch(`${API_BASE}/editor/stats`);
            if (!res.ok) throw new Error('Failed to fetch editor stats');
            return await res.json();
        } catch (error) {
            console.error("API Error: getEditorStats", error);
            throw error;
        }
    },

    async getParallelEditorData(filePath: string, page: number = 0, pageSize: number = 15): Promise<any> {
        try {
            const encodedPath = encodeURIComponent(filePath);
            const res = await fetch(`${API_BASE}/parallel-editor/${encodedPath}?page=${page}&page_size=${pageSize}`);
            if (!res.ok) throw new Error('Failed to fetch parallel editor data');
            return await res.json();
        } catch (error) {
            console.error("API Error: getParallelEditorData", error);
            throw error;
        }
    },

    async updateParallelEditorItem(filePath: string, updateData: { text_index: number; new_translation: string }): Promise<any> {
        try {
            const encodedPath = encodeURIComponent(filePath);
            const res = await fetch(`${API_BASE}/parallel-editor/${encodedPath}/update`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updateData)
            });
            if (!res.ok) throw new Error('Failed to update editor item');
            return await res.json();
        } catch (error) {
            console.error("API Error: updateParallelEditorItem", error);
            throw error;
        }
    },

    async searchParallelEditorFile(filePath: string, searchParams: {
        query: string;
        scope: string;
        is_regex?: boolean;
        search_flagged?: boolean;
    }): Promise<any[]> {
        try {
            const encodedPath = encodeURIComponent(filePath);
            const res = await fetch(`${API_BASE}/parallel-editor/${encodedPath}/search`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(searchParams)
            });
            if (!res.ok) throw new Error('Failed to search in file');
            return await res.json();
        } catch (error) {
            console.error("API Error: searchParallelEditorFile", error);
            throw error;
        }
    },

    async gotoParallelEditorLine(filePath: string, lineIndex: number, pageSize: number = 15): Promise<any> {
        try {
            const encodedPath = encodeURIComponent(filePath);
            const res = await fetch(`${API_BASE}/parallel-editor/${encodedPath}/goto/${lineIndex}?page_size=${pageSize}`);
            if (!res.ok) throw new Error('Failed to calculate page for line');
            return await res.json();
        } catch (error) {
            console.error("API Error: gotoParallelEditorLine", error);
            throw error;
        }
    },

    async clearFileModifications(filePath: string): Promise<any> {
        try {
            const encodedPath = encodeURIComponent(filePath);
            const res = await fetch(`${API_BASE}/parallel-editor/${encodedPath}/modifications`, {
                method: 'DELETE'
            });
            if (!res.ok) throw new Error('Failed to clear file modifications');
            return await res.json();
        } catch (error) {
            console.error("API Error: clearFileModifications", error);
            throw error;
        }
    },

    async clearAllModifications(): Promise<any> {
        try {
            const res = await fetch(`${API_BASE}/parallel-editor/modifications`, {
                method: 'DELETE'
            });
            if (!res.ok) throw new Error('Failed to clear all modifications');
            return await res.json();
        } catch (error) {
            console.error("API Error: clearAllModifications", error);
            throw error;
        }
    },

    async getFileModifications(filePath: string): Promise<any> {
        try {
            const encodedPath = encodeURIComponent(filePath);
            const res = await fetch(`${API_BASE}/parallel-editor/${encodedPath}/modifications`);
            if (!res.ok) throw new Error('Failed to get file modifications');
            return await res.json();
        } catch (error) {
            console.error("API Error: getFileModifications", error);
            throw error;
        }
    },

    // --- Cache File Management ---

    async loadCacheFile(filePath: string): Promise<any> {
        try {
            const res = await fetch(`${API_BASE}/parallel-editor/load-cache`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath })
            });
            if (!res.ok) throw new Error('Failed to load cache file');
            return await res.json();
        } catch (error) {
            console.error("API Error: loadCacheFile", error);
            throw error;
        }
    },

    async openFileDialog(): Promise<any> {
        try {
            const res = await fetch(`${API_BASE}/parallel-editor/open-file-dialog`, {
                method: 'POST'
            });
            if (!res.ok) throw new Error('Failed to open file dialog');
            return await res.json();
        } catch (error) {
            console.error("API Error: openFileDialog", error);
            throw error;
        }
    },

    async getCacheStatus(): Promise<any> {
        try {
            const res = await fetch(`${API_BASE}/parallel-editor/upload-status`);
            if (!res.ok) throw new Error('Failed to get cache status');
            return await res.json();
        } catch (error) {
            console.error("API Error: getCacheStatus", error);
            throw error;
        }
    },

    async browseDirectory(path: string = '.'): Promise<any> {
        try {
            const encodedPath = encodeURIComponent(path);
            const res = await fetch(`${API_BASE}/parallel-editor/browse-directory?path=${encodedPath}`);
            if (!res.ok) throw new Error('Failed to browse directory');
            return await res.json();
        } catch (error) {
            console.error("API Error: browseDirectory", error);
            throw error;
        }
    },

    // --- AI Glossary Analysis ---
    async startGlossaryAnalysis(
        inputPath: string,
        percent: number,
        lines?: number,
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
        if (!res.ok) throw new Error('Failed to save analysis');
        return await res.json();
    }
};
