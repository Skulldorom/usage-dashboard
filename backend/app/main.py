from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router as api_router, start_auto_polling, stop_auto_polling
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_auto_polling()
    try:
        yield
    finally:
        await stop_auto_polling()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(api_router, prefix=settings.api_v1_prefix)
