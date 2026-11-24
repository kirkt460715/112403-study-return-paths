"""同意解析与撤回后果测试。"""

import unittest
from datetime import date, datetime

from pathway_tool.analysis import run_analysis
from pathway_tool.consent import ConsentResolver
from pathway_tool.loading import bundle_from_rows

from fixtures import EVENTS, fixture_bundle


class ConsentResolutionTests(unittest.TestCase):
    def test_consent_event_overrides_registration_snapshot(self):
        bundle = fixture_bundle()
        resolver = ConsentResolver(bundle)
        # I04/E3：登记快照是 withdrawn，同意事件也是 withdrawn，结论一致
        decision = resolver.for_token_event("I04", "E3")
        self.assertEqual(decision.state, "withdrawn")
        self.assertEqual(decision.basis, "consent_event")

    def test_latest_consent_event_wins_and_global_used_as_fallback(self):
        bundle = bundle_from_rows(
            events=EVENTS,
            registrations=[
                dict(registration_id="R1", event_id="E1", identity_token="I01",
                     household_token="H1", channel="web", status="attended", consent="yes"),
            ],
            links=[],
            consent_events=[
                dict(consent_id="C1", identity_token="I01", event_id=None,
                     status="granted", effective_at=datetime(2026, 8, 1, 9, 0)),
                dict(consent_id="C2", identity_token="I01", event_id=None,
                     status="withdrawn", effective_at=datetime(2026, 9, 1, 9, 0)),
            ],
            touches=[],
        )
        resolver = ConsentResolver(bundle)
        decision = resolver.for_token_event("I01", "E1")
        self.assertEqual(decision.state, "withdrawn")

    def test_missing_evidence_is_unknown_not_granted(self):
        bundle = bundle_from_rows(
            events=EVENTS,
            registrations=[
                dict(registration_id="R1", event_id="E1", identity_token="I01",
                     household_token="H1", channel="web", status="attended", consent=""),
            ],
            links=[],
            consent_events=[],
            touches=[],
        )
        decision = ConsentResolver(bundle).for_token_event("I01", "E1")
        self.assertEqual(decision.state, "unknown")

    def test_withdrawn_attendance_excluded_from_individual_paths(self):
        result = run_analysis(fixture_bundle(), k=2)
        firm = result.firm.participation
        # I04/E3 撤回：不出现在任何可进入个人路径的时间线记录中
        for timeline in firm.timelines.values():
            for record in timeline:
                if record.event_id == "E3":
                    self.assertFalse(record.included_in_individual_path)
                    self.assertEqual(record.consent_state, "withdrawn")
        self.assertGreaterEqual(firm.withdrawn_attendance_count, 1)
        # I04 不在首访/复访人员中
        self.assertNotIn("I04", firm.first_visit)
        self.assertNotIn("I04", firm.repeat_person_ids)


if __name__ == "__main__":
    unittest.main()
