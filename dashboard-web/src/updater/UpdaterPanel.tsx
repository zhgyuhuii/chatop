import { useEffect, useState } from "react";
import { fetchVersions, rollback } from "./updaterApi";
import type { ServiceVersion } from "./updaterApi";

export function UpdaterPanel() {
  const [svcs, setSvcs] = useState<ServiceVersion[]>([]);
  const [busy, setBusy] = useState("");
  const reload = () => fetchVersions().then((r) => setSvcs(r.services)).catch(() => {});
  useEffect(() => { reload(); }, []);
  return (
    <div className="updater-panel">
      <h2>服务版本 · 热更</h2>
      <table>
        <thead><tr><th>服务</th><th>生效版本</th><th>操作</th></tr></thead>
        <tbody>
          {svcs.map((s) => (
            <tr key={s.name}>
              <td>{s.name}</td><td>{s.active}</td>
              <td>
                <button disabled={busy === s.name}
                  onClick={async () => { setBusy(s.name); await rollback(s.name); await reload(); setBusy(""); }}>
                  回滚上一版
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
