import { describe, it, expect, vi } from "vitest";
import { fetchVersions, applyBundle } from "./updaterApi";

describe("updaterApi", () => {
  it("fetchVersions hits the versions endpoint", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ services: [{ name: "station", active: "1.6.0", path: "/x" }] }),
        { status: 200 }));
    const r = await fetchVersions();
    expect(spy).toHaveBeenCalledWith("/dashboard/api/updater/versions");
    expect(r.services[0].name).toBe("station");
  });

  it("applyBundle posts name+version", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true, name: "station", version: "1.7.0", detail: "applied" }),
        { status: 200 }));
    const r = await applyBundle("station", "1.7.0");
    expect(spy).toHaveBeenCalledWith("/dashboard/api/updater/apply", expect.objectContaining({ method: "POST" }));
    expect(r.ok).toBe(true);
  });
});
