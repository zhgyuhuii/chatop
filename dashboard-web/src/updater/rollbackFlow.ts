import type { ApplyResp } from "./updaterApi";

export interface RollbackFlowDeps {
  rollback: (name: string) => Promise<ApplyResp>;
  setBusy: (name: string) => void;
  setMsg: (msg: string) => void;
  reload: () => Promise<void>;
}

/**
 * 封装「回滚上一版」按钮点击后的完整流程：始终清 busy（哪怕抛错），
 * 并把 `res.ok === false`（例如"没有上一版本"）或异常都转成用户可见的中文提示，
 * 而不是让按钮永久卡在 disabled 状态却什么都不说。
 */
export async function performRollback(name: string, deps: RollbackFlowDeps): Promise<void> {
  const { rollback, setBusy, setMsg, reload } = deps;
  setBusy(name);
  setMsg("");
  try {
    const res = await rollback(name);
    if (!res.ok) {
      setMsg(`回滚失败：${res.detail || "未知错误"}`);
      return;
    }
    await reload();
  } catch {
    setMsg("回滚失败");
  } finally {
    setBusy("");
  }
}
