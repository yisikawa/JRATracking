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
from data.database import init_db, Entry, Result

ROOT = pathlib.Path(__file__).parent.parent.parent
DB_PATH = f"sqlite:///{ROOT / 'jra_data.db'}"
MODEL_PATH = ROOT / "jra_model.pkl"

router = APIRouter()

_predictor: JRAPredictor | None = None
_tasks: dict[str, dict] = {}


def load_predictor():
    global _predictor
    if MODEL_PATH.exists():
        with open(MODEL_PATH, "rb") as f:
            _predictor = pickle.load(f)
        print(f"[model] モデルをロードしました: {MODEL_PATH}")


def _save_predictor(p: JRAPredictor):
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(p, f)


def _get_db():
    return init_db(DB_PATH)


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
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "running", "done": False, "error": None}

    def train():
        global _predictor
        try:
            session = _get_db()
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

    summary = _predictor._build_summary()
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
    for i, name in id_to_horse.items():
        param = f"beta_h[{i}]"
        if param in summary.index:
            row = summary.loc[param]
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
def predict(entries: list[PredictEntry]):
    if _predictor is None:
        return {"error": "モデル未学習"}

    input_list = [{"jockey": e.jockey, "horse": e.horse} for e in entries]
    prob_win, prob_top3 = _predictor.predict(input_list)

    known_jockeys = set(_predictor.known_jockeys())
    known_horses = set(_predictor.known_horses())

    results = []
    for e, pw, pt in zip(entries, prob_win, prob_top3):
        j_ok = e.jockey in known_jockeys
        h_ok = e.horse in known_horses
        if j_ok and h_ok:
            status = "known"
        elif not j_ok and not h_ok:
            status = "both_unknown"
        elif not j_ok:
            status = "jockey_unknown"
        else:
            status = "horse_unknown"
        results.append({
            "jockey": e.jockey,
            "horse":  e.horse,
            "win_pct":  round(float(pw) * 100, 1),
            "top3_pct": round(float(pt) * 100, 1),
            "status": status,
        })

    results.sort(key=lambda x: x["win_pct"], reverse=True)
    return results
