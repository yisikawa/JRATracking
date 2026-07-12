import pathlib
import sys
from contextlib import asynccontextmanager

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Windows環境ではコンソール出力が既定でcp932になり、スクレイピング先(netkeiba)由来の
# デコード不能な文字をprintした際にUnicodeEncodeErrorでリクエストごとクラッシュするため、
# 標準出力/エラー出力をUTF-8(エンコード不能な文字は置換)に固定する
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
