import { useEffect, useState } from "react";
import { modelApi } from "../api/client";

type RankRow = { name: string; score: number; std?: number };
type PredictResult = { jockey: string; horse: string; win_pct: number; top3_pct: number; status: string };
type EntryRow = { jockey: string; horse: string };

const STATUS_BADGE: Record<string, [string, string]> = {
  known:          ["badge-green",  "✓ 既知"],
  jockey_unknown: ["badge-yellow", "⚠ 騎手不明"],
  horse_unknown:  ["badge-yellow", "⚠ 馬不明"],
  both_unknown:   ["badge-red",    "⚠ 両方不明"],
};

export default function Analysis() {
  const [tab, setTab] = useState(0);
  const [mode, setMode] = useState("advi");
  const [training, setTraining] = useState(false);
  const [trainMsg, setTrainMsg] = useState("");
  const [modelTrained, setModelTrained] = useState(false);

  const [rankings, setRankings] = useState<{ jockeys: RankRow[]; horses: RankRow[]; mode: string } | null>(null);
  const [rankTab, setRankTab] = useState(0);

  const [entries, setEntries] = useState<EntryRow[]>(Array(6).fill({ jockey: "", horse: "" }).map(() => ({ jockey: "", horse: "" })));
  const [predicting, setPredicting] = useState(false);
  const [predResults, setPredResults] = useState<PredictResult[] | null>(null);

  useEffect(() => {
    modelApi.status().then((s) => setModelTrained(s.trained)).catch(() => {});
  }, []);

  const handleTrain = () => {
    setTraining(true);
    setTrainMsg("info:学習を開始しました...");
    modelApi.startTraining(mode).then(({ task_id }) => {
      const es = new EventSource(`/api/model/train/stream/${task_id}`);
      es.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.error) {
          setTrainMsg(`error:${data.error}`);
          es.close();
          setTraining(false);
        } else if (data.done) {
          setTrainMsg(`success:学習完了 — 騎手 ${data.jockeys} 名 / 馬 ${data.horses} 頭`);
          setModelTrained(true);
          es.close();
          setTraining(false);
          modelApi.rankings().then(setRankings).catch(() => {});
        }
      };
      es.onerror = () => { es.close(); setTraining(false); setTrainMsg("error:学習中にエラーが発生しました"); };
    });
  };

  const loadRankings = () => {
    modelApi.rankings().then(setRankings).catch(() => {});
  };

  useEffect(() => {
    if (modelTrained) loadRankings();
  }, [modelTrained]);

  const updateEntry = (i: number, field: "jockey" | "horse", val: string) => {
    setEntries((prev) => prev.map((e, idx) => idx === i ? { ...e, [field]: val } : e));
  };

  const addEntry = () => setEntries((prev) => [...prev, { jockey: "", horse: "" }]);

  const handlePredict = async () => {
    const valid = entries.filter((e) => e.jockey.trim() && e.horse.trim());
    if (!valid.length) return;
    setPredicting(true);
    setPredResults(null);
    try {
      const results = await modelApi.predict(valid);
      setPredResults(results);
    } finally {
      setPredicting(false);
    }
  };

  const renderMsg = (msg: string) => {
    const [type, text] = msg.split(/:(.+)/);
    const cls = type === "success" ? "alert-success" : type === "error" ? "alert-danger" : "alert-info";
    return <div className={`alert ${cls}`}>{text}</div>;
  };

  return (
    <div>
      <h2 className="page-title">分析・予測</h2>

      {/* Train section */}
      <div className="card">
        <div className="card-title">モデル学習</div>
        <div className="form-group">
          <label className="form-label">学習モード</label>
          <div className="radio-group">
            {[
              { val: "advi",     label: "高速 (ADVI)",    desc: "数秒〜数分 / 近似解" },
              { val: "fast",     label: "標準 (MCMC)",    desc: "数分 / chains=2" },
              { val: "standard", label: "精密 (MCMC)",    desc: "10分以上 / chains=4" },
            ].map(({ val, label, desc }) => (
              <label key={val} className="radio-label">
                <input type="radio" name="mode" value={val}
                  checked={mode === val} onChange={() => setMode(val)} />
                <span>
                  <div>{label}</div>
                  <div style={{ fontSize: 11, opacity: 0.7 }}>{desc}</div>
                </span>
              </label>
            ))}
          </div>
        </div>
        {trainMsg && renderMsg(trainMsg)}
        <button className="btn btn-primary" onClick={handleTrain} disabled={training}>
          {training ? <><span className="spinner" /> 学習中...</> : "モデル学習（データ更新）"}
        </button>
      </div>

      {/* Rankings + Predict (only if trained) */}
      {modelTrained && (
        <div className="card">
          <div className="tabs">
            {["能力ランキング", "勝率予測"].map((t, i) => (
              <button key={i} className={`tab${tab === i ? " active" : ""}`} onClick={() => setTab(i)}>{t}</button>
            ))}
          </div>

          {/* Rankings */}
          {tab === 0 && rankings && (
            <>
              <div className="tabs" style={{ marginTop: 0 }}>
                {["騎手ランキング", "馬ランキング"].map((t, i) => (
                  <button key={i} className={`tab${rankTab === i ? " active" : ""}`} onClick={() => setRankTab(i)}>{t}</button>
                ))}
              </div>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>順位</th>
                      <th>{rankTab === 0 ? "騎手" : "馬名"}</th>
                      <th>能力値</th>
                      {rankings.mode !== "advi" && <th>標準偏差</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {(rankTab === 0 ? rankings.jockeys : rankings.horses).slice(0, 50).map((r, i) => (
                      <tr key={r.name}>
                        <td style={{ color: "var(--text-muted)" }}>{i + 1}</td>
                        <td><strong>{r.name}</strong></td>
                        <td>{r.score}</td>
                        {rankings.mode !== "advi" && <td className="text-muted">{r.std ?? "—"}</td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* Predict */}
          {tab === 1 && (
            <>
              <p className="text-muted" style={{ marginBottom: 12 }}>
                出走馬の騎手名と馬名を入力してください。
              </p>
              <div className="table-wrap" style={{ marginBottom: 12 }}>
                <table className="entry-editor">
                  <thead>
                    <tr><th>#</th><th>騎手名</th><th>馬名</th></tr>
                  </thead>
                  <tbody>
                    {entries.map((e, i) => (
                      <tr key={i}>
                        <td style={{ width: 36, textAlign: "center", color: "var(--text-muted)" }}>{i + 1}</td>
                        <td><input placeholder="騎手名" value={e.jockey}
                          onChange={(ev) => updateEntry(i, "jockey", ev.target.value)} /></td>
                        <td><input placeholder="馬名" value={e.horse}
                          onChange={(ev) => updateEntry(i, "horse", ev.target.value)} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex gap-2" style={{ marginBottom: 16 }}>
                <button className="btn btn-ghost" onClick={addEntry}>+ 行を追加</button>
                <button className="btn btn-primary" onClick={handlePredict} disabled={predicting}>
                  {predicting ? <><span className="spinner" /> 予測中...</> : "予測実行"}
                </button>
              </div>
              {predResults && (
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr><th>騎手</th><th>馬名</th><th>状態</th><th>勝率 (%)</th><th>3着内率 (%)</th></tr>
                    </thead>
                    <tbody>
                      {predResults.map((r, i) => {
                        const [cls, label] = STATUS_BADGE[r.status] ?? ["badge-yellow", r.status];
                        return (
                          <tr key={i}>
                            <td>{r.jockey}</td>
                            <td><strong>{r.horse}</strong></td>
                            <td><span className={`badge ${cls}`}>{label}</span></td>
                            <td><strong>{r.win_pct}</strong></td>
                            <td>{r.top3_pct}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {!modelTrained && (
        <div className="alert alert-warning">モデルが未学習です。上のボタンで学習を開始してください。</div>
      )}
    </div>
  );
}
