from deepthink_agent import prompts


def test_format_synthesis_traces_block():
    block = prompts.format_synthesis_traces_block(
        [
            {
                "path": "信息是否充足",
                "detail": "缺约束会导致方案漂。",
                "reasoning": "用户未给预算。",
                "answer": "先问预算。",
            },
        ]
    )
    assert "路径 1：信息是否充足" in block
    assert "路径展开（Chat）" in block
    assert "R1 推理过程" in block
    assert "先问预算" in block


def test_format_synthesis_traces_empty():
    assert prompts.format_synthesis_traces_block([]) == "（无）"
