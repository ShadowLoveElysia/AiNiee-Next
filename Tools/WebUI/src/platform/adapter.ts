export type RequestTransport = (url: string, init: RequestInit) => Promise<Response>;

export interface PreferenceStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface PlatformAdapter {
  environment: 'browser' | 'tauri';
  transport: RequestTransport;
  preferences: PreferenceStorage;
  capabilities: {
    nativeFiles: boolean;
    openOutput: boolean;
    windowControls: boolean;
  };
  selectFile?: () => Promise<string | null>;
  selectDirectory?: () => Promise<string | null>;
  openOutput?: (path: string) => Promise<void>;
  window?: { minimize(): Promise<void>; maximize(): Promise<void>; close(): Promise<void> };
}

export const browserPlatform: PlatformAdapter = {
  environment: 'browser',
  transport: (url, init) => window.fetch(url, init),
  preferences: {
    getItem: (key) => window.localStorage.getItem(key),
    setItem: (key, value) => window.localStorage.setItem(key, value),
  },
  capabilities: { nativeFiles: false, openOutput: false, windowControls: false },
};
