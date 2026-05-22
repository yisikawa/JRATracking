import { useEffect, useRef, useState } from "react";
import { dbApi } from "../api/client";

type Stats = { races: number; horses: number; entries: number; results: number };
type RaceRow = { id: string; name: string; date: string; location: string; course_type: string; distance: number };

const TABLES = ["races", "horses", "entries", "results"] as const;
type Table = typeof TABLES[number];

export default function DatabaseManager() {
  const [tab, setTab] = useState(0);
  const [stats, setStats] = useState<Stats | null>(null);
  const [tableData, setTableData] = useState<Record<string, unknown>[]>([]);
  const [selectedTable, setSelectedTable] = useState<Table>("races");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [deleteId, setDeleteId] = useState("");
  const [importTable, setImportTable] = useState<Table>("races");
  const fileRef = useRef<HTMLInputElement>(null);

  const loadStats = () => dbApi.stats().then(setStats).catch(() => {});

  useEffect(() => { loadStats(); }, []);

  const loadTable = async (t: Table) => {
    setLoading(true);
    setMsg("");
    try {
      const data = await dbApi.getTable(t);
      setTableData(data);
    } catch (e: unknown) {
      setMsg(`error:${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (tab === 0) loadTable(selectedTable);
  }, [selectedTable, tab]);

  const handleDelete = async () => {
    if (!deleteId) return;
    if (!confirm(`レース ${deleteId} を削除しますか？関連データも全て削除されます。`)) return;
    try {
      await dbApi.deleteRace(deleteId);
      setMsg("success:削除しました。");
      loadStats();
      loadTable(selectedTable);
      setDeleteId("");
    } catch (e: unknown) {
      setMsg(`error:${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const handleImport = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`/api/db/${importTable}/import`, { method: "POST", body: form });
      const data = await res.json();
      setMsg(`success:${data.count} 件インポートしました。`);
      loadStats();
    } catch (e: unknown) {
      setMsg(`error:${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const handleReset = async () => {
    if (!confirm("全データを削除してデータベースを初期化しますか？この操作は取り消せません。")) return;
    try {
      await dbApi.resetDb();
      setMsg("success:データベースを初期化しました。");
      loadStats();
      setTableData([]);
    } catch (e: unknown) {
      setMsg(`error:${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const renderMsg = (msg: string) => {
    const [type, text] = msg.split(/:(.+)/);
    const cls = type === "success" ? "alert-success" : type === "error" ? "alert-danger" : "alert-info";
    return <div className={`alert ${cls}`}>{text}</div>;
  };

  return (
    <div>
      <h2 className="page-title">データベース管理</h2>

      {stats && (
        <div className="stats-grid">
          {(["races", "horses", "entries", "results"] as const).map((k) => (
            <div className="stat-card" key={k}>
              <div className="stat-value">{stats[k].toLocaleString()}</div>
              <div className="stat-label">{k}</div>
            </div>
          ))}
        </div>
      )}

      {msg && renderMsg(msg)}

      <div className="tabs">
        {["データ閲覧・削除", "エクスポート / インポート", "メンテナンス"].map((t, i) => (
          <button key={i} className={`tab${tab === i ? " active" : ""}`} onClick={() => setTab(i)}>{t}</button>
        ))}
      </div>

      {/* Tab 0: browse */}
      {tab === 0 && (
        <div className="card">
          <div className="flex gap-2 items-center" style={{ marginBottom: 14 }}>
            <select className="form-select" style={{ maxWidth: 160 }}
              value={selectedTable}
              onChange={(e) => setSelectedTable(e.target.value as Table)}>
              {TABLES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            {loading && <span className="spinner" />}
          </div>

          {tableData.length > 0 ? (
            <div className="table-wrap" style={{ maxHeight: 400, overflowY: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>{Object.keys(tableData[0]).map((k) => <th key={k}>{k}</th>)}</tr>
                </thead>
                <tbody>
                  {tableData.map((row, i) => (
                    <tr key={i}>
                      {Object.values(row).map((v, j) => (
                        <td key={j}>{String(v ?? "")}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            !loading && <div className="alert alert-info">データがありません。</div>
          )}

          {selectedTable === "races" && (
            <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
              <div className="card-title" style={{ fontSize: 14 }}>レース削除</div>
              <div className="alert alert-warning" style={{ marginBottom: 10 }}>
                削除すると関連する出走データ・結果データも削除されます。
              </div>
              <div className="flex gap-2 items-center">
                <select className="form-select" style={{ maxWidth: 340 }}
                  value={deleteId} onChange={(e) => setDeleteId(e.target.value)}>
                  <option value="">— レースを選択 —</option>
                  {tableData.map((r) => {
                    const race = r as RaceRow;
                    return (
                      <option key={race.id} value={race.id}>
                        {race.date} — {race.name} ({race.id})
                      </option>
                    );
                  })}
                </select>
                <button className="btn btn-danger" onClick={handleDelete} disabled={!deleteId}>
                  削除
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab 1: export/import */}
      {tab === 1 && (
        <div className="card">
          <div className="card-title">エクスポート</div>
          <div className="flex gap-2" style={{ flexWrap: "wrap", marginBottom: 24 }}>
            {TABLES.map((t) => (
              <a key={t} href={dbApi.exportUrl(t)} download={`${t}.csv`} className="btn btn-ghost">
                {t}.csv をダウンロード
              </a>
            ))}
          </div>

          <div className="card-title" style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }}>
            インポート
          </div>
          <div className="form-group">
            <label className="form-label">インポート先テーブル</label>
            <select className="form-select" style={{ maxWidth: 160 }}
              value={importTable} onChange={(e) => setImportTable(e.target.value as Table)}>
              {TABLES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">CSV ファイル</label>
            <input type="file" accept=".csv" ref={fileRef} className="form-input" style={{ maxWidth: 280 }} />
          </div>
          <button className="btn btn-primary" onClick={handleImport}>インポート実行</button>
        </div>
      )}

      {/* Tab 2: maintenance */}
      {tab === 2 && (
        <div className="card">
          <div className="card-title" style={{ color: "var(--danger)" }}>危険な操作</div>
          <div className="alert alert-danger" style={{ marginBottom: 14 }}>
            以下の操作は取り消せません。実行前に必ずデータをエクスポートしてください。
          </div>
          <button className="btn btn-danger" onClick={handleReset}>
            データベースを全削除（初期化）
          </button>
        </div>
      )}
    </div>
  );
}
