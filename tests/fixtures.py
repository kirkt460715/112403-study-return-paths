"""测试辅助：构造可复用的合成内存数据。"""

from datetime import date, datetime

from pathway_tool.loading import bundle_from_rows

EVENTS = [
    {"event_id": "E1", "date": date(2026, 9, 2), "topic": "钱币分享", "series_version": "S1"},
    {"event_id": "E2", "date": date(2026, 9, 16), "topic": "拓印实践", "series_version": "S1"},
    {"event_id": "E3", "date": date(2026, 10, 3), "topic": "晋商金融", "series_version": "S2"},
    {"event_id": "E4", "date": date(2026, 10, 17), "topic": "钱币分享", "series_version": "S2"},
]


def fixture_bundle(**overrides):
    rows = dict(
        events=EVENTS,
        registrations=[
            dict(registration_id="R1", event_id="E1", identity_token="I01",
                 household_token="H1", channel="community", status="attended", consent="yes"),
            dict(registration_id="R2", event_id="E1", identity_token="I02",
                 household_token="H1", channel="community", status="attended", consent="yes"),
            dict(registration_id="R3", event_id="E2", identity_token="I01",
                 household_token="H1", channel="friend", status="attended", consent="yes"),
            dict(registration_id="R4", event_id="E2", identity_token="I03",
                 household_token="H2", channel="school", status="cancelled", consent="yes"),
            dict(registration_id="R5", event_id="E3", identity_token="I04",
                 household_token="H3", channel="web", status="attended", consent="withdrawn"),
            dict(registration_id="R6", event_id="E4", identity_token="I1A",
                 household_token="H1", channel="community", status="attended", consent="yes"),
        ],
        links=[
            dict(left_token="I01", right_token="I1A", link_strength="confirmed",
                 valid_from=date(2026, 9, 1), valid_to=date(2026, 10, 31), review="approved"),
            dict(left_token="I02", right_token="I1A", link_strength="possible",
                 valid_from=date(2026, 9, 1), valid_to=None, review="pending"),
            dict(left_token="I03", right_token="I04", link_strength="distinct",
                 valid_from=date(2026, 9, 1), valid_to=None, review="approved"),
        ],
        consent_events=[
            dict(consent_id="C1", identity_token="I01", event_id="E1",
                 status="granted", effective_at=datetime(2026, 8, 1, 9, 0)),
            dict(consent_id="C2", identity_token="I01", event_id="E3",
                 status="withdrawn", effective_at=datetime(2026, 10, 1, 12, 0)),
            dict(consent_id="C3", identity_token="I02", event_id="E1",
                 status="granted", effective_at=datetime(2026, 8, 4, 9, 0)),
            dict(consent_id="C4", identity_token="I04", event_id="E3",
                 status="withdrawn", effective_at=datetime(2026, 10, 2, 12, 0)),
        ],
        touches=[
            dict(identity_token="I01", event_id="E1", touch_type="flyer",
                 touch_date=date(2026, 8, 20)),
            dict(identity_token="I01", event_id="E1", touch_type="community_post",
                 touch_date=date(2026, 8, 25)),
            dict(identity_token="I03", event_id="E2", touch_type="school_notice",
                 touch_date=date(2026, 9, 1)),
            dict(identity_token="I04", event_id="E3", touch_type="web_page",
                 touch_date=date(2026, 9, 20)),
        ],
        feedback=[],
    )
    rows.update(overrides)
    return bundle_from_rows(**rows)
