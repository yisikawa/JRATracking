# JRA Tracking アプリ改善 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 現行アプリの正確性バグ（同名馬の衝突・タイム解析漏れ・エラー握りつぶし）と性能問題（DBエンジン多重生成・N+1クエリ）を解消し、テスト基盤を導入する。

**Architecture:** React + FastAPI 分離構成はそのまま維持。DBアクセスを共有エンジン + FastAPI `Depends` に一元化し、予測モデルは馬名ではなく horse_id をキーに学習するよう変更する（表示名はマップで解決）。

**Tech Stack:** FastAPI / SQLAlchemy / SQLite / NumPyro / React 18 + TypeScript + Vite / pytest（新規導入）

## Global Constraints

- Python 実行は必ず `venv\Scripts\python`（Windows・リポジトリ直下の venv）を使う。テスト実行コマンド: `venv\Scripts\python -m pytest tests -v`
- フロントエンドの型検証: `cd frontend && npx tsc --noEmit`
- 既存の API パス（`/api/scrape/*`, `/api/model/*`, `/api/db/*`)は変更しない。追加のみ可。
- 既存の学習済み `jra_model.pkl` を読み込んでもクラッシュしないこと（属性のバックフィルで対応）。ただし Task 5 以降は**再学習が必要**である旨を README に明記する。
- **git 運用（ユーザーのグローバル方針）:** タスク単位のローカルコミットは、実装セッション開始時にユーザーへコミット可否を確認してから行うこと。`git push` / `git merge` / PR 作成は絶対に行わない。
- コード内コメント・UI 文言は既存に合わせて日本語。

---

## 現状の課題一覧（調査結果サマリ）

| # | 重要度 | 課題 | 場所 | 対応タスク |
|---|--------|------|------|-----------|
| 1 | 高 | 全リクエストで `init_db()` → エンジン新規生成 + マイグレーション検査が毎回走る。セッションも close されない | `backend/routers/*.py` の `_get_db()` | Task 2 |
| 2 | 高 | 学習データ構築が Result 1件ごとに Entry を個別クエリ（N+1）。数万件で極端に遅い | [model.py:70-75](backend/routers/model.py#L70-L75) | Task 4 |
| 3 | 高 | モデルが**馬名**をキーに学習しており、同名馬が衝突する。horse_id は取得済みなのに未使用 | [model.py:75-80](backend/routers/model.py#L75-L80), [predictor.py:39](analysis/predictor.py#L39) | Task 5 |
| 4 | 高 | 今日のレース予測画面で騎手欄に騎手**ID**（例: 05339）が表示される（予測入力に jockey_id を使い、それをそのまま表示しているため） | [TodaysPrediction.tsx:149](frontend/src/pages/TodaysPrediction.tsx#L149) | Task 5 |
| 5 | 中 | `_parse_time` が 1 分未満のタイム（例: "58.3"）を解析できず None になる | [scraper.py:442-447](data/scraper.py#L442-L447) | Task 1 |
| 6 | 中 | `results` テーブルの `(race_id, horse_id)` にインデックスがなく、保存時の重複チェックが全走査 | [database.py:67-79](data/database.py#L67-L79) | Task 2 |
| 7 | 中 | `/rankings` が毎回 `_predictor._build_summary()`（private 呼び出し）を再計算。MCMC ではパラメータ数千件の集計が毎回走る | [model.py:128](backend/routers/model.py#L128) | Task 6 |
| 8 | 中 | 学習の排他制御なし。二重に開始すると 2 スレッドがグローバル `_predictor` を奪い合う | [model.py:55-103](backend/routers/model.py#L55-L103) | Task 6 |
| 9 | 中 | フロントの `try/finally`（catch なし）が複数箇所。fetch 失敗時に unhandled rejection となり画面にエラーが出ない | TodaysPrediction.tsx / Analysis.tsx | Task 8 |
| 10 | 中 | CSV インポートが `res.ok` を見ない。失敗時「undefined 件インポートしました」と表示 | [DatabaseManager.tsx:56-69](frontend/src/pages/DatabaseManager.tsx#L56-L69) | Task 8 |
| 11 | 中 | 予測勝率がレース内で正規化されず、1レースの合計が 100% にならない | [model.py:174-206](backend/routers/model.py#L174-L206) | Task 7 |
| 12 | 低 | `@app.on_event("startup")` は FastAPI 非推奨（lifespan へ移行） | [main.py:31-33](backend/main.py#L31-L33) | Task 3 |
| 13 | 低 | `session.query(Race).get(race_id)` は SQLAlchemy 2.0 非推奨 API | [db_router.py:52](backend/routers/db_router.py#L52) | Task 3 |
| 14 | 低 | `date.fromisoformat` の失敗が 500 になる（400 を返すべき） | [scraping.py:31](backend/routers/scraping.py#L31), [scraping.py:115](backend/routers/scraping.py#L115) | Task 2 |
| 15 | 低 | `start.bat` の案内 IP（192.168.111.228）が CORS 設定・README の固定 IP（192.168.111.10）と不一致 | [start.bat](start.bat) | Task 9 |
| 16 | 低 | テストが 1 本もない | 全体 | Task 1〜 |

## スコープ外（将来の改善案）

計画の肥大化を避けるため今回は実装しない。別計画として検討する価値があるもの:

- **一括収集の中断ボタン**（現状はブラウザを閉じるしかない。SSE 切断でジェネレータは次の yield で止まるが、1日分の処理中は止まらない）
- **レース構造を考慮したモデル**（現在は馬ごとの独立ベルヌーイ。1レース1勝の制約を持つ conditional logit / softmax への変更で精度向上が見込める）
- `print` → `logging` への移行、`_tasks` 辞書のクリーンアップ
- pickle 永続化の安全な形式（joblib / 独自シリアライズ）への変更
- CORS 許可オリジンの環境変数化
- ESLint / Prettier / フロントエンドテスト（Vitest）導入

---

### Task 1: pytest 基盤導入 + `_parse_time` の 1 分未満タイム対応

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/conftest.py`
- Create: `tests/test_scraper_utils.py`
- Modify: `data/scraper.py:442-447`（`_parse_time`）

**Interfaces:**
- Produces: `tests/conftest.py`（以降の全テストが利用する sys.path 設定）、`JRAScraper._parse_time` が `"58.3"` 形式も秒数 float で返す

- [ ] **Step 1: 開発用依存を定義しインストール**

`requirements-dev.txt` を作成:

```
pytest
httpx
```

実行: `venv\Scripts\pip install -r requirements-dev.txt`

- [ ] **Step 2: conftest.py を作成**

`tests/conftest.py`:

```python
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
```

- [ ] **Step 3: 失敗するテストを書く**

`tests/test_scraper_utils.py`:

```python
from data.scraper import JRAScraper, _normalize_jockey


def _scraper() -> JRAScraper:
    return JRAScraper(None)  # db_session はパース系メソッドでは未使用


def test_parse_time_with_minutes():
    assert _scraper()._parse_time("1:34.5") == 94.5


def test_parse_time_under_one_minute():
    # 1000m 戦など 1 分未満のタイムは "58.3" 形式で表示される
    assert _scraper()._parse_time("58.3") == 58.3


def test_parse_time_invalid():
    assert _scraper()._parse_time("") is None
    assert _scraper()._parse_time("中止") is None


def test_normalize_jockey_strips_symbols():
    assert _normalize_jockey("☆西塚") == "西塚"
    assert _normalize_jockey("ルメール") == "ルメール"


def test_extract_race_id_from_url():
    s = _scraper()
    assert s._extract_race_id("202601060112") == "202601060112"
    assert s._extract_race_id("https://db.netkeiba.com/race/202601060112/") == "202601060112"
    assert s._extract_race_id("https://race.netkeiba.com/race/shutuba.html?race_id=202601060112") == "202601060112"
```

- [ ] **Step 4: テストを実行して失敗を確認**

Run: `venv\Scripts\python -m pytest tests -v`
Expected: `test_parse_time_under_one_minute` が FAIL（None が返る）、他は PASS

- [ ] **Step 5: `_parse_time` を修正**

`data/scraper.py` の `_parse_time` を以下に置き換え:

```python
    def _parse_time(self, time_str: str):
        """'1:34.5' → 94.5、'58.3' → 58.3 のように秒数に変換する"""
        m = re.match(r'(\d+):(\d+)\.(\d+)', time_str)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 10
        m = re.match(r'^\d+\.\d+$', time_str)
        if m:
            return float(time_str)
        return None
```

- [ ] **Step 6: テストを実行して全 PASS を確認**

Run: `venv\Scripts\python -m pytest tests -v`
Expected: 全件 PASS

- [ ] **Step 7: コミット**

```bash
git add requirements-dev.txt tests/conftest.py tests/test_scraper_utils.py data/scraper.py
git commit -m "test: pytest基盤導入と1分未満タイムの解析対応"
```

---

### Task 2: DB セッション管理の一元化とインデックス追加

**Files:**
- Modify: `data/database.py`
- Create: `backend/deps.py`
- Modify: `backend/routers/scraping.py`
- Modify: `backend/routers/model.py`
- Modify: `backend/routers/db_router.py`
- Test: `tests/test_db_api.py`（新規）

**Interfaces:**
- Produces:
  - `data.database.get_session_factory(db_path: str) -> sessionmaker` — パスごとにエンジンを 1 度だけ生成しキャッシュ
  - `backend.deps.get_db()` — FastAPI 依存性（yield でセッションを返し finally で close）
  - `backend.deps.DB_PATH: str` — 本番 DB の接続文字列
  - 以降のタスクはルーター内で `session: Session = Depends(get_db)` を前提とする

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_db_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.deps import get_db
from data.database import get_session_factory


@pytest.fixture()
def client(tmp_path):
    db_path = f"sqlite:///{tmp_path / 'test.db'}"
    factory = get_session_factory(db_path)

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_session_factory_is_cached(tmp_path):
    db_path = f"sqlite:///{tmp_path / 'cache.db'}"
    assert get_session_factory(db_path) is get_session_factory(db_path)


def test_stats_empty(client):
    res = client.get("/api/db/stats")
    assert res.status_code == 200
    assert res.json() == {"races": 0, "horses": 0, "entries": 0, "results": 0}


def test_unknown_table_returns_404(client):
    res = client.get("/api/db/unknown_table")
    assert res.status_code == 404


def test_by_date_invalid_date_returns_400(client):
    res = client.get("/api/scrape/by-date?date_str=not-a-date")
    assert res.status_code == 400
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `venv\Scripts\python -m pytest tests/test_db_api.py -v`
Expected: FAIL（`backend.deps` が存在しない ImportError、`get_session_factory` 未定義）

- [ ] **Step 3: `data/database.py` を修正**

先頭の import に `Index` を追加:

```python
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, ForeignKey, UniqueConstraint, Index, text, inspect as sa_inspect
```

`Result` クラスに `__table_args__` を追加（クラス末尾、`horse = relationship(...)` の下）:

```python
    __table_args__ = (Index('ix_results_race_horse', 'race_id', 'horse_id'),)
```

ファイル末尾の `init_db` を以下に置き換え、`_migrate` にインデックス作成を追加:

```python
_factories = {}


def get_session_factory(db_path='sqlite:///jra_data.db'):
    """DBパスごとにエンジン+sessionmakerを1度だけ生成してキャッシュする"""
    if db_path not in _factories:
        engine = create_engine(db_path, connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        _migrate(engine)
        _factories[db_path] = sessionmaker(bind=engine)
    return _factories[db_path]


def init_db(db_path='sqlite:///jra_data.db'):
    """互換用: 新しいセッションを返す（エンジンは共有）"""
    return get_session_factory(db_path)()
```

`_migrate` の末尾（`with engine.connect() as conn:` ブロック内）に追加:

```python
        # 既存DB向け: 重複チェック高速化のためのインデックス
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_results_race_horse ON results (race_id, horse_id)'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_entries_race_horse ON entries (race_id, horse_id)'))
        conn.commit()
```

- [ ] **Step 4: `backend/deps.py` を作成**

```python
import pathlib

from data.database import get_session_factory

ROOT = pathlib.Path(__file__).parent.parent
DB_PATH = f"sqlite:///{ROOT / 'jra_data.db'}"


def get_db():
    session = get_session_factory(DB_PATH)()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 5: `backend/routers/scraping.py` を書き換え**

ファイル全体を以下に置き換え:

```python
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.deps import get_db, DB_PATH
from data.database import get_session_factory, Race
from data.scraper import JRAScraper

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=1)


def _parse_date(date_str: str) -> date:
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(400, "日付は YYYY-MM-DD 形式で指定してください")


class RaceScrapeRequest(BaseModel):
    race_id: str


@router.get("/by-date")
def get_races_by_date(date_str: str, session: Session = Depends(get_db)):
    target = _parse_date(date_str)
    scraper = JRAScraper(session)
    race_ids = scraper.get_race_ids_by_date(target)
    return {"race_ids": race_ids}


@router.post("/race")
def scrape_race(req: RaceScrapeRequest, session: Session = Depends(get_db)):
    scraper = JRAScraper(session)
    data = scraper.scrape_race_results(req.race_id)
    if data:
        scraper.save_to_db(data)
        return {"success": True, "race_name": data["race"].name,
                "location": data["race"].location}
    return {"success": False}


def _weekend_dates(years: int) -> list:
    today = date.today()
    try:
        start = date(today.year - years, today.month, today.day)
    except ValueError:
        start = date(today.year - years, today.month, 28)
    days = []
    d = start
    while d <= today:
        if d.weekday() in (5, 6):
            days.append(d)
        d += timedelta(days=1)
    return days


@router.get("/bulk/stream")
async def bulk_stream(years: int = 1):
    # StreamingResponse のジェネレータ内では Depends のセッションが
    # 先に close される可能性があるため、自前で生成・クローズする
    async def generate():
        loop = asyncio.get_event_loop()
        session = get_session_factory(DB_PATH)()
        try:
            scraper = JRAScraper(session)
            dates = _weekend_dates(years)
            total = len(dates)
            saved = failed = skipped = 0

            for i, d in enumerate(dates):
                race_ids = await loop.run_in_executor(
                    _executor, scraper.get_race_ids_by_date, d
                )
                for race_id in race_ids:
                    if session.query(Race).filter_by(id=race_id).first():
                        skipped += 1
                        continue
                    data = await loop.run_in_executor(
                        _executor, scraper.scrape_race_results, race_id
                    )
                    if data:
                        scraper.save_to_db(data)
                        saved += 1
                    else:
                        failed += 1

                progress = round((i + 1) / total * 100, 1)
                payload = {
                    "progress": progress,
                    "date": str(d),
                    "saved": saved,
                    "failed": failed,
                    "skipped": skipped,
                    "done": False,
                }
                yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(0)

            yield f"data: {json.dumps({'done': True, 'saved': saved, 'failed': failed, 'skipped': skipped})}\n\n"
        finally:
            session.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/upcoming")
def get_upcoming(date_str: str, session: Session = Depends(get_db)):
    target = _parse_date(date_str) if date_str else date.today()
    scraper = JRAScraper(session)
    race_ids = scraper.get_upcoming_race_ids(target)
    return {"race_ids": race_ids}


@router.get("/shutuba/{race_id}")
async def get_shutuba(race_id: str, session: Session = Depends(get_db)):
    loop = asyncio.get_event_loop()
    scraper = JRAScraper(session)
    result = await loop.run_in_executor(_executor, scraper.scrape_shutuba, race_id)
    return result
```

- [ ] **Step 6: `backend/routers/model.py` の DB アクセスを差し替え**

import 部を修正（`pathlib` は MODEL_PATH 用に残す）:

```python
import asyncio
import json
import pathlib
import pickle
import threading
import uuid

import pandas as pd
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from analysis.predictor import JRAPredictor
from backend.deps import DB_PATH
from data.database import get_session_factory, Entry, Result

ROOT = pathlib.Path(__file__).parent.parent.parent
MODEL_PATH = ROOT / "jra_model.pkl"
```

`_get_db` 関数を削除し、`start_training` 内の `train()` を以下のように変更（セッションを finally で close する。データ構築ロジック自体は Task 4 で変更するのでここでは触らない）:

```python
    def train():
        global _predictor
        session = get_session_factory(DB_PATH)()
        try:
            results = session.query(Result).all()
            if not results:
                _tasks[task_id].update({"done": True, "error": "学習データがありません"})
                return

            data = []
            for r in results:
                entry = session.query(Entry).filter_by(
                    race_id=r.race_id, horse_id=r.horse_id
                ).first()
                if entry:
                    horse_name = entry.horse.name if entry.horse else r.horse_id
                    data.append({
                        "rank":        r.rank,
                        "jockey":      entry.jockey_id or entry.jockey,
                        "jockey_name": entry.jockey,
                        "horse_id":    horse_name,
                    })

            if not data:
                _tasks[task_id].update({"done": True, "error": "有効な学習データがありません"})
                return

            df = pd.DataFrame(data)
            predictor = JRAPredictor()
            _tasks[task_id]["status"] = "training"
            predictor.train(df, mode=mode)
            _save_predictor(predictor)
            _predictor = predictor
            _tasks[task_id].update({
                "done": True,
                "status": "completed",
                "jockeys": len(predictor.known_jockeys()),
                "horses": len(predictor.known_horses()),
            })
        except Exception as e:
            _tasks[task_id].update({"done": True, "error": str(e)})
        finally:
            session.close()
```

- [ ] **Step 7: `backend/routers/db_router.py` の DB アクセスを差し替え**

import 部を修正:

```python
import io

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.deps import get_db
from data.database import Race, Horse, Entry, Result, Base
```

`ROOT` / `DB_PATH` / `_get_db` の定義を削除し、各エンドポイントの先頭 `session = _get_db()` を引数 `session: Session = Depends(get_db)` に置き換える。例:

```python
@router.get("/stats")
def get_stats(session: Session = Depends(get_db)):
    return {
        "races":   session.query(Race).count(),
        "horses":  session.query(Horse).count(),
        "entries": session.query(Entry).count(),
        "results": session.query(Result).count(),
    }
```

同様に `get_table(table: str, limit: int = 500, session: Session = Depends(get_db))`、`delete_race(race_id: str, session: Session = Depends(get_db))`、`export_csv(table: str, session: Session = Depends(get_db))`、`import_csv(table: str, file: UploadFile = File(...), session: Session = Depends(get_db))`、`reset_db(session: Session = Depends(get_db))` に変更。関数本体のロジックはそのまま。

- [ ] **Step 8: テストを実行して全 PASS を確認**

Run: `venv\Scripts\python -m pytest tests -v`
Expected: 全件 PASS

- [ ] **Step 9: アプリを起動して手動確認**

Run: `start.bat` を実行し、ダッシュボードで DB 統計が表示されることを確認（既存 `jra_data.db` にインデックスが自動追加される）。

- [ ] **Step 10: コミット**

```bash
git add data/database.py backend/deps.py backend/routers/scraping.py backend/routers/model.py backend/routers/db_router.py tests/test_db_api.py
git commit -m "refactor: DBエンジン共有化・セッションclose・インデックス追加"
```

---

### Task 3: FastAPI lifespan 移行と非推奨 API の解消

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/routers/db_router.py:52`（`delete_race` 内）

**Interfaces:**
- Consumes: Task 2 の `Depends(get_db)` 構成
- Produces: 変更なし（内部実装のみ）

- [ ] **Step 1: `backend/main.py` を lifespan に移行**

ファイル全体を以下に置き換え:

```python
import pathlib
import sys
from contextlib import asynccontextmanager

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import scraping, model, db_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # モデルを起動時にロード
    model.load_predictor()
    yield


app = FastAPI(title="JRA Tracking API", lifespan=lifespan)

ALLOWED_ORIGINS = [
    "http://192.168.111.10:5151",
    "http://localhost:5151",
    "http://127.0.0.1:5151",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(scraping.router, prefix="/api/scrape", tags=["scraping"])
app.include_router(model.router,    prefix="/api/model",  tags=["model"])
app.include_router(db_router.router, prefix="/api/db",    tags=["database"])
```

- [ ] **Step 2: `db_router.py` の legacy `Query.get` を修正**

`delete_race` 内の

```python
    race = session.query(Race).get(race_id)
```

を

```python
    race = session.get(Race, race_id)
```

に変更。

- [ ] **Step 3: テストを実行**

Run: `venv\Scripts\python -m pytest tests -v`
Expected: 全件 PASS（TestClient が lifespan 経由で起動することも確認される）

- [ ] **Step 4: コミット**

```bash
git add backend/main.py backend/routers/db_router.py
git commit -m "refactor: lifespan移行とSQLAlchemy非推奨APIの解消"
```

---

### Task 4: 学習データ構築の JOIN 化（N+1 クエリ解消）

**Files:**
- Modify: `backend/routers/model.py`
- Test: `tests/test_training_frame.py`（新規）

**Interfaces:**
- Consumes: `get_session_factory`（Task 2）
- Produces: `backend.routers.model._build_training_frame(session) -> pd.DataFrame` — 列は `rank:int, jockey:str, jockey_name:str, horse_id:str`。このタスク時点では従来互換で `horse_id` 列に**馬名**が入る（Task 5 で本物の ID に変更）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_training_frame.py`:

```python
from datetime import date

from backend.routers.model import _build_training_frame
from data.database import get_session_factory, Race, Horse, Entry, Result


def _make_session(tmp_path):
    factory = get_session_factory(f"sqlite:///{tmp_path / 'train.db'}")
    return factory()


def test_build_training_frame_joins_results_and_entries(tmp_path):
    session = _make_session(tmp_path)
    session.add(Race(id="202605010101", name="テストR", date=date(2026, 1, 1)))
    session.add(Horse(id="H1", name="テスト馬"))
    session.add(Entry(race_id="202605010101", horse_id="H1",
                      jockey="ルメール", jockey_id="J1"))
    session.add(Result(race_id="202605010101", horse_id="H1", rank=1))
    session.commit()

    df = _build_training_frame(session)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["rank"] == 1
    assert row["jockey"] == "J1"          # jockey_id 優先
    assert row["jockey_name"] == "ルメール"
    assert row["horse_id"] == "テスト馬"   # 現行互換: 馬名キー（Task 5 で H1 に変更）
    session.close()


def test_build_training_frame_empty_db(tmp_path):
    session = _make_session(tmp_path)
    df = _build_training_frame(session)
    assert df.empty
    session.close()
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `venv\Scripts\python -m pytest tests/test_training_frame.py -v`
Expected: FAIL（`_build_training_frame` が存在しない ImportError）

- [ ] **Step 3: `_build_training_frame` を実装**

`backend/routers/model.py` の import に `Horse` を追加:

```python
from data.database import get_session_factory, Entry, Horse, Result
```

`_save_predictor` の下にモジュール関数を追加:

```python
def _build_training_frame(session) -> pd.DataFrame:
    """results と entries を JOIN して学習用 DataFrame を構築する"""
    rows = (
        session.query(Result.rank, Entry.jockey_id, Entry.jockey,
                      Result.horse_id, Horse.name)
        .join(Entry, (Entry.race_id == Result.race_id) &
                     (Entry.horse_id == Result.horse_id))
        .outerjoin(Horse, Horse.id == Result.horse_id)
        .all()
    )
    data = [
        {
            "rank":        rank,
            "jockey":      jockey_id or jockey_name,
            "jockey_name": jockey_name,
            "horse_id":    horse_name or result_horse_id,
        }
        for rank, jockey_id, jockey_name, result_horse_id, horse_name in rows
    ]
    return pd.DataFrame(data)
```

- [ ] **Step 4: `train()` 内のループを差し替え**

`start_training` の `train()` 内、`results = session.query(Result).all()` から `df = pd.DataFrame(data)` までを以下に置き換え:

```python
            df = _build_training_frame(session)
            if df.empty:
                _tasks[task_id].update({"done": True, "error": "学習データがありません"})
                return
```

（`results` 変数・for ループ・`if not data:` チェックはすべて削除。）

- [ ] **Step 5: テストを実行して全 PASS を確認**

Run: `venv\Scripts\python -m pytest tests -v`
Expected: 全件 PASS

- [ ] **Step 6: コミット**

```bash
git add backend/routers/model.py tests/test_training_frame.py
git commit -m "perf: 学習データ構築をJOIN一括取得に変更しN+1を解消"
```

---

### Task 5: 馬を horse_id キーで学習（同名馬の衝突解消）+ 騎手・馬名の表示修正

**Files:**
- Modify: `analysis/predictor.py`
- Modify: `backend/routers/model.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/TodaysPrediction.tsx`
- Test: `tests/test_predictor_maps.py`（新規）、`tests/test_training_frame.py`（更新）

**Interfaces:**
- Consumes: `_build_training_frame`（Task 4）
- Produces:
  - `_build_training_frame` の `horse_id` 列が本物の horse_id になり、`horse_name` 列（表示名）が追加される
  - `JRAPredictor.horse_display_map: dict[str, str]`（horse_id → 馬名）、`JRAPredictor.horse_name_map: dict[str, str]`（馬名 → horse_id）
  - `JRAPredictor.resolve_horse_key(value: str) -> str | None` — horse_id または馬名を horse_map のキーへ解決
  - `/api/model/predict` レスポンス各行に `jockey_name: str` と `horse_name: str` が追加される

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_predictor_maps.py`:

```python
import pandas as pd

from analysis.predictor import JRAPredictor


def _df():
    return pd.DataFrame([
        {"rank": 1, "jockey": "J1", "jockey_name": "ルメール",
         "horse_id": "H1", "horse_name": "テスト馬"},
        {"rank": 4, "jockey": "J2", "jockey_name": "武豊",
         "horse_id": "H2", "horse_name": "サンプル馬"},
    ])


def test_prepare_data_builds_horse_maps():
    p = JRAPredictor()
    p.prepare_data(_df())
    assert p.horse_display_map == {"H1": "テスト馬", "H2": "サンプル馬"}
    assert p.horse_name_map == {"テスト馬": "H1", "サンプル馬": "H2"}


def test_resolve_horse_key_accepts_id_and_name():
    p = JRAPredictor()
    p.prepare_data(_df())
    assert p.resolve_horse_key("H1") == "H1"
    assert p.resolve_horse_key("テスト馬") == "H1"
    assert p.resolve_horse_key("存在しない馬") is None
```

あわせて `tests/test_training_frame.py` の assert を新仕様に更新:

```python
    assert row["horse_id"] == "H1"          # 馬IDをキーにする
    assert row["horse_name"] == "テスト馬"   # 表示名は別列
```

（コメント付きの旧行 `assert row["horse_id"] == "テスト馬" ...` を上記 2 行に置き換える。）

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `venv\Scripts\python -m pytest tests -v`
Expected: 新テスト 3 件と `test_build_training_frame_joins_results_and_entries` が FAIL

- [ ] **Step 3: `analysis/predictor.py` を修正**

`__init__` を以下に置き換え:

```python
    def __init__(self, model_path=None):  # model_path は互換性のため残す
        self.fit_result  = None
        self.fit_mode    = None   # 'advi' | 'fast' | 'standard'
        self.jockey_map  = {}     # name/id → 0-indexed int
        self.horse_map   = {}     # horse_id → 0-indexed int
        self.jockey_display_map = {}
        self.horse_display_map  = {}   # horse_id → 馬名
        self.horse_name_map     = {}   # 馬名 → horse_id
        self.summary = None
```

（`self.summary = None` は Task 6 で使うがここで一緒に追加してよい。）

`prepare_data` の `unique_horses = ...` の直後に追加:

```python
        if 'horse_name' in df.columns:
            self.horse_display_map = dict(zip(df['horse_id'], df['horse_name']))
            self.horse_name_map = {name: hid for hid, name in self.horse_display_map.items()}
```

クラス末尾（`known_horses` の後）にメソッドを追加:

```python
    def resolve_horse_key(self, value: str):
        """horse_id または馬名を horse_map のキーに解決する。未知なら None"""
        if value in self.horse_map and value != self.UNKNOWN:
            return value
        hid = self.horse_name_map.get(value)
        if hid in self.horse_map:
            return hid
        return None
```

`predict` の `h_idx = ...` 行を以下に置き換え:

```python
        resolved = [self.resolve_horse_key(e['horse']) for e in race_entries]
        h_idx = np.array([self.horse_map[k] if k is not None else unk_h for k in resolved])
```

- [ ] **Step 4: `backend/routers/model.py` を修正**

(a) `_build_training_frame` の内包表記を新仕様に変更:

```python
    data = [
        {
            "rank":        rank,
            "jockey":      jockey_id or jockey_name,
            "jockey_name": jockey_name,
            "horse_id":    result_horse_id,
            "horse_name":  horse_name or result_horse_id,
        }
        for rank, jockey_id, jockey_name, result_horse_id, horse_name in rows
    ]
```

(b) `load_predictor` に旧 pickle 向けバックフィルを追加:

```python
def load_predictor():
    global _predictor
    if MODEL_PATH.exists():
        with open(MODEL_PATH, "rb") as f:
            _predictor = pickle.load(f)
        # 旧バージョンのpickleに存在しない属性を補完
        for attr, default in [("horse_display_map", {}), ("horse_name_map", {}),
                              ("summary", None)]:
            if not hasattr(_predictor, attr):
                setattr(_predictor, attr, default)
        print(f"[model] モデルをロードしました: {MODEL_PATH}")
```

(c) `get_rankings` の馬名解決を表示マップ経由に変更。`id_to_horse` ループ内の

```python
            entry = {"name": name, "score": round(float(row["Mean"]), 3)}
```

の直前にある `for i, name in id_to_horse.items():` を `for i, key in id_to_horse.items():` に変え、ループ先頭で表示名を解決:

```python
    for i, key in id_to_horse.items():
        param = f"beta_h[{i}]"
        if param in summary.index:
            row = summary.loc[param]
            name = _predictor.horse_display_map.get(key, key)
            entry = {"name": name, "score": round(float(row["Mean"]), 3)}
```

（以降の `if not is_advi:` ブロックと `horses.append(entry)` はそのまま。）

(d) `predict` エンドポイントの結果組み立てを変更。`known_horses` の set 化を削除し、以下に置き換え:

```python
    known_jockeys = set(_predictor.known_jockeys())

    results = []
    for e, pw, pt in zip(entries, prob_win, prob_top3):
        j_ok = e.jockey in known_jockeys
        resolved_h = _predictor.resolve_horse_key(e.horse)
        h_ok = resolved_h is not None
        if j_ok and h_ok:
            status = "known"
        elif not j_ok and not h_ok:
            status = "both_unknown"
        elif not j_ok:
            status = "jockey_unknown"
        else:
            status = "horse_unknown"
        results.append({
            "jockey":      e.jockey,
            "jockey_name": _predictor.jockey_display_map.get(e.jockey, e.jockey),
            "horse":       e.horse,
            "horse_name":  _predictor.horse_display_map.get(resolved_h, e.horse),
            "win_pct":  round(float(pw) * 100, 1),
            "top3_pct": round(float(pt) * 100, 1),
            "status": status,
        })
```

- [ ] **Step 5: バックエンドテストを実行して全 PASS を確認**

Run: `venv\Scripts\python -m pytest tests -v`
Expected: 全件 PASS

- [ ] **Step 6: フロントエンドを修正**

`frontend/src/api/client.ts` の `predict` の戻り型に表示名フィールドを追加:

```ts
  predict: (entries: { jockey: string; horse: string }[]) =>
    request<
      {
        jockey: string;
        jockey_name?: string;
        horse: string;
        horse_name?: string;
        win_pct: number;
        top3_pct: number;
        status: string;
      }[]
    >("/model/predict", { method: "POST", body: JSON.stringify(entries) }),
```

`frontend/src/pages/TodaysPrediction.tsx`:

(a) 型定義を更新:

```ts
type PredictResult = { jockey: string; jockey_name?: string; horse: string; horse_name?: string; win_pct: number; top3_pct: number; status: string };
type ShutItem = { horse_name: string; horse_id?: string; jockey: string; jockey_id?: string; bracket_number: number; horse_number: number; sex?: string; age?: number; weight?: number; trainer?: string };
```

(b) 予測入力を horse_id ベースに変更（`handlePredict` 内）:

```ts
      const input = entries.map((e) => ({
        jockey: e.jockey_id ?? e.jockey,
        horse: e.horse_id ?? e.horse_name,
      }));
```

(c) テーブル行の突き合わせと表示を変更（`results.map` 内）:

```ts
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
                      <td>{r.top3_pct}</td>
                    </tr>
                  );
                })}
```

- [ ] **Step 7: 型検証**

Run: `cd frontend && npx tsc --noEmit`
Expected: エラーなし

- [ ] **Step 8: コミット**

```bash
git add analysis/predictor.py backend/routers/model.py frontend/src/api/client.ts frontend/src/pages/TodaysPrediction.tsx tests/test_predictor_maps.py tests/test_training_frame.py
git commit -m "fix: 馬をhorse_idキーで学習し同名馬の衝突と騎手ID表示を解消"
```

**注意:** この変更後、既存の `jra_model.pkl`（馬名キーで学習済み）は読み込めるが、出馬表予測では馬が unknown 扱いになる。**再学習が必要**（Task 9 の README に記載）。

---

### Task 6: ランキング summary のキャッシュと学習の二重実行防止

**Files:**
- Modify: `analysis/predictor.py`
- Modify: `backend/routers/model.py`
- Modify: `frontend/src/pages/Analysis.tsx`
- Test: `tests/test_predictor_maps.py`（追記）

**Interfaces:**
- Consumes: `JRAPredictor.summary` 属性（Task 5 の `__init__` で追加済み）
- Produces:
  - `JRAPredictor.get_summary() -> pd.DataFrame`（キャッシュ付き公開メソッド）
  - `POST /api/model/train/start` が学習中は HTTP 409、不正 mode は HTTP 400 を返す

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_predictor_maps.py` に追記:

```python
def test_get_summary_is_cached():
    p = JRAPredictor()
    p.prepare_data(_df())
    p.fit_result = {"type": "advi", "svi": None, "params": {}}
    s1 = p.get_summary()
    s2 = p.get_summary()
    assert s1 is s2  # 2回目はキャッシュが返る
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `venv\Scripts\python -m pytest tests/test_predictor_maps.py -v`
Expected: `test_get_summary_is_cached` が FAIL（`get_summary` 未定義）

- [ ] **Step 3: `analysis/predictor.py` に実装**

`train()` の末尾 `return self._build_summary()` を以下に置き換え:

```python
        self.summary = self._build_summary()
        return self.summary
```

`_build_summary` の直後に公開メソッドを追加:

```python
    def get_summary(self) -> pd.DataFrame:
        """学習時に計算した summary を返す（旧pickle向けに遅延構築も可能）"""
        if getattr(self, 'summary', None) is None:
            self.summary = self._build_summary()
        return self.summary
```

- [ ] **Step 4: `backend/routers/model.py` に排他制御を追加**

import に `HTTPException` を追加:

```python
from fastapi import APIRouter, HTTPException
```

モジュールレベル（`_tasks` の下）に追加:

```python
_train_lock = threading.Lock()
```

`start_training` の冒頭を変更:

```python
@router.post("/train/start")
def start_training(mode: str = "advi"):
    if mode not in ("advi", "fast", "standard"):
        raise HTTPException(400, f"不正な学習モードです: {mode}")
    if not _train_lock.acquire(blocking=False):
        raise HTTPException(409, "既に学習を実行中です")
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "running", "done": False, "error": None}
```

`train()` の `finally` 節にロック解放を追加:

```python
        finally:
            session.close()
            _train_lock.release()
```

`get_rankings` の summary 取得を公開メソッドに変更:

```python
    summary = _predictor.get_summary()
```

- [ ] **Step 5: `frontend/src/pages/Analysis.tsx` の学習開始に catch を追加**

`handleTrain` の `modelApi.startTraining(mode).then(...)` チェーンに catch を追加:

```ts
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
    }).catch((e: unknown) => {
      setTrainMsg(`error:${e instanceof Error ? e.message : String(e)}`);
      setTraining(false);
    });
```

- [ ] **Step 6: 検証**

Run: `venv\Scripts\python -m pytest tests -v`
Expected: 全件 PASS

Run: `cd frontend && npx tsc --noEmit`
Expected: エラーなし

- [ ] **Step 7: コミット**

```bash
git add analysis/predictor.py backend/routers/model.py frontend/src/pages/Analysis.tsx tests/test_predictor_maps.py
git commit -m "feat: summaryキャッシュ化と学習の二重実行防止(409)"
```

---

### Task 7: レース内正規化勝率の追加

**Files:**
- Modify: `backend/routers/model.py`（`predict` エンドポイント）
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/TodaysPrediction.tsx`

**Interfaces:**
- Consumes: Task 5 の `/predict` レスポンス形式
- Produces: `POST /api/model/predict?normalize=true` で各行に `win_pct_norm: float | None`（レース内合計 100% に正規化した勝率）が追加される

- [ ] **Step 1: バックエンドに normalize パラメータを追加**

`predict` エンドポイントのシグネチャを変更:

```python
@router.post("/predict")
def predict(entries: list[PredictEntry], normalize: bool = False):
```

`results.sort(...)` の直前に追加:

```python
    if normalize:
        total = sum(r["win_pct"] for r in results)
        for r in results:
            r["win_pct_norm"] = round(r["win_pct"] / total * 100, 1) if total > 0 else None
```

- [ ] **Step 2: API テストを追加**

`tests/test_db_api.py` に追記（モデル未学習時の挙動確認のみ。学習済みモデルを要するテストは重いため行わない）:

```python
def test_predict_untrained_returns_error(client):
    res = client.post("/api/model/predict?normalize=true",
                      json=[{"jockey": "テスト", "horse": "テスト馬"}])
    assert res.status_code == 200
    assert res.json() == {"error": "モデル未学習"} or "error" in res.json()
```

**注意:** このテストはグローバル `_predictor` の状態に依存する。実機に `jra_model.pkl` が存在すると学習済みになるため、テスト冒頭で `backend.routers.model._predictor` を None に差し替える:

```python
def test_predict_untrained_returns_error(client, monkeypatch):
    import backend.routers.model as model_module
    monkeypatch.setattr(model_module, "_predictor", None)
    res = client.post("/api/model/predict?normalize=true",
                      json=[{"jockey": "テスト", "horse": "テスト馬"}])
    assert res.status_code == 200
    assert res.json() == {"error": "モデル未学習"}
```

（前者ではなくこの monkeypatch 版を採用する。）

Run: `venv\Scripts\python -m pytest tests -v`
Expected: 全件 PASS

- [ ] **Step 3: フロントエンドの client.ts を更新**

`predict` を normalize 対応にし、`win_pct_norm` を型に追加:

```ts
  predict: (entries: { jockey: string; horse: string }[], normalize = false) =>
    request<
      {
        jockey: string;
        jockey_name?: string;
        horse: string;
        horse_name?: string;
        win_pct: number;
        win_pct_norm?: number | null;
        top3_pct: number;
        status: string;
      }[]
    >(`/model/predict?normalize=${normalize}`, {
      method: "POST",
      body: JSON.stringify(entries),
    }),
```

- [ ] **Step 4: TodaysPrediction に正規化勝率列を追加**

`PredictResult` 型に `win_pct_norm?: number | null;` を追加。

`handlePredict` 内の呼び出しを `const pred = await modelApi.predict(input, true);` に変更。

テーブルヘッダーを変更:

```ts
                <tr>
                  <th>枠</th><th>馬番</th><th>馬名</th><th>性齢</th>
                  <th>斤量</th><th>騎手</th><th>調教師</th>
                  <th>状態</th><th>勝率 (%)</th><th>正規化勝率 (%)</th><th>3着内率 (%)</th>
                </tr>
```

行の `<td><strong>{r.win_pct}</strong></td>` の直後に追加:

```ts
                      <td><strong>{r.win_pct_norm ?? "—"}</strong></td>
```

- [ ] **Step 5: 型検証**

Run: `cd frontend && npx tsc --noEmit`
Expected: エラーなし

- [ ] **Step 6: コミット**

```bash
git add backend/routers/model.py frontend/src/api/client.ts frontend/src/pages/TodaysPrediction.tsx tests/test_db_api.py
git commit -m "feat: レース内で合計100%に正規化した勝率を追加"
```

---

### Task 8: フロントエンドのエラーハンドリング修正

**Files:**
- Modify: `frontend/src/pages/TodaysPrediction.tsx`
- Modify: `frontend/src/pages/Analysis.tsx`
- Modify: `frontend/src/pages/DatabaseManager.tsx`

**Interfaces:**
- Consumes: 既存 API のみ
- Produces: 変更なし（UI 挙動のみ）

- [ ] **Step 1: TodaysPrediction の catch 追加**

`handleGetRaces` の `try { ... } finally` に catch を挿入:

```ts
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
```

`handlePredict` も同様に、`finally` の前に挿入:

```ts
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPredicting(false);
    }
```

- [ ] **Step 2: Analysis の手動予測に catch とエラー表示を追加**

state を追加（`predResults` の下）:

```ts
  const [predMsg, setPredMsg] = useState("");
```

`handlePredict` を変更:

```ts
  const handlePredict = async () => {
    const valid = entries.filter((e) => e.jockey.trim() && e.horse.trim());
    if (!valid.length) return;
    setPredicting(true);
    setPredResults(null);
    setPredMsg("");
    try {
      const results = await modelApi.predict(valid);
      setPredResults(results);
    } catch (e: unknown) {
      setPredMsg(`error:${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setPredicting(false);
    }
  };
```

予測タブの描画（`{predResults && (` の直前）にエラー表示を追加:

```ts
              {predMsg && renderMsg(predMsg)}
```

- [ ] **Step 3: DatabaseManager のインポート結果チェック**

`handleImport` を変更:

```ts
  const handleImport = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`/api/db/${importTable}/import`, { method: "POST", body: form });
      const data = (await res.json().catch(() => ({}))) as { count?: number; detail?: string };
      if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
      setMsg(`success:${data.count} 件インポートしました。`);
      loadStats();
    } catch (e: unknown) {
      setMsg(`error:${e instanceof Error ? e.message : String(e)}`);
    }
  };
```

- [ ] **Step 4: 型検証**

Run: `cd frontend && npx tsc --noEmit`
Expected: エラーなし

- [ ] **Step 5: コミット**

```bash
git add frontend/src/pages/TodaysPrediction.tsx frontend/src/pages/Analysis.tsx frontend/src/pages/DatabaseManager.tsx
git commit -m "fix: fetch失敗時のエラー表示追加とインポート結果の検証"
```

---

### Task 9: start.bat の IP 不一致修正と README 更新

**Files:**
- Modify: `start.bat`
- Modify: `README.md`

**Interfaces:**
- Consumes: 全タスクの変更内容
- Produces: なし（ドキュメントのみ）

- [ ] **Step 1: start.bat の案内 IP を修正**

`echo  Open http://localhost:5151 or http://192.168.111.228:5151` の行を以下に変更（CORS 設定・README の固定 IP と一致させる）:

```bat
echo  Open http://localhost:5151 or http://192.168.111.10:5151
```

- [ ] **Step 2: README.md を更新**

(a) 「API エンドポイント」表の `POST /api/model/predict` 行を以下に変更:

```markdown
| POST | `/api/model/predict?normalize=true\|false` | 勝率予測（normalize=true でレース内合計100%に正規化） |
```

(b) 同表の `POST /api/model/train/start` 行の直後に注記を追加:

```markdown
> 学習実行中に再度 `/api/model/train/start` を呼ぶと **409** が返ります。
```

(c) 「使い方 → 2. モデル学習」セクションの末尾に追加:

```markdown
> **旧バージョンからの移行:** v0.2 以降、馬は馬名ではなく netkeiba の馬IDで学習します。
> 旧バージョンで学習した `jra_model.pkl` は予測時に馬が「不明」扱いになるため、**再学習してください**。
```

(d) 「必要条件」セクションの後に「テスト実行」セクションを追加:

````markdown
## テスト実行（開発者向け）

```bat
venv\Scripts\pip install -r requirements-dev.txt
venv\Scripts\python -m pytest tests -v
```
````

(e) 「ファイル構成」ツリーに追加（`backend/` ブロック内に `deps.py`、ルート直下に `tests/` と `requirements-dev.txt`）:

```
│   ├── deps.py              # DBセッション依存性 (Depends)
```

```
├── tests/                   # pytest テスト
├── requirements-dev.txt     # 開発用依存（pytest など）
```

- [ ] **Step 3: 全体検証**

Run: `venv\Scripts\python -m pytest tests -v`
Expected: 全件 PASS

Run: `cd frontend && npx tsc --noEmit`
Expected: エラーなし

- [ ] **Step 4: コミット**

```bash
git add start.bat README.md
git commit -m "docs: start.batのIP不一致修正とREADME更新"
```

---

## 実装後の手動確認チェックリスト

1. `start.bat` で起動 → ダッシュボードに DB 統計が表示される
2. 「分析・予測」→ 高速 (ADVI) で再学習 → 完了メッセージとランキング表示（馬名が表示されること）
3. 学習中にもう一度「モデル学習」を押す → 「既に学習を実行中です」エラーが表示される
4. 「今日のレース予測」→ 出馬表取得 → 騎手欄に**騎手名**（IDでなく）が表示され、「正規化勝率」列の合計が約 100% になる
5. DB 管理 → 不正な CSV をインポート → 「undefined 件」ではなくエラーメッセージが表示される
