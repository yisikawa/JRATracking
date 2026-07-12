import asyncio
import json
import pathlib
import pickle
import threading
import uuid

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from analysis.predictor import JRAPredictor
from backend.deps import DB_PATH
from data.database import get_session_factory, Entry, Horse, Result

ROOT = pathlib.Path(__file__).parent.parent.parent
MODEL_PATH = ROOT / "jra_model.pkl"

router = APIRouter()

_predictor: JRAPredictor | None = None
_tasks: dict[str, dict] = {}
_train_lock = threading.Lock()


def load_predictor():
    global _predictor
    if MODEL_PATH.exists():
        try:
            with open(MODEL_PATH, "rb") as f:
                _predictor = pickle.load(f)
        except Exception as e:
            # 破損したpickleでアプリ全体の起動を失敗させない
            # (未学習状態として起動を継続し、UIから再学習できるようにする)
            print(f"[model] モデルの読み込みに失敗しました({e})。未学習状態で起動します: {MODEL_PATH}")
            _predictor = None
            return
        # 旧バージョンのpickleに存在しない属性を補完
        for attr, default in [("horse_display_map", {}), ("horse_name_map", {}),
                              ("summary", None)]:
            if not hasattr(_predictor, attr):
                setattr(_predictor, attr, default)
        print(f"[model] モデルをロードしました: {MODEL_PATH}")


def _save_predictor(p: JRAPredictor):
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(p, f)


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
            "horse_id":    result_horse_id,
            "horse_name":  horse_name or result_horse_id,
        }
        for rank, jockey_id, jockey_name, result_horse_id, horse_name in rows
    ]
    return pd.DataFrame(data)


@router.get("/status")
def get_status():
    if _predictor is None:
        return {"trained": False}
    return {
        "trained": True,
        "mode": _predictor.fit_mode,
        "jockeys": len(_predictor.known_jockeys()),
        "horses": len(_predictor.known_horses()),
    }


@router.post("/train/start")
def start_training(mode: str = "advi"):
    if mode not in ("advi", "fast", "standard"):
        raise HTTPException(400, f"不正な学習モードです: {mode}")
    if not _train_lock.acquire(blocking=False):
        raise HTTPException(409, "既に学習を実行中です")
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "running", "done": False, "error": None}

    def train():
        global _predictor
        session = get_session_factory(DB_PATH)()
        try:
            df = _build_training_frame(session)
            if df.empty:
                _tasks[task_id].update({"done": True, "error": "学習データがありません"})
                return

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
            _train_lock.release()

    threading.Thread(target=train, daemon=True).start()
    return {"task_id": task_id}


@router.get("/train/stream/{task_id}")
async def training_stream(task_id: str):
    async def generate():
        while True:
            task = _tasks.get(task_id, {"done": True, "error": "タスクが見つかりません"})
            yield f"data: {json.dumps(task)}\n\n"
            if task.get("done"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/rankings")
def get_rankings():
    if _predictor is None:
        return {"error": "モデル未学習"}

    summary = _predictor.get_summary()
    is_advi = _predictor.fit_mode == "advi"

    id_to_jockey = {v: k for k, v in _predictor.jockey_map.items()
                    if k != _predictor.UNKNOWN}
    jockeys = []
    for i, key in id_to_jockey.items():
        param = f"beta_j[{i}]"
        if param in summary.index:
            row = summary.loc[param]
            name = _predictor.jockey_display_map.get(key, key)
            entry = {"name": name, "score": round(float(row["Mean"]), 3)}
            if not is_advi:
                entry.update({
                    "std": round(float(row["StdDev"]), 3),
                    "p5":  round(float(row["5%"]), 3),
                    "p95": round(float(row["95%"]), 3),
                })
            jockeys.append(entry)
    jockeys.sort(key=lambda x: x["score"], reverse=True)

    id_to_horse = {v: k for k, v in _predictor.horse_map.items()
                   if k != _predictor.UNKNOWN}
    horses = []
    for i, key in id_to_horse.items():
        param = f"beta_h[{i}]"
        if param in summary.index:
            row = summary.loc[param]
            name = _predictor.horse_display_map.get(key, key)
            entry = {"name": name, "score": round(float(row["Mean"]), 3)}
            if not is_advi:
                entry.update({
                    "std": round(float(row["StdDev"]), 3),
                    "p5":  round(float(row["5%"]), 3),
                    "p95": round(float(row["95%"]), 3),
                })
            horses.append(entry)
    horses.sort(key=lambda x: x["score"], reverse=True)

    return {"jockeys": jockeys, "horses": horses, "mode": _predictor.fit_mode}


class PredictEntry(BaseModel):
    jockey: str
    horse: str


@router.post("/predict")
def predict(entries: list[PredictEntry], normalize: bool = False):
    if _predictor is None:
        return {"error": "モデル未学習"}

    input_list = [{"jockey": e.jockey, "horse": e.horse} for e in entries]
    prob_win, prob_top3 = _predictor.predict(input_list)

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

    if normalize:
        total = sum(r["win_pct"] for r in results)
        for r in results:
            r["win_pct_norm"] = round(r["win_pct"] / total * 100, 1) if total > 0 else None

    results.sort(key=lambda x: x["win_pct"], reverse=True)
    return results
