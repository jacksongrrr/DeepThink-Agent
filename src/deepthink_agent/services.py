from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError

from deepthink_agent import prompts
from deepthink_agent.config import Settings
from deepthink_agent.models_api import (
    BranchResult,
    PathReasonerRun,
    ReasonerResult,
    RunResponse,
    ThinkingPathItem,
)

logger = logging.getLogger(__name__)


class DeepSeekPipelineError(Exception):
    """封装上游 API 或解析失败，供 HTTP 层映射。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _extract_reasoner_parts(message: Any) -> tuple[str | None, str]:
    """从 Chat Completions 消息中提取推理与最终回答（兼容 DeepSeek reasoner 字段）。"""
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning is None and hasattr(message, "model_dump"):
        reasoning = message.model_dump().get("reasoning_content")
    answer = (getattr(message, "content", None) or "").strip()
    if reasoning is not None:
        reasoning = str(reasoning).strip() or None
    return reasoning, answer


def _parse_paths_payload(raw: str) -> list[ThinkingPathItem]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise DeepSeekPipelineError(f"思考路径 JSON 解析失败：{e}") from e
    if not isinstance(data, dict):
        raise DeepSeekPipelineError("思考路径响应必须是 JSON 对象")
    items = data.get("paths")
    if items is None:
        raise DeepSeekPipelineError("思考路径 JSON 缺少 paths 字段")
    if not isinstance(items, list):
        raise DeepSeekPipelineError("paths 必须是数组")
    out: list[ThinkingPathItem] = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise DeepSeekPipelineError(f"paths[{i}] 必须是对象")
        path = it.get("path")
        detail = it.get("detail")
        if detail is None and isinstance(it.get("reason"), str):
            detail = it.get("reason")
        if not isinstance(path, str) or not isinstance(detail, str):
            raise DeepSeekPipelineError(f"paths[{i}] 的 path/detail 必须是字符串")
        p, d = path.strip(), detail.strip()
        if not p or not d:
            continue
        out.append(ThinkingPathItem(path=p, detail=d))
    return out


async def generate_thinking_paths(
    client: AsyncOpenAI,
    settings: Settings,
    question: str,
) -> list[ThinkingPathItem]:
    user = prompts.PATH_GENERATOR_USER_TEMPLATE.format(question=question.strip())
    try:
        completion = await client.chat.completions.create(
            model=settings.model_chat,
            messages=[
                {"role": "system", "content": prompts.PATH_GENERATOR_SYSTEM},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.35,
        )
    except (APIError, APIConnectionError, RateLimitError) as e:
        logger.exception("Chat API 调用失败")
        raise DeepSeekPipelineError(f"思考路径生成失败：{e}") from e

    raw = completion.choices[0].message.content or "{}"
    return _parse_paths_payload(raw)


async def run_reasoner(
    client: AsyncOpenAI,
    settings: Settings,
    *,
    system_prompt: str,
    user_prompt: str,
) -> ReasonerResult:
    try:
        completion = await client.chat.completions.create(
            model=settings.model_reasoner,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except (APIError, APIConnectionError, RateLimitError) as e:
        logger.exception("Reasoner API 调用失败")
        raise DeepSeekPipelineError(f"R1 推理失败：{e}") from e

    msg = completion.choices[0].message
    reasoning, answer = _extract_reasoner_parts(msg)
    if not answer:
        raise DeepSeekPipelineError("R1 返回空回答")
    return ReasonerResult(reasoning=reasoning, answer=answer)


async def run_reasoner_for_single_path(
    client: AsyncOpenAI,
    settings: Settings,
    *,
    question: str,
    index: int,
    item: ThinkingPathItem,
) -> ReasonerResult:
    user = prompts.REASONER_PER_PATH_USER_TEMPLATE.format(
        question=question.strip(),
        index=index,
        path=item.path,
        detail=item.detail,
    )
    return await run_reasoner(
        client,
        settings,
        system_prompt=prompts.REASONER_PER_PATH_SYSTEM,
        user_prompt=user,
    )


async def run_final_synthesis_chat(
    client: AsyncOpenAI,
    settings: Settings,
    *,
    question: str,
    path_runs: list[PathReasonerRun],
) -> ReasonerResult:
    traces = [
        {
            "path": r.path,
            "detail": r.detail,
            "reasoning": r.reasoning,
            "answer": r.answer,
        }
        for r in path_runs
    ]
    block = prompts.format_synthesis_traces_block(traces)
    user = prompts.FINAL_SYNTHESIS_USER_TEMPLATE.format(
        question=question.strip(), traces_block=block
    )
    try:
        completion = await client.chat.completions.create(
            model=settings.model_chat,
            messages=[
                {"role": "system", "content": prompts.FINAL_SYNTHESIS_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.45,
        )
    except (APIError, APIConnectionError, RateLimitError) as e:
        logger.exception("综合回答 Chat 调用失败")
        raise DeepSeekPipelineError(f"综合回答生成失败：{e}") from e
    content = (completion.choices[0].message.content or "").strip()
    if not content:
        raise DeepSeekPipelineError("综合回答为空")
    return ReasonerResult(reasoning=None, answer=content)


async def run_tech_pipeline(
    client: AsyncOpenAI,
    settings: Settings,
    question: str,
) -> tuple[list[ThinkingPathItem], list[PathReasonerRun], ReasonerResult]:
    """Chat 多路径 → 每路径 R1 **并行** → Chat 综合。"""
    q = question.strip()
    paths = await generate_thinking_paths(client, settings, q)
    if not paths:
        raise DeepSeekPipelineError("未生成任何有效思考路径")
    coros = [
        run_reasoner_for_single_path(client, settings, question=q, index=i + 1, item=item)
        for i, item in enumerate(paths)
    ]
    raw_results = await asyncio.gather(*coros)
    path_runs = [
        PathReasonerRun(
            path=item.path,
            detail=item.detail,
            reasoning=rr.reasoning,
            answer=rr.answer,
        )
        for item, rr in zip(paths, raw_results, strict=True)
    ]
    final = await run_final_synthesis_chat(client, settings, question=q, path_runs=path_runs)
    return paths, path_runs, final


async def run_compare(client: AsyncOpenAI, settings: Settings, question: str) -> RunResponse:
    q = question.strip()
    baseline_coro = run_reasoner(
        client,
        settings,
        system_prompt=prompts.REASONER_SYSTEM_BASELINE,
        user_prompt=prompts.REASONER_USER_BASELINE_TEMPLATE.format(question=q),
    )
    paths_coro = generate_thinking_paths(client, settings, q)
    baseline, paths = await asyncio.gather(baseline_coro, paths_coro)
    if not paths:
        raise DeepSeekPipelineError("对比模式：思考路径为空")
    coros = [
        run_reasoner_for_single_path(client, settings, question=q, index=i + 1, item=item)
        for i, item in enumerate(paths)
    ]
    raw_results = await asyncio.gather(*coros)
    path_runs = [
        PathReasonerRun(
            path=item.path,
            detail=item.detail,
            reasoning=rr.reasoning,
            answer=rr.answer,
        )
        for item, rr in zip(paths, raw_results, strict=True)
    ]
    final = await run_final_synthesis_chat(client, settings, question=q, path_runs=path_runs)
    return RunResponse(
        mode="compare",
        baseline=BranchResult(
            label="纯 R1（无思考路径预处理）", paths=None, path_runs=None, reasoner=baseline
        ),
        tech=BranchResult(
            label="技术：多路径 × 并行 R1 + Chat 综合",
            paths=paths,
            path_runs=path_runs,
            reasoner=final,
        ),
    )


async def run_tech_only(client: AsyncOpenAI, settings: Settings, question: str) -> RunResponse:
    paths, path_runs, final = await run_tech_pipeline(client, settings, question)
    return RunResponse(
        mode="tech_only",
        tech=BranchResult(
            label="技术：多路径 × 并行 R1 + Chat 综合",
            paths=paths,
            path_runs=path_runs,
            reasoner=final,
        ),
    )


async def run_baseline_only(client: AsyncOpenAI, settings: Settings, question: str) -> RunResponse:
    q = question.strip()
    baseline = await run_reasoner(
        client,
        settings,
        system_prompt=prompts.REASONER_SYSTEM_BASELINE,
        user_prompt=prompts.REASONER_USER_BASELINE_TEMPLATE.format(question=q),
    )
    return RunResponse(
        mode="baseline_only",
        baseline=BranchResult(
            label="纯 R1（无思考路径预处理）",
            paths=None,
            path_runs=None,
            reasoner=baseline,
        ),
    )
