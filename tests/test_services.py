import json

import pytest

from deepthink_agent.services import (
    DeepSeekPipelineError,
    _parse_classification_payload,
    _parse_paths_payload,
)


def test_parse_paths_payload_detail_ok():
    raw = json.dumps(
        {
            "paths": [
                {"path": " 维度A ", "detail": " 展开说明一。第二句。"},
                {"path": "", "detail": "x"},
            ]
        },
        ensure_ascii=False,
    )
    items = _parse_paths_payload(raw)
    assert len(items) == 1
    assert items[0].path == "维度A"
    assert "展开说明一" in items[0].detail


def test_parse_paths_payload_reason_fallback():
    raw = json.dumps(
        {"paths": [{"path": "仅旧字段", "reason": "当作 detail 用"}]},
        ensure_ascii=False,
    )
    items = _parse_paths_payload(raw)
    assert len(items) == 1
    assert items[0].detail == "当作 detail 用"


def test_parse_paths_payload_invalid():
    with pytest.raises(DeepSeekPipelineError):
        _parse_paths_payload("not json")


def test_parse_classification_payload_ok():
    raw = json.dumps(
        {
            "domain_type": "决策",
            "difficulty": "中",
            "subcategory": "资源约束",
            "structure_type": "开放",
            "thinking_stance": "先列假设再验证",
        },
        ensure_ascii=False,
    )
    d = _parse_classification_payload(raw)
    assert d["difficulty"] == "中"
    assert "thinking_stance" in d
