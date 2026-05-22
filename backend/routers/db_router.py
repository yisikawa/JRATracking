import io
import pathlib

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from data.database import init_db, Race, Horse, Entry, Result, Base

ROOT = pathlib.Path(__file__).parent.parent.parent
DB_PATH = f"sqlite:///{ROOT / 'jra_data.db'}"

router = APIRouter()

MODEL_MAP = {"races": Race, "horses": Horse, "entries": Entry, "results": Result}


def _get_db():
    return init_db(DB_PATH)


@router.get("/stats")
def get_stats():
    session = _get_db()
    return {
        "races":   session.query(Race).count(),
        "horses":  session.query(Horse).count(),
        "entries": session.query(Entry).count(),
        "results": session.query(Result).count(),
    }


@router.get("/{table}")
def get_table(table: str, limit: int = 500):
    if table not in MODEL_MAP:
        raise HTTPException(404, f"テーブル '{table}' が見つかりません")
    session = _get_db()
    model = MODEL_MAP[table]
    query = session.query(model)
    if table == "races":
        query = query.order_by(model.date.desc())
    items = query.limit(limit).all()
    return [
        {c.name: getattr(item, c.name) for c in item.__table__.columns}
        for item in items
    ]


@router.delete("/race/{race_id}")
def delete_race(race_id: str):
    session = _get_db()
    race = session.query(Race).get(race_id)
    if not race:
        raise HTTPException(404, "レースが見つかりません")
    try:
        session.delete(race)
        session.commit()
        return {"success": True}
    except Exception as e:
        session.rollback()
        raise HTTPException(500, str(e))


@router.get("/{table}/export")
def export_csv(table: str):
    if table not in MODEL_MAP:
        raise HTTPException(404, f"テーブル '{table}' が見つかりません")
    session = _get_db()
    items = session.query(MODEL_MAP[table]).all()
    if not items:
        raise HTTPException(404, "データがありません")
    rows = [{c.name: getattr(i, c.name) for c in i.__table__.columns} for i in items]
    csv_bytes = pd.DataFrame(rows).to_csv(index=False).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{table}.csv"'},
    )


@router.post("/{table}/import")
async def import_csv(table: str, file: UploadFile = File(...)):
    if table not in MODEL_MAP:
        raise HTTPException(404, f"テーブル '{table}' が見つかりません")
    session = _get_db()
    model = MODEL_MAP[table]
    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
        if table == "races" and "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date
        count = 0
        for _, row in df.iterrows():
            row_dict = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
            session.merge(model(**row_dict))
            count += 1
        session.commit()
        return {"success": True, "count": count}
    except Exception as e:
        session.rollback()
        raise HTTPException(500, str(e))


@router.delete("/reset")
def reset_db():
    session = _get_db()
    try:
        engine = session.get_bind()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, str(e))
