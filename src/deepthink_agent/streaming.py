from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError

from deepthink_agent import prompts
from deepthink_agent.config import Settings
from deepthink_agent.services import DeepSeekPipelineError, generate_thinking_paths

logger = logging.getLogger(__name__)

StreamKind = Literal["reasoning", "answer"]


def _delta_parts(delta: Any) -> tuple[str, str]:
    """从流式 chunk 的 delta 中取 reasoning_content 与 content。"""
    r = getattr(delta, "reasoning_content", None) or ""
    c = getattr(delta, "content", None) or ""
    if hasattr(delta, "model_dump"):
        d = delta.model_dump(exclude_none=True)
        if "reasoning_content" in d and d["reasoning_content"] is not None:
            r = d["reasoning_content"]
        if "content" in d and d["content"] is not None:
            c = d["content"]
    if not isinstance(r, str):
        r = str(r) if r is not None else ""
    if not isinstance(c, str):
        c = str(c) if c is not None else ""
    return r, c


async def iter_reasoner_stream_chunks(
    client: AsyncOpenAI,
    settings: Settings,
    *,
    system_prompt: str,
    user_prompt: str,
) -> AsyncIterator[tuple[StreamKind, str]]:
    try:
        stream = await client.chat.completions.create(
            model=settings.model_reasoner,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
        )
    except (APIError, APIConnectionError, RateLimitError) as e:
        logger.exception("Reasoner 流式 API 调用失败")
        raise DeepSeekPipelineError(f"R1 流式推理失败：{e}") from e

    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta is None:
            continue
        r_part, c_part = _delta_parts(delta)
        if r_part:
            yield ("reasoning", r_part)
        if c_part:
            yield ("answer", c_part)


async def iter_chat_stream_text(
    client: AsyncOpenAI,
    settings: Settings,
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.45,
) -> AsyncIterator[str]:
    try:
        stream = await client.chat.completions.create(
            model=settings.model_chat,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
            temperature=temperature,
        )
    except (APIError, APIConnectionError, RateLimitError) as e:
        logger.exception("Chat 流式 API 调用失败")
        raise DeepSeekPipelineError(f"综合回答流式失败：{e}") from e

    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta is None:
            continue
        part = getattr(delta, "content", None) or ""
        if hasattr(delta, "model_dump"):
            d = delta.model_dump(exclude_none=True)
            if "content" in d and d["content"] is not None:
                part = d["content"]
        if not isinstance(part, str):
            part = str(part) if part is not None else ""
        if part:
            yield part


async def merge_async_dict_streams(
    *streams: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """合并多条事件流；各流之间顺序不确定（并行交错输出）。"""
    q: asyncio.Queue[tuple[int, dict[str, Any] | None]] = asyncio.Queue()

    async def pump(idx: int, it: AsyncIterator[dict[str, Any]]) -> None:
        try:
            async for ev in it:
                await q.put((idx, ev))
        except Exception as e:
            logger.exception("合并流中的子迭代器异常")
            await q.put((idx, {"type": "error", "message": str(e)}))
        finally:
            await q.put((idx, None))

    n = len(streams)
    tasks = [asyncio.create_task(pump(i, s)) for i, s in enumerate(streams)]
    finished = 0
    try:
        while finished < n:
            _idx, ev = await q.get()
            if ev is None:
                finished += 1
            else:
                yield ev
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _stream_parallel_paths_then_synthesis(
    client: AsyncOpenAI,
    settings: Settings,
    q: str,
    paths: list[Any],
) -> AsyncIterator[dict[str, Any]]:
    """多条路径的 R1 **并行**流式输出（经队列交错），全部完成后综合 Chat 流式。"""
    out_q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    n = len(paths)
    results: dict[int, dict[str, str | None]] = {}

    async def worker(idx: int, p: Any) -> None:
        try:
            await out_q.put(
                {
                    "type": "path_round_start",
                    "branch": "tech",
                    "path_index": idx,
                    "path": p.path,
                    "detail": p.detail,
                }
            )
            user = prompts.REASONER_PER_PATH_USER_TEMPLATE.format(
                question=q,
                index=idx + 1,
                path=p.path,
                detail=p.detail,
            )
            reasoning_parts: list[str] = []
            answer_parts: list[str] = []
            async for kind, text in iter_reasoner_stream_chunks(
                client,
                settings,
                system_prompt=prompts.REASONER_PER_PATH_SYSTEM,
                user_prompt=user,
            ):
                if kind == "reasoning":
                    reasoning_parts.append(text)
                    await out_q.put(
                        {
                            "type": "reasoning_delta",
                            "branch": "tech",
                            "path_index": idx,
                            "text": text,
                        }
                    )
                else:
                    answer_parts.append(text)
                    await out_q.put(
                        {
                            "type": "path_answer_delta",
                            "branch": "tech",
                            "path_index": idx,
                            "text": text,
                        }
                    )
            rs = "".join(reasoning_parts).strip() or None
            ans = "".join(answer_parts).strip()
            if not ans:
                raise DeepSeekPipelineError(f"路径「{p.path}」的 R1 未返回可见回答")
            results[idx] = {
                "path": p.path,
                "detail": p.detail,
                "reasoning": rs,
                "answer": ans,
            }
        except Exception as e:
            logger.exception("并行路径 R1 失败")
            await out_q.put({"type": "error", "message": str(e)})
        finally:
            await out_q.put({"type": "path_round_end", "branch": "tech", "path_index": idx})

    tasks = [asyncio.create_task(worker(i, p)) for i, p in enumerate(paths)]
    done_rounds = 0
    try:
        while done_rounds < n:
            ev = await out_q.get()
            typ = ev.get("type")
            if typ == "path_round_end":
                done_rounds += 1
            yield ev
    finally:
        await asyncio.gather(*tasks, return_exceptions=True)

    path_runs_data = [results[i] for i in range(n) if i in results]
    if len(path_runs_data) != n:
        raise DeepSeekPipelineError("部分路径 R1 未成功完成")

    traces_block = prompts.format_synthesis_traces_block(path_runs_data)
    syn_user = prompts.FINAL_SYNTHESIS_USER_TEMPLATE.format(
        question=q,
        traces_block=traces_block,
    )
    yield {"type": "synthesis_start", "branch": "tech"}
    async for text in iter_chat_stream_text(
        client,
        settings,
        system_prompt=prompts.FINAL_SYNTHESIS_SYSTEM,
        user_prompt=syn_user,
        temperature=0.45,
    ):
        yield {"type": "synthesis_delta", "branch": "tech", "text": text}
    yield {"type": "branch_end", "branch": "tech"}


async def _iter_baseline_compare_stream(
    client: AsyncOpenAI,
    settings: Settings,
    q: str,
) -> AsyncIterator[dict[str, Any]]:
    yield {"type": "phase", "branch": "baseline", "phase": "reasoning"}
    async for kind, text in iter_reasoner_stream_chunks(
        client,
        settings,
        system_prompt=prompts.REASONER_SYSTEM_BASELINE,
        user_prompt=prompts.REASONER_USER_BASELINE_TEMPLATE.format(question=q),
    ):
        if kind == "reasoning":
            yield {"type": "reasoning_delta", "branch": "baseline", "text": text}
        else:
            yield {"type": "answer_delta", "branch": "baseline", "text": text}
    yield {"type": "branch_end", "branch": "baseline"}


async def _iter_tech_from_paths_task(
    client: AsyncOpenAI,
    settings: Settings,
    q: str,
    paths_task: asyncio.Task,
) -> AsyncIterator[dict[str, Any]]:
    yield {"type": "phase", "branch": "tech", "phase": "paths_loading"}
    paths = await paths_task
    if not paths:
        yield {"type": "error", "message": "未生成任何有效思考路径"}
        return
    yield {
        "type": "paths",
        "branch": "tech",
        "paths": [{"path": p.path, "detail": p.detail} for p in paths],
    }
    yield {"type": "phase", "branch": "tech", "phase": "path_r1_series"}
    async for ev in _stream_parallel_paths_then_synthesis(client, settings, q, paths):
        yield ev


async def stream_events_baseline_only(
    client: AsyncOpenAI,
    settings: Settings,
    question: str,
) -> AsyncIterator[dict[str, Any]]:
    q = question.strip()
    yield {"type": "meta", "mode": "baseline_only"}
    yield {
        "type": "branch",
        "branch": "baseline",
        "title": "纯 R1（无思考路径预处理）",
    }
    async for kind, text in iter_reasoner_stream_chunks(
        client,
        settings,
        system_prompt=prompts.REASONER_SYSTEM_BASELINE,
        user_prompt=prompts.REASONER_USER_BASELINE_TEMPLATE.format(question=q),
    ):
        if kind == "reasoning":
            yield {"type": "reasoning_delta", "branch": "baseline", "text": text}
        else:
            yield {"type": "answer_delta", "branch": "baseline", "text": text}
    yield {"type": "branch_end", "branch": "baseline"}
    yield {"type": "done"}


async def stream_events_tech_only(
    client: AsyncOpenAI,
    settings: Settings,
    question: str,
) -> AsyncIterator[dict[str, Any]]:
    q = question.strip()
    yield {"type": "meta", "mode": "tech_only"}
    yield {
        "type": "branch",
        "branch": "tech",
        "title": "技术：多路径 × 并行 R1 + Chat 综合",
    }
    paths_task = asyncio.create_task(generate_thinking_paths(client, settings, q))
    async for ev in _iter_tech_from_paths_task(client, settings, q, paths_task):
        yield ev
    yield {"type": "done"}


async def stream_events_compare(
    client: AsyncOpenAI,
    settings: Settings,
    question: str,
) -> AsyncIterator[dict[str, Any]]:
    """左侧单次 R1 与右侧技术管线（路径生成 → 并行多 R1 → 综合）**同时**推进。"""
    q = question.strip()
    yield {"type": "meta", "mode": "compare"}
    yield {
        "type": "branch",
        "branch": "baseline",
        "title": "纯 R1（无思考路径预处理）",
    }
    yield {
        "type": "branch",
        "branch": "tech",
        "title": "技术：多路径 × 并行 R1 + Chat 综合",
    }
    paths_task = asyncio.create_task(generate_thinking_paths(client, settings, q))
    merged = merge_async_dict_streams(
        _iter_baseline_compare_stream(client, settings, q),
        _iter_tech_from_paths_task(client, settings, q, paths_task),
    )
    async for ev in merged:
        yield ev
    yield {"type": "done"}


async def iter_run_ndjson_lines(
    client: AsyncOpenAI,
    settings: Settings,
    *,
    question: str,
    mode: str,
) -> AsyncIterator[bytes]:
    """按行输出 NDJSON，便于 fetch 流式解析。"""

    async def gen_events() -> AsyncIterator[dict[str, Any]]:
        if mode == "compare":
            async for ev in stream_events_compare(client, settings, question):
                yield ev
        elif mode == "tech_only":
            async for ev in stream_events_tech_only(client, settings, question):
                yield ev
        else:
            async for ev in stream_events_baseline_only(client, settings, question):
                yield ev

    try:
        async for ev in gen_events():
            line = json.dumps(ev, ensure_ascii=False) + "\n"
            yield line.encode("utf-8")
    except DeepSeekPipelineError as e:
        err_line = json.dumps({"type": "error", "message": e.message}, ensure_ascii=False) + "\n"
        yield err_line.encode("utf-8")
