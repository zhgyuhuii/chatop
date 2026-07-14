import { describe, it, expect, vi } from "vitest";
import { performRollback } from "./rollbackFlow";
import type { ApplyResp } from "./updaterApi";

describe("performRollback", () => {
  it("clears busy and leaves msg empty on success", async () => {
    const setBusy = vi.fn();
    const setMsg = vi.fn();
    const reload = vi.fn().mockResolvedValue(undefined);
    const rollback = vi.fn().mockResolvedValue(
      { ok: true, name: "station", version: "1.6.0", detail: "rolled back" } satisfies ApplyResp);
    await performRollback("station", { rollback, setBusy, setMsg, reload });
    expect(setBusy).toHaveBeenCalledWith("station");
    expect(setBusy).toHaveBeenLastCalledWith("");
    expect(reload).toHaveBeenCalled();
    expect(setMsg).toHaveBeenLastCalledWith("");
  });

  it("surfaces res.detail and still clears busy when ok is false", async () => {
    const setBusy = vi.fn();
    const setMsg = vi.fn();
    const reload = vi.fn().mockResolvedValue(undefined);
    const rollback = vi.fn().mockResolvedValue(
      { ok: false, name: "station", version: "", detail: "no previous version" } satisfies ApplyResp);
    await performRollback("station", { rollback, setBusy, setMsg, reload });
    expect(setMsg).toHaveBeenLastCalledWith("回滚失败：no previous version");
    expect(setBusy).toHaveBeenLastCalledWith("");
  });

  it("clears busy even when rollback() throws, and shows a generic failure message", async () => {
    const setBusy = vi.fn();
    const setMsg = vi.fn();
    const reload = vi.fn().mockResolvedValue(undefined);
    const rollback = vi.fn().mockRejectedValue(new Error("network down"));
    await expect(performRollback("station", { rollback, setBusy, setMsg, reload })).resolves.toBeUndefined();
    expect(setBusy).toHaveBeenLastCalledWith("");
    expect(setMsg).toHaveBeenLastCalledWith("回滚失败");
    expect(reload).not.toHaveBeenCalled();
  });
});
