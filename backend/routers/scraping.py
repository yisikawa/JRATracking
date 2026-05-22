import asyncio
import json
import pathlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from data.database import init_db, Race
from data.scraper import JRAScraper

ROOT = pathlib.Path(__file__).parent.parent.parent
DB_PATH = f"sqlite:///{ROOT / 'jra_data.db'}"

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=1)


def _get_db():
    return init_db(DB_PATH)


class RaceScrapeRequest(BaseModel):
    race_id: str


@router.get("/by-date")
def get_races_by_date(date: str):
    target = date.fromisoformat(date)
    session = _get_db()
    scraper = JRAScraper(session)
    race_ids = scraper.get_race_ids_by_date(target)
    return {"race_ids": race_ids}


@router.post("/race")
def scrape_race(req: RaceScrapeRequest):
    session = _get_db()
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
    async def generate():
        loop = asyncio.get_event_loop()
        session = _get_db()
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

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/upcoming")
def get_upcoming(date: str):
    target = date.fromisoformat(date) if date else date.today()
    session = _get_db()
    scraper = JRAScraper(session)
    race_ids = scraper.get_upcoming_race_ids(target)
    return {"race_ids": race_ids}


@router.get("/shutuba/{race_id}")
async def get_shutuba(race_id: str):
    loop = asyncio.get_event_loop()
    session = _get_db()
    scraper = JRAScraper(session)
    result = await loop.run_in_executor(_executor, scraper.scrape_shutuba, race_id)
    return result
