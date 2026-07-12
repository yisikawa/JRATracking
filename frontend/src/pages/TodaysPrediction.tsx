import { useEffect, useState } from "react";
import { scrapeApi, modelApi } from "../api/client";

const PLACE_CODES: Record<string, string> = {
  "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
  "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
};

function raceLabel(id: string) {
  const venue = PLACE_CODES[id.slice(4, 6)] ?? id.slice(4, 6);
  return `${venue} ${parseInt(id.slice(10, 12))}R  (${id})`;
}

type PredictResult = { jockey: string; jockey_name?: string; horse: string; horse_name?: string; win_pct: number; win_pct_norm?: number | null; top3_pct: number; status: string };
type ShutItem = { horse_name: string; horse_id?: string; jockey: string; jockey_id?: string; bracket_number: number; horse_number: number; sex?: string; age?: number; weight?: number; trainer?: string };

const STATUS_BADGE: Record<string, [string, string]> = {
  known:          ["badge-green",  "✓"],
  jockey_unknown: ["badge-yellow", "⚠騎手"],
  horse_unknown:  ["badge-yellow", "⚠馬"],
  both_unknown:   ["badge-red",    "⚠両方"],
};

export default function TodaysPrediction() {
  const today = new Date().toISOString().slice(0, 10);
  const [fetchDate, setFetchDate] = useState(today);
  const [raceIds, setRaceIds] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(false);
  const [predicting, setPredicting] = useState(false);
  const [results, setResults] = useState<PredictResult[] | null>(null);
  const [shutuba, setShutuba] = useState<ShutItem[] | null>(null);
  const [meta, setMeta] = useState("");
  const [error, setError] = useState("");
  const [modelTrained, setModelTrained] = useState(false);

  useEffect(() => {
    modelApi.status().then((s) => setModelTrained(s.trained)).catch(() => {});
  }, []);

  const handleGetRaces = async () => {
    setLoading(true);
    setError("");
    setRaceIds([]);
    setSelectedId("");
    setResults(null);
    setShutuba(null);
    try {
      const { race_ids } = await scrapeApi.upcoming(fetchDate);
      setRaceIds(race_ids);
      if (race_ids.length) setSelectedId(race_ids[0]);
      else setError("レースが見つかりません。開催がない日か、まだ公開されていない可能性があります。");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handlePredict = async () => {
    if (!selectedId) return;
    setPredicting(true);
    setError("");
    setResults(null);
    try {
      const data = await scrapeApi.shutuba(selectedId) as { entries?: ShutItem[]; _error?: string; race_name?: string; location?: string; course_type?: string; distance?: number; weather?: string };
      if (data._error || !data.entries?.length) {
        setError(data._error as string ?? "出馬表の取得に失敗しました。");
        return;
      }
      const entries = data.entries;
      setShutuba(entries);
      const parts = [data.location, data.course_type && data.distance ? `${data.course_type}${data.distance}m` : "", data.weather].filter(Boolean);
      setMeta(`${data.race_name ?? selectedId}　${parts.join(" / ")}`);

      const input = entries.map((e) => ({
        jockey: e.jockey_id ?? e.jockey,
        horse: e.horse_id ?? e.horse_name,
      }));
      const pred = await modelApi.predict(input, true);
      setResults(pred);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPredicting(false);
    }
  };

  if (!modelTrained) {
    return (
      <div>
        <h2 className="page-title">今日のレース予測</h2>
        <div className="alert alert-warning">
          先に「分析・予測」→「モデル学習」を実行してください。
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2 className="page-title">今日のレース予測</h2>
      <div className="card">
        <div className="card-title">レース選択</div>
        <div className="flex gap-2 items-center flex-wrap flex-col-sp" style={{ marginBottom: 14 }}>
          <input type="date" className="form-input" style={{ maxWidth: 180 }}
            value={fetchDate} onChange={(e) => setFetchDate(e.target.value)} />
          <button className="btn btn-ghost btn-block" onClick={handleGetRaces} disabled={loading}>
            {loading ? <><span className="spinner" /> 取得中...</> : "レース一覧を取得"}
          </button>
        </div>

        {raceIds.length > 0 && (
          <div className="flex gap-2 items-center flex-wrap flex-col-sp">
            <select className="form-select" style={{ maxWidth: 280 }}
              value={selectedId} onChange={(e) => setSelectedId(e.target.value)}>
              {raceIds.map((id) => (
                <option key={id} value={id}>{raceLabel(id)}</option>
              ))}
            </select>
            <button className="btn btn-primary btn-block" onClick={handlePredict} disabled={predicting}>
              {predicting ? <><span className="spinner" /> 予測中...</> : "出馬表取得 → 予測実行"}
            </button>
          </div>
        )}

        {error && <div className="alert alert-warning mt-4">{error}</div>}
      </div>

      {results && shutuba && (
        <div className="card">
          <div className="card-title">{meta}</div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>枠</th><th>馬番</th><th>馬名</th><th>性齢</th>
                  <th>斤量</th><th>騎手</th><th>調教師</th>
                  <th>状態</th><th>勝率 (%)</th><th>正規化勝率 (%)</th><th>3着内率 (%)</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => {
                  const s = shutuba.find((e) => (e.horse_id ?? e.horse_name) === r.horse);
                  const [cls, label] = STATUS_BADGE[r.status] ?? ["badge-yellow", r.status];
                  return (
                    <tr key={i}>
                      <td>{s?.bracket_number ?? "—"}</td>
                      <td>{s?.horse_number ?? "—"}</td>
                      <td><strong>{r.horse_name ?? r.horse}</strong></td>
                      <td>{s ? `${s.sex ?? ""}${s.age ?? ""}` : "—"}</td>
                      <td>{s?.weight ?? "—"}</td>
                      <td>{r.jockey_name ?? r.jockey}</td>
                      <td className="text-muted">{s?.trainer ?? "—"}</td>
                      <td><span className={`badge ${cls}`}>{label}</span></td>
                      <td><strong>{r.win_pct}</strong></td>
                      <td><strong>{r.win_pct_norm ?? "—"}</strong></td>
                      <td>{r.top3_pct}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
