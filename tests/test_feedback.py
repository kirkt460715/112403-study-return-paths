"""反馈测试：按人独立归属、家庭成员不互相继承、受同意约束。"""

import unittest
from datetime import date, datetime

from pathway_tool.analysis import run_analysis
from pathway_tool.loading import bundle_from_rows

from fixtures import EVENTS


def _bundle_with_feedback():
    return bundle_from_rows(
        events=EVENTS,
        registrations=[
            dict(registration_id="R1", event_id="E1", identity_token="I01",
                 household_token="H1", channel="community", status="attended", consent="yes"),
            dict(registration_id="R2", event_id="E1", identity_token="I02",
                 household_token="H1", channel="community", status="attended", consent="yes"),
            dict(registration_id="R3", event_id="E2", identity_token="I01",
                 household_token="H1", channel="friend", status="attended", consent="yes"),
            # I02 报名 E2 后取消：同意仍有效，但没有实际到场
            dict(registration_id="R5", event_id="E2", identity_token="I02",
                 household_token="H1", channel="friend", status="cancelled", consent="yes"),
            dict(registration_id="R4", event_id="E3", identity_token="I05",
                 household_token="H5", channel="web", status="attended", consent="withdrawn"),
        ],
        links=[],
        consent_events=[
            dict(consent_id="C1", identity_token="I05", event_id="E3",
                 status="withdrawn", effective_at=datetime(2026, 10, 1, 12, 0)),
        ],
        touches=[],
        feedback=[
            dict(feedback_id="F1", identity_token="I01", event_id="E1",
                 interested_topics=["拓印实践"], score=5, comment="想再來"),
            dict(feedback_id="F2", identity_token="I02", event_id="E1",
                 interested_topics=["晋商金融"], score=4, comment=""),
            dict(feedback_id="F3", identity_token="I05", event_id="E3",
                 interested_topics=["钱币分享"], score=5, comment=""),
        ],
    )


class FeedbackTests(unittest.TestCase):
    def test_feedback_attributed_to_each_person_not_household(self):
        result = run_analysis(_bundle_with_feedback())
        view = result.feedback_firm
        # I01 与 I02 同属 H1，但各自只带自己的反馈
        self.assertEqual(
            view.person_feedback["I01"][0]["interested_topics"], ["拓印实践"]
        )
        self.assertEqual(
            view.person_feedback["I02"][0]["interested_topics"], ["晋商金融"]
        )
        check = next(
            item for item in view.household_isolation_checks
            if item["household_token"] == "H1"
        )
        self.assertEqual(set(check["feedback_by_person"]), {"I01", "I02"})
        # 每人只统计自己的反馈条数，家庭成员不互相继承、不重复累计
        self.assertEqual(check["feedback_by_person"], {"I01": 1, "I02": 1})

    def test_withdrawn_feedback_excluded_from_individual_analysis(self):
        result = run_analysis(_bundle_with_feedback())
        excluded_ids = [item["feedback_id"] for item in result.feedback_firm.excluded]
        self.assertIn("F3", excluded_ids)
        # 撤回者的意向不出现在任何专题汇总中
        all_interests = [
            wanted
            for interests in result.feedback_firm.topic_interest.values()
            for wanted in interests
        ]
        self.assertNotIn("钱币分享", all_interests)

    def test_feedback_for_unattended_event_is_rejected(self):
        bundle = _bundle_with_feedback()
        # I02 对 E2 同意有效但报名取消、未实际到场，其 E2 反馈应被拒绝
        bundle.feedback.append(
            type(bundle.feedback[0])(
                feedback_id="F9", identity_token="I02", event_id="E2",
                interested_topics=["晋商金融"], score=3, comment="",
            )
        )
        result = run_analysis(bundle)
        excluded = next(
            item for item in result.feedback_firm.excluded
            if item["feedback_id"] == "F9"
        )
        self.assertIn("不在本人同意有效的到场记录中", excluded["reason"])


if __name__ == "__main__":
    unittest.main()
