from types import SimpleNamespace

from product_kb.index import HybridIndex


class _ScrollRecorder:
    def __init__(self) -> None:
        self.scroll_filter = None

    def scroll(self, **kwargs):
        self.scroll_filter = kwargs["scroll_filter"]
        return [], None


class _PagedScroll:
    def __init__(self) -> None:
        self.calls = 0

    def collection_exists(self, _name):
        return True

    def scroll(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return [SimpleNamespace(id="a"), SimpleNamespace(id="b")], "next"
        return [SimpleNamespace(id="c")], None


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


def test_active_guard_rejects_archived_and_superseded_results() -> None:
    assert HybridIndex._is_active({"status": "active"})
    assert not HybridIndex._is_active({"status": "archived"})
    assert not HybridIndex._is_active({"status": "superseded"})
    assert not HybridIndex._is_active({})


def test_all_point_ids_reads_every_page() -> None:
    index = HybridIndex.__new__(HybridIndex)
    index.settings = SimpleNamespace(collection_name="test")
    index.client = _PagedScroll()

    assert index._all_point_ids() == ["a", "b", "c"]
