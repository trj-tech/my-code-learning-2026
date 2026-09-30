"""FastAPI 应用入口：uvicorn app.main:app --reload"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.routes import router


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    settings_path = Path("./data/chroma")
    settings_path.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="研发团队自动化周报智能体",
    description="LangGraph ReAct Agent：自动拉取 Git/文档/任务数据，生成结构化团队周报",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router, prefix="/api/v1")
