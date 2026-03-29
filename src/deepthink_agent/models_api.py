from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=8000)
    mode: Literal["compare", "tech_only", "baseline_only"] = "compare"


class ThinkingPathItem(BaseModel):
    """Chat 生成的单条路径：短标题 + 详细阐明。"""

    path: str
    detail: str


class ReasonerResult(BaseModel):
    reasoning: str | None = None
    answer: str


class PathReasonerRun(BaseModel):
    """每条思考路径对应的一次 R1 调用结果。"""

    path: str
    detail: str
    reasoning: str | None = None
    answer: str


class BranchResult(BaseModel):
    label: str
    paths: list[ThinkingPathItem] | None = None
    path_runs: list[PathReasonerRun] | None = None
    reasoner: ReasonerResult


class RunResponse(BaseModel):
    mode: str
    baseline: BranchResult | None = None
    tech: BranchResult | None = None


class ErrorResponse(BaseModel):
    detail: str
