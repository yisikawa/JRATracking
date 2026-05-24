import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import scraping, model, db_router

app = FastAPI(title="JRA Tracking API")

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

# モデルを起動時にロード
@app.on_event("startup")
def startup():
    model.load_predictor()
