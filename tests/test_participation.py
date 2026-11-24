"""首访/复访、取消与补录测试。"""

import unittest
from datetime import date

from pathway_tool.analysis import run_analysis

from fixtures import EVENTS, fixture_bundle


def reg(registration_id, event_id, token, household, channel, status, consent="yes"):
    return dict(
        registration_id=registration_id, event_id=event_id,
        identity_token=token, household_token=household,
        channel=channel, status=status, consent=consent,
    )


class FirstRepeatVisitTests(unittest.TestCase):
    def test_fixture_first_and_repeat_headcounts(self):
        result = run_analysis(fixture_bundle())
        firm = result.firm.participation
        # 确定口径：I01（E1→E2→E4）、I02（E1）有同意有效到场
        self.assertEqual(firm.headcount_first_visit, 2)
        self.assertEqual(firm.headcount_repeat, 1)
        self.assertEqual(firm.first_visit["I01"].event_id, "E1")
        self.assertEqual(firm.first_visit["I02"].event_id, "E1")

    def test_cancelled_registration_does_not_count_as_participation(self):
        bundle = fixture_bundle(
            registrations=[
                reg("R1", "E1", "I01", "H1", "web", "cancelled"),
                reg("R2", "E2", "I01", "H1", "web", "attended"),
            ]
        )
        result = run_analysis(bundle)
        participation = result.firm.participation
        self.assertEqual(participation.headcount_first_visit, 1)
        # 首访应是实际到场的 E2，而不是被取消的 E1
        self.assertEqual(participation.first_visit["I01"].event_id, "E2")
        self.assertEqual(len(participation.cancellations), 1)

    def test_makeup_record_rewrites_first_visit_attribution(self):
        # E2 的补录日期早于原首访 E1 之前不可能；这里用更早场次 E1 补录、
        # 原登记首访在 E2，验证补录成为首访并保留 makeup 标记
        bundle = fixture_bundle(
            registrations=[
                reg("R1", "E2", "I01", "H1", "friend", "attended"),
                reg("R2", "E1", "I01", "H1", "community", "makeup"),
            ]
        )
        result = run_analysis(bundle)
        first = result.firm.participation.first_visit["I01"]
        self.assertEqual(first.event_id, "E1")
        self.assertTrue(first.is_makeup)
        # 补录后 E2 变为复访
        self.assertIn("I01", result.firm.participation.repeat_person_ids)

    def test_duplicate_person_event_deduped_and_flagged(self):
        bundle = fixture_bundle(
            registrations=[
                reg("R1", "E1", "I01", "H1", "web", "attended"),
                reg("R2", "E1", "I01", "H1", "web", "makeup"),
            ]
        )
        result = run_analysis(bundle)
        participation = result.firm.participation
        # 同人同场次只算一次到场
        self.assertEqual(participation.attendance_count, 1)
        anomaly_types = [item["type"] for item in participation.anomalies]
        self.assertIn("duplicate_person_event", anomaly_types)


if __name__ == "__main__":
    unittest.main()
