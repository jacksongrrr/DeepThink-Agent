import asyncio
from types import SimpleNamespace

import pytest

from deepthink_agent.streaming import _delta_parts, merge_async_dict_streams


def test_delta_parts_reasoning_and_content():
    d = SimpleNamespace(reasoning_content="思考", content="答")
    r, c = _delta_parts(d)
    assert r == "思考"
    assert c == "答"


def test_delta_parts_empty():
    d = SimpleNamespace()
    r, c = _delta_parts(d)
    assert r == ""
    assert c == ""


@pytest.mark.asyncio
async def test_merge_async_dict_streams_interleaves():
    async def a():
        yield {"id": "a", "n": 1}
        await asyncio.sleep(0)
        yield {"id": "a", "n": 2}

    async def b():
        yield {"id": "b", "n": 1}

    out = [x async for x in merge_async_dict_streams(a(), b())]
    assert len(out) == 3
    assert {e["id"] for e in out} == {"a", "b"}
