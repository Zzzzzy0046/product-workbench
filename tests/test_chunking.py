from product_kb.chunking import chunk_markdown


def test_heading_locator_and_stable_ids() -> None:
    text = "# 产品定义\n\n总述。\n\n## MVP\n\n只做核心任务。"
    first = chunk_markdown("source-1", text, "测试文档", {"status": "active"})
    second = chunk_markdown("source-1", text, "测试文档", {"status": "active"})

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert first[0].locator == "产品定义"
    assert first[1].locator == "产品定义 > MVP"
    assert "测试文档" in first[1].text


def test_long_sections_are_split() -> None:
    text = "# 长文\n\n" + ("这是一个用于切块的句子。" * 400)
    chunks = chunk_markdown("source-2", text, "长文测试", {"status": "active"})
    assert len(chunks) > 1
    assert all(chunk.text for chunk in chunks)
