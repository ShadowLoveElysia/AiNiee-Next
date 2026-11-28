export type Catalog = Record<string, string>;
export type MessageParameters = Record<string, string | number>;

export function resolveMessage(key: string, catalogs: readonly Catalog[], parameters: MessageParameters = {}, fallback = key): string {
  const text = catalogs.map((catalog) => catalog[key]).find((value) => typeof value === 'string' && value.length > 0) ?? fallback;
  return text.replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, (placeholder, name: string) =>
    Object.prototype.hasOwnProperty.call(parameters, name) ? String(parameters[name]) : placeholder);
}
