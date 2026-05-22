import { useEffect, useState } from "react";
import { dbApi, modelApi } from "../api/client";

export default function Dashboard() {
  const [stats, setStats] = useState<{ races: number; horses: number; entries: number; results: number } | null>(null);
  const [model, setModel] = useState<{ trained: boolean; mode?: string; jockeys?: number; horses?: number } | null>(null);

  useEffect(() => {
    dbApi.stats().then(setStats).catch(() => {});
    modelApi.status().then(setModel).catch(() => {});
  }, []);

  return (
    <div>
      <h2 className="page-title">ダッシュボード</h2>

      <div className="card">
        <div className="card-title">データベース統計</div>
        {stats ? (
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-value">{stats.races.toLocaleString()}</div>
              <div className="stat-label">レース</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.horses.toLocaleString()}</div>
              <div className="stat-label">馬</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.entries.toLocaleString()}</div>
              <div className="stat-label">出走記録</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.results.toLocaleString()}</div>
              <div className="stat-label">レース結果</div>
            </div>
          </div>
        ) : (
          <div className="flex gap-2 items-center text-muted">
            <span className="spinner" /> 読み込み中...
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-title">モデル状態</div>
        {model ? (
          model.trained ? (
            <div className="alert alert-success">
              ✅ 学習済み（モード: {model.mode}）　騎手 {model.jockeys} 名 / 馬 {model.horses} 頭
            </div>
          ) : (
            <div className="alert alert-warning">
              ⚠ モデル未学習。「分析・予測」でモデルを学習してください。
            </div>
          )
        ) : (
          <div className="flex gap-2 items-center text-muted">
            <span className="spinner" /> 読み込み中...
          </div>
        )}
      </div>

      {stats && stats.races === 0 && (
        <div className="alert alert-info">
          データがありません。「データ収集」からレース結果を取得してください。
        </div>
      )}
    </div>
  );
}
