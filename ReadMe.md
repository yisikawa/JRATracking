# JRA Tracking & Analysis App

[netkeiba.com](https://db.netkeiba.com) からレース結果を取得し、ベイズ推定（NumPyro / JAX）を用いて騎手や競走馬の能力を分析・予測するアプリケーションです。

**React + FastAPI** によるフロントエンド / バックエンド分離構成で、PC・スマートフォン両対応のレスポンシブUIを提供します。

---

## 機能

- **データ収集**
  - 日付指定・レースID指定・期間一括収集（1〜5年分）
  - 取得済みレースは自動スキップ（重複なし）
  - 一括収集の進捗をリアルタイムで表示

- **分析・予測（ベイズ推定）**
  - NumPyro / JAX による階層ベイズモデル
  - 学習モード: 高速 (ADVI) / 標準 MCMC / 精密 MCMC
  - 学習進捗を SSE（Server-Sent Events）でブラウザにリアルタイム通知
  - 学習済みモデルを `jra_model.pkl` に保存し、再起動後も維持
  - 騎手能力ランキング・馬能力ランキング表示
  - 出走馬リストの勝率・3着内率予測

- **今日のレース予測**
  - 当日出馬表を自動取得 → 学習済みモデルで即時予測
  - 未知の騎手・馬は「平均能力」として自動処理

- **データベース管理**
  - テーブル閲覧・レース単位での削除
  - CSV エクスポート / インポート
  - データベース初期化

---

## 技術スタック

| 区分 | 技術 |
|------|------|
| フロントエンド | React 18 + TypeScript + Vite |
| バックエンド | FastAPI + Uvicorn |
| ベイズ推定 | NumPyro / JAX |
| データベース | SQLite（SQLAlchemy） |
| スクレイピング | requests + BeautifulSoup4 |

---

## 必要条件

- Python 3.11 以上
- Node.js 18 以上（フロントエンドのビルド用）

---

## インストール手順

### 1. 仮想環境の作成とバックエンド依存ライブラリのインストール

```bat
cd D:\LLMprojects\JRATracking
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

> **JAX について**  
> CPU版は `requirements.txt` に含まれています。GPU (CUDA) を使う場合は別途インストールしてください。  
> ```bat
> pip install --upgrade "jax[cuda12_pip]" -f https://storage.googleapis.com/jax-releases/jax_cuda_releases.html
> ```

### 2. フロントエンド依存ライブラリのインストール

```bat
cd frontend
npm install
cd ..
```

---

## 起動方法

`start.bat` をダブルクリックするか、コマンドプロンプトから実行します。

```bat
start.bat
```

- **バックエンド**: `http://localhost:8000` で起動
- **フロントエンド**: `http://localhost:5151` で起動（ブラウザで開く）

### LAN内の他PCからアクセスする場合

同じネットワーク内の他のPCやスマートフォンから以下のURLでアクセスできます。

```
http://<このPCのIPアドレス>:5151
```

---

## 使い方

### 1. データ収集

サイドバーの「データ収集」を選択します。

| タブ | 操作 |
|------|------|
| 日付指定 | 開催日を選択 → 「一覧取得 → 全レース保存」 |
| レースID / URL指定 | 12桁のレースID または netkeiba のURL を入力 |
| 一括収集 | 収集年数（1〜5年）を選択 → 「一括収集開始」（進捗バーで状況確認） |

### 2. モデル学習

「分析・予測」→「モデル学習」ボタンをクリックします。

| モード | 所要時間 | 特徴 |
|--------|----------|------|
| 高速 (ADVI) | 数秒〜数分 | 近似解・大量データ向き |
| 標準 (MCMC) | 数分 | chains=2 |
| 精密 (MCMC) | 10分以上 | chains=4・最高精度 |

学習完了後、騎手・馬のランキングが表示されます。モデルはファイル保存されるため再起動後も維持されます。

### 3. 勝率予測（手動入力）

「分析・予測」→「勝率予測」タブで騎手名・馬名を入力して「予測実行」をクリックします。

### 4. 今日のレース予測

1. 先に「分析・予測」でモデル学習を完了させます。
2. 「今日のレース予測」→ 開催日を選択 → 「レース一覧を取得」
3. レースを選択 → 「出馬表取得 → 予測実行」

---

## ファイル構成

```
JRATracking/
├── backend/
│   ├── main.py              # FastAPI アプリ・起動エントリーポイント
│   └── routers/
│       ├── scraping.py      # スクレイピング API (/api/scrape/*)
│       ├── model.py         # 学習・予測 API (/api/model/*)
│       └── db_router.py     # DB管理 API (/api/db/*)
├── frontend/
│   ├── src/
│   │   ├── api/client.ts    # バックエンド API クライアント
│   │   ├── components/
│   │   │   └── Layout.tsx   # サイドバー・レスポンシブレイアウト
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── DataCollection.tsx
│   │   │   ├── Analysis.tsx
│   │   │   ├── TodaysPrediction.tsx
│   │   │   └── DatabaseManager.tsx
│   │   └── index.css        # グローバルスタイル
│   ├── package.json
│   └── vite.config.ts
├── data/
│   ├── scraper.py           # netkeiba スクレイピングロジック
│   └── database.py          # SQLAlchemy モデル定義・DB初期化
├── analysis/
│   └── predictor.py         # NumPyro ベイズモデル・学習・予測
├── jra_data.db              # SQLite データベース
├── jra_model.pkl            # 学習済みモデル（学習後に自動生成）
├── requirements.txt         # Python 依存ライブラリ
└── start.bat                # アプリ起動スクリプト
```

---

## API エンドポイント

| メソッド | パス | 概要 |
|---------|------|------|
| GET | `/api/scrape/by-date?date_str=YYYY-MM-DD` | 日付指定でレースID一覧取得 |
| POST | `/api/scrape/race` | レース結果をスクレイピング・保存 |
| GET | `/api/scrape/bulk/stream?years=N` | 一括収集（SSEストリーム） |
| GET | `/api/scrape/upcoming?date_str=YYYY-MM-DD` | 当日出馬表レースID一覧 |
| GET | `/api/scrape/shutuba/{race_id}` | 出馬表取得 |
| GET | `/api/model/status` | モデル学習状態の確認 |
| POST | `/api/model/train/start?mode=advi\|fast\|standard` | 学習開始 |
| GET | `/api/model/train/stream/{task_id}` | 学習進捗（SSEストリーム） |
| GET | `/api/model/rankings` | 騎手・馬ランキング取得 |
| POST | `/api/model/predict` | 勝率予測 |
| GET | `/api/db/stats` | DB統計（件数） |
| GET | `/api/db/{table}` | テーブルデータ取得 |
| DELETE | `/api/db/race/{race_id}` | レース削除（関連データ含む） |
| GET | `/api/db/{table}/export` | CSV ダウンロード |
| POST | `/api/db/{table}/import` | CSV インポート |
| DELETE | `/api/db/reset` | DB全初期化 |

---

## レースID の形式

```
YYYY CC KK DD NN
2026 06 01 06 12
↑年  ↑開催場 ↑回 ↑日 ↑レース番号
```

**開催場コード:**

| コード | 開催場 | コード | 開催場 |
|:---:|---|:---:|---|
| 01 | 札幌 | 06 | 中山 |
| 02 | 函館 | 07 | 中京 |
| 03 | 福島 | 08 | 京都 |
| 04 | 新潟 | 09 | 阪神 |
| 05 | 東京 | 10 | 小倉 |

---

## 注意事項

- スクレイピングはリクエスト間に **1秒の待機** を設けており、サーバーへの負荷を最小限にしています。
- サイト構造の変更によりスクレイピングが機能しなくなる場合があります。
- 一括収集の目安: 1年分 ≒ 20〜30分（ネットワーク環境による）。
- Windowsファイアウォールで **ポート 5151・8000** を開放しないと、LAN内の他PCからアクセスできません。
