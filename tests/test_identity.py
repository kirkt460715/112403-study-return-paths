"""分层身份解析测试：确定/存疑/明确不同、有效期、家庭不合并。"""

import unittest
from datetime import date

from pathway_tool.identity import (
    ANON_PREFIX,
    IdentityConflictError,
    resolve_identities,
)

from fixtures import fixture_bundle


class IdentityResolutionTests(unittest.TestCase):
    def test_firm_view_only_uses_confirmed_approved_active_links(self):
        firm, tentative, audits = resolve_identities(
            fixture_bundle(), as_of=date(2026, 10, 17)
        )
        # I01 与 I1A 确定关联，合并为同一人
        self.assertEqual(firm.person_for("I01"), firm.person_for("I1A"))
        # possible 关联在确定口径中不合并
        self.assertNotEqual(firm.person_for("I02"), firm.person_for("I1A"))
        # 存疑口径中追加 possible 合并
        self.assertEqual(
            tentative.person_for("I02"), tentative.person_for("I1A")
        )

    def test_tentative_dependencies_are_listed_and_marked_withdrawable(self):
        _, tentative, _ = resolve_identities(
            fixture_bundle(), as_of=date(2026, 10, 17)
        )
        self.assertEqual(len(tentative.tentative_dependencies), 1)
        dependency = tentative.tentative_dependencies[0]
        self.assertEqual(dependency["type"], "possible_link")
        self.assertTrue(dependency["withdrawable"])
        self.assertEqual(dependency["review"], "pending")

    def test_distinct_link_blocks_merge_in_both_views(self):
        bundle = fixture_bundle()
        # 即便人为增加一条 confirmed 把 I03、I04 拉到一起，也必须报冲突
        bundle.links.append(
            type(bundle.links[0])(
                left_token="I03",
                right_token="I04",
                link_strength="confirmed",
                valid_from=date(2026, 9, 1),
                valid_to=None,
                review="approved",
            )
        )
        with self.assertRaises(IdentityConflictError):
            resolve_identities(bundle, as_of=date(2026, 10, 17))

    def test_expired_confirmed_link_is_not_applied(self):
        # as_of 晚于 valid_to：确定关联失效，I01 与 I1A 重新拆成两人
        firm, _, audits = resolve_identities(
            fixture_bundle(), as_of=date(2026, 11, 1)
        )
        self.assertNotEqual(firm.person_for("I01"), firm.person_for("I1A"))
        audit = next(item for item in audits if item.link.link_strength == "confirmed")
        self.assertFalse(audit.active)
        self.assertIn("expired", audit.reason)

    def test_rejected_link_never_applied(self):
        bundle = fixture_bundle()
        bundle.links[0] = type(bundle.links[0])(
            left_token="I01", right_token="I1A", link_strength="confirmed",
            valid_from=date(2026, 9, 1), valid_to=None, review="rejected",
        )
        firm, _, _ = resolve_identities(bundle, as_of=date(2026, 10, 17))
        self.assertNotEqual(firm.person_for("I01"), firm.person_for("I1A"))

    def test_household_members_are_never_merged(self):
        firm, _, _ = resolve_identities(
            fixture_bundle(), as_of=date(2026, 10, 17)
        )
        # H1 家庭有 I01、I02 两人，但 person 不同
        self.assertEqual(sorted(firm.household_persons["H1"]), ["I01", "I02"])
        self.assertNotEqual(firm.person_for("I01"), firm.person_for("I02"))

    def test_household_only_registration_gets_anonymous_non_merged_person(self):
        bundle = fixture_bundle(
            registrations=[
                dict(registration_id="R9", event_id="E1", identity_token="",
                     household_token="H9", channel="web", status="attended", consent="yes"),
            ]
        )
        firm, _, _ = resolve_identities(bundle, as_of=date(2026, 10, 17))
        self.assertEqual(len(firm.anonymous_participants), 1)
        anon = firm.anonymous_participants[0]
        self.assertTrue(anon["person_id"].startswith(ANON_PREFIX))
        self.assertEqual(anon["household_token"], "H9")
        # 匿名参与者独立成 person，不与任何 token 合并
        self.assertEqual(firm.person_for(anon["person_id"]), anon["person_id"])


if __name__ == "__main__":
    unittest.main()
