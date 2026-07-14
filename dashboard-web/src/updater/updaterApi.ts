export interface ServiceVersion { name: string; active: string; path: string; }
export interface VersionsResp { services: ServiceVersion[]; }
export interface ApplyResp { ok: boolean; name: string; version: string; detail: string; }

export async function fetchVersions(): Promise<VersionsResp> {
  const r = await fetch("/dashboard/api/updater/versions");
  if (!r.ok) throw new Error(`versions ${r.status}`);
  return r.json();
}

export async function applyBundle(name: string, version: string): Promise<ApplyResp> {
  const r = await fetch("/dashboard/api/updater/apply", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ name, version }),
  });
  return r.json();
}

export async function rollback(name: string): Promise<ApplyResp> {
  const r = await fetch("/dashboard/api/updater/rollback", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return r.json();
}
