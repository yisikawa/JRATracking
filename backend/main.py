import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import scraping, model, db_router

app = FastAPI(title="JRA Tracking API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scraping.router, prefix="/api/scrape", tags=["scraping"])
app.include_router(model.router,    prefix="/api/model",  tags=["model"])
app.include_router(db_router.router, prefix="/api/db",    tags=["database"])

# モデルを起動時にロード
@app.on_event("startup")
def startup():
    model.load_predictor()
