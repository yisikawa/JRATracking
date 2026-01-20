# JRA Tracking & Analysis App

JRA（日本中央競馬会）の公式データベースからレース結果を取得し、ベイズ推定を用いて騎手や競走馬の能力を分析・可視化するためのアプリケーションです。

## 機能

- **データ収集 (Data Collection)**:
  - JRA公式サイトのレース結果ページからデータをスクレイピングします。
  - レース情報、競走馬、騎手、着順などのデータを取得し、ローカルデータベース (`jra_data.db`) に保存します。

- **分析・予測 (Analysis & Prediction)**:
  - 収集したデータを元に、Stan (CmdStanPy) を使用したベイズ推定モデルで学習を行います。
  - **騎手能力 (beta_j)**: 各騎手の実力を数値化し、ランキング形式で表示します。
  - **馬能力 (beta_h)**: 各競走馬の実力を数値化し、ランキング形式で表示します。
  - 推定結果には不確実性（標準偏差や信用区間）も表示されます。

## 必要条件

- Python 3.8 以上
- 以下のPythonライブラリ（`requirements.txt`に含まれています）:
  - streamlit
  - pandas
  - requests
  - beautifulsoup4
  - sqlalchemy
  - cmdstanpy
  - plotly
- **CmdStan**: ベイズ推定を行うためのStanのコマンドラインインターフェース

## インストール手順

1. **ディレクトリの移動**:
   ```bash
   cd JRATracking
   ```

2. **依存ライブラリのインストール**:
   ```bash
   pip install -r requirements.txt
   ```

3. **CmdStanのインストール**:
   `cmdstanpy`を使用するために、CmdStan本体をインストールする必要があります。以下のコマンドを実行してください。
   ```bash
   install_cmdstan
   ```
   ※ 初回実行時にのみ必要です。詳細は [CmdStanPyのドキュメント](https://cmdstanpy.readthedocs.io/en/stable/installation.html) を参照してください。

## 使い方

1. **アプリケーションの起動**:
   ```bash
   streamlit run main.py
   ```

2. **ブラウザでアクセス**:
   通常は自動的にブラウザが開きますが、開かない場合は `http://localhost:8501` にアクセスしてください。

3. **データの収集**:
   - サイドバーのメニューから「データ収集」を選択します。
   - JRAデータベースの「競走成績」ページのURLを入力します（例: `https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde...`）。
   - 「データ取得開始」ボタンをクリックします。

4. **分析の実行**:
   - サイドバーのメニューから「分析・予測」を選択します。
   - 「モデル学習 (データ更新)」ボタンをクリックします。
   - 学習が完了すると、騎手と馬の能力ランキングが表示されます。

## ファイル構成

- `main.py`: アプリケーションのメインファイル (Streamlit)。
- `data/`
  - `scraper.py`: Webスクレイピングロジック。
  - `database.py`: データベース定義と操作。
- `analysis/`
  - `predictor.py`: Stanモデルのラッパー、学習・予測ロジック。
  - `jra_model.stan`: ベイズ推定モデルの定義ファイル。
- `requirements.txt`: 依存ライブラリ一覧。

## 注意事項

- スクレイピングを行う際は、対象サイトの負荷にならないよう注意してください（本アプリには待機時間が設定されています）。
- サイトの構造変更により、スクレイピングが機能しなくなる可能性があります。

## CSVフォーマット (CSV Format)

インポート・エクスポート機能で使用するCSVファイルの各カラム仕様は以下の通りです。

### Races (レース情報)
| Column            | Description         | Example              |
| ----------------- | ------------------- | -------------------- |
| `id`              | レースID (Unique)    | `202601060101`       |
| `name`            | レース名            | `4歳以上1勝クラス`   |
| `date`            | 開催日 (YYYY-MM-DD) | `2026-01-05`         |
| `location`        | 開催場所            | `中山`               |
| `course_type`     | コース区分          | `芝`                 |
| `distance`        | 距離 (m)            | `2000`               |
| `weather`         | 天候                | `晴`                 |
| `track_condition` | 馬場状態            | `良`                 |

### Horses (競走馬)
| Column | Description        | Example                    |
| ------ | ------------------ | -------------------------- |
| `id`   | 馬ID/馬名 (Unique) | `ドウデュース`             |
| `name` | 馬名               | `ドウデュース`             |
| `sire` | 父                 | `ハーツクライ`             |
| `dam`  | 母                 | `ダストアンドダイヤモンズ` |

### Entries (出走情報)
| Column           | Description | Example        |
| ---------------- | ----------- | -------------- |
| `race_id`        | レースID    | `202601060101` |
| `horse_id`       | 馬ID        | `ドウデュース` |
| `bracket_number` | 枠番        | `5`            |
| `horse_number`   | 馬番        | `7`            |
| `jockey`         | 騎手        | `武豊`         |
| `trainer`        | 調教師      | `友道康夫`     |
| `weight`         | 斤量        | `58.0`         |

### Results (レース結果)
| Column         | Description | Example        |
| -------------- | ----------- | -------------- |
| `race_id`      | レースID    | `202601060101` |
| `horse_id`     | 馬ID        | `ドウデュース` |
| `rank`         | 着順        | `1`            |
| `time_seconds` | タイム (秒) | `118.5`        |
| `odds`         | オッズ      | `2.5`          |

