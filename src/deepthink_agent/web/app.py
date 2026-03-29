from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI

from deepthink_agent.config import Settings, get_settings
from deepthink_agent.deepseek_client import create_async_client
from deepthink_agent.models_api import ErrorResponse, RunRequest, RunResponse
from deepthink_agent.services import (
    DeepSeekPipelineError,
    run_baseline_only,
    run_compare,
    run_tech_only,
)
from deepthink_agent.streaming import iter_run_ndjson_lines

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
STATIC_DIR = ROOT_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    client = create_async_client(settings)
    app.state.settings = settings
    app.state.client = client
    yield
    await client.close()


app = FastAPI(
    title="DeepThink Agent",
    description="对比思考路径预处理 + DeepSeek R1 与纯 R1",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DeepSeekPipelineError)
async def pipeline_error_handler(_: Request, exc: DeepSeekPipelineError):
    return JSONResponse(
        status_code=502,
        content=ErrorResponse(detail=exc.message).model_dump(),
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/run", response_model=RunResponse)
async def run_pipeline(body: RunRequest, request: Request):
    client: AsyncOpenAI = request.app.state.client
    settings: Settings = request.app.state.settings
    try:
        if body.mode == "compare":
            return await run_compare(client, settings, body.question)
        if body.mode == "tech_only":
            return await run_tech_only(client, settings, body.question)
        return await run_baseline_only(client, settings, body.question)
    except Exception as e:
        logger.exception("未处理异常")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/run/stream")
async def run_pipeline_stream(body: RunRequest, request: Request):
    """NDJSON 流：每行一个 JSON 事件，便于前端逐段渲染思考与回答。"""
    client: AsyncOpenAI = request.app.state.client
    settings: Settings = request.app.state.settings

    async def byte_iter():
        try:
            async for chunk in iter_run_ndjson_lines(
                client,
                settings,
                question=body.question,
                mode=body.mode,
            ):
                yield chunk
        except Exception as e:
            logger.exception("流式管线异常")
            line = json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False) + "\n"
            yield line.encode("utf-8")

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        byte_iter(),
        media_type="application/x-ndjson; charset=utf-8",
        headers=headers,
    )


def _mount_static() -> None:
    if STATIC_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


_mount_static()


@app.get("/")
async def index_page():
    index = STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=500, detail="静态文件缺失：static/index.html")
    return FileResponse(index)
