export const PAGE_ORDER = ['translate', 'polish', 'tasks', 'settings'] as const;
export type Page = typeof PAGE_ORDER[number];
