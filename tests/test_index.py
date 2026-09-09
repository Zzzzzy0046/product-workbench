from types import SimpleNamespace

from product_kb.index import HybridIndex


class _ScrollRecorder:
    def __init__(self) -> None:
        self.scroll_filter = None

    def scroll(self, **kwargs):
        self.scroll_filter = kwargs["scroll_filter"]
        return [], None


def test_curated_points_keep_requested_type_filter() -> None:
    index = HybridIndex.__new__(HybridIndex)
    index.settings = SimpleNamespace(collection_name="test")
    index.client = _ScrollRecorder()

    index._curated_points({"type": "case"})

    conditions = index.client.scroll_filter.must
    type_conditions = [condition for condition in conditions if condition.key == "type"]
    assert len(type_conditions) == 1
    assert type_conditions[0].match.any == ["case"]


def test_payload_filter_rejects_non_case_results() -> None:
    assert HybridIndex._payload_matches_filters({"type": "case"}, {"type": "case"})
    assert not HybridIndex._payload_matches_filters(
        {"type": "source"}, {"type": "case"}
    )
    assert HybridIndex._payload_matches_filters(
        {"platform": ["android", "ios"]}, {"platform": "android"}
    )
