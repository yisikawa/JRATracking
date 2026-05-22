import { useState } from "react";
import { scrapeApi } from "../api/client";

type BulkEvent = {
  progress?: number;
  date?: string;
  saved?: number;
  failed?: number;
  skipped?: number;
  done?: boolean;
};

export default function DataCollection() {
  const [tab, setTab] = useState(0);

  // --- by date ---
  const [dateVal, setDateVal] = useState("");
  const [dateLoading, setDateLoading] = useState(false);
  const [dateMsg, setDateMsg] = useState("");

  // --- by ID ---
  const [raceInput, setRaceInput] = useState("202601060112");
  const [idLoading, setIdLoading] = useState(false);
  const [idMsg, setIdMsg] = useState("");
  const [idResult, setIdResult] = useState<{ race_name?: string; location?: string } | null>(null);

  // --- bulk ---
  const [bulkYears, setBulkYears] = useState(1);
  const [bulkState, setBulkState] = useState<BulkEvent | null>(null);
  const [bulkRunning, setBulkRunning] = useState(false);

  const handleByDate = async () => {
    if (!dateVal) return;
    setDateLoading(true);
    setDateMsg("");
    try {
      const { race_ids } = await scrapeApi.byDate(dateVal);
      if (!race_ids.length) {
        setDateMsg("error:指定日のレースが見つかりませんでした。JRA非開催日か、結果未確定の可能性があります。");
        return;
      }
      setDateMsg(`info:${race_ids.length} レースを取得します: ${race_ids.join(", ")}`);
      let saved = 0, failed = 0;
      for (const id of race_ids) {
        const r = await scrapeApi.scrapeRace(id);
        r.success ? saved++ : failed++;
      }
      setDateMsg(`success:完了 — ${saved} レース保存 / ${failed} 件失敗`);
    } catch (e: unknown) {
      setDateMsg(`error:${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setDateLoading(false);
    }
  };

  const handleById = async () => {
    setIdLoading(true);
    setIdMsg("");
    setIdResult(null);
    try {
      const r = await scrapeApi.scrapeRace(raceInput);
      if (r.success) {
        setIdResult(r);
        setIdMsg("success:データを保存しました。");
      } else {
        setIdMsg("error:データ取得に失敗しました。レースIDを確認してください。");
      }
    } catch (e: unknown) {
      setIdMsg(`error:${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setIdLoading(false);
    }
  };

  const handleBulk = () => {
    setBulkRunning(true);
    setBulkState(null);
    const es = new EventSource(`/api/scrape/bulk/stream?years=${bulkYears}`);
    es.onmessage = (e) => {
      const data: BulkEvent = JSON.parse(e.data);
      setBulkState(data);
      if (data.done) {
        es.close();
        setBulkRunning(false);
      }
    };
    es.onerror = () => {
      es.close();
      setBulkRunning(false);
    };
  };

  const renderMsg = (msg: string) => {
    const [type, text] = msg.split(/:(.+)/);
    const cls = type === "success" ? "alert-success" : type === "error" ? "alert-danger" : "alert-info";
    return <div className={`alert ${cls}`}>{text}</div>;
  };

  return (
    <div>
      <h2 className="page-title">データ収集</h2>

      <div className="tabs">
        {["日付指定", "レースID / URL指定", "一括収集"].map((t, i) => (
          <button key={i} className={`tab${tab === i ? " active" : ""}`} onClick={() => setTab(i)}>
            {t}
          </button>
        ))}
      </div>

      {/* Tab 0: by date */}
      {tab === 0 && (
        <div className="card">
          <div className="card-title">日付指定で全レース取得</div>
          <p className="text-muted" style={{ marginBottom: 14 }}>
            指定した日のレース一覧を取得し、全結果をまとめて保存します。
          </p>
          <div className="form-group">
            <label className="form-label">開催日</label>
            <input type="date" className="form-input" style={{ maxWidth: 200 }}
              value={dateVal} onChange={(e) => setDateVal(e.target.value)} />
          </div>
          {dateMsg && renderMsg(dateMsg)}
          <button className="btn btn-primary" onClick={handleByDate} disabled={dateLoading || !dateVal}>
            {dateLoading ? <><span className="spinner" /> 取得中...</> : "一覧取得 → 全レース保存"}
          </button>
        </div>
      )}

      {/* Tab 1: by ID */}
      {tab === 1 && (
        <div className="card">
          <div className="card-title">レースID / URL 指定</div>
          <p className="text-muted" style={{ marginBottom: 14 }}>
            12桁のレースIDまたは netkeiba の URL を入力します。
          </p>
          <div className="form-group">
            <label className="form-label">レースID または URL</label>
            <input className="form-input" style={{ maxWidth: 400 }}
              value={raceInput} onChange={(e) => setRaceInput(e.target.value)}
              placeholder="202601060112" />
          </div>
          {idResult && (
            <div className="alert alert-info">
              取得成功: <strong>{idResult.race_name}</strong>（{idResult.location}）
            </div>
          )}
          {idMsg && renderMsg(idMsg)}
          <button className="btn btn-primary" onClick={handleById} disabled={idLoading}>
            {idLoading ? <><span className="spinner" /> 取得中...</> : "データ取得"}
          </button>
        </div>
      )}

      {/* Tab 2: bulk */}
      {tab === 2 && (
        <div className="card">
          <div className="card-title">一括収集</div>
          <p className="text-muted" style={{ marginBottom: 14 }}>
            指定した期間の土日レース結果を自動一括取得します（取得済みはスキップ）。
          </p>
          <div className="form-group">
            <label className="form-label">収集期間</label>
            <select className="form-select" style={{ maxWidth: 140 }}
              value={bulkYears} onChange={(e) => setBulkYears(Number(e.target.value))}>
              {[1, 2, 3, 4, 5].map((y) => (
                <option key={y} value={y}>{y}年分</option>
              ))}
            </select>
          </div>
          {bulkState && !bulkState.done && (
            <div style={{ marginBottom: 12 }}>
              <div className="flex gap-2 items-center" style={{ marginBottom: 4 }}>
                <span className="spinner" />
                <span>{bulkState.date} を処理中... {bulkState.progress}%</span>
              </div>
              <div className="progress-bar-wrap">
                <div className="progress-bar-fill" style={{ width: `${bulkState.progress}%` }} />
              </div>
              <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
                保存: {bulkState.saved} / スキップ: {bulkState.skipped} / 失敗: {bulkState.failed}
              </div>
            </div>
          )}
          {bulkState?.done && (
            <div className="alert alert-success">
              一括収集完了 — 保存: {bulkState.saved} / スキップ: {bulkState.skipped} / 失敗: {bulkState.failed}
            </div>
          )}
          <button className="btn btn-primary" onClick={handleBulk} disabled={bulkRunning}>
            {bulkRunning ? <><span className="spinner" /> 収集中...</> : "一括収集開始"}
          </button>
        </div>
      )}
    </div>
  );
}
