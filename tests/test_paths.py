"""专题衔接路径测试，含教研关注的钱币分享→拓印/后续专题问题。"""

import unittest

from pathway_tool.analysis import run_analysis

from fixtures import fixture_bundle


class TopicPathTests(unittest.TestCase):
    def test_fixture_transitions_firm_view(self):
        result = run_analysis(fixture_bundle())
        transitions = result.firm.topic_paths.transitions
        # I01：E1 钱币分享 → E2 拓印实践 → E4 钱币分享
        self.assertEqual(
            transitions[("钱币分享", "拓印实践")]["person_ids"], ["I01"]
        )
        self.assertEqual(
            transitions[("拓印实践", "钱币分享")]["person_ids"], ["I01"]
        )

    def test_topic_followups_answer_research_question(self):
        result = run_analysis(fixture_bundle())
        followups = {
            item["next_topic"]: item
            for item in result.firm.topic_paths.topic_followups["钱币分享"]
        }
        # 参加过钱币分享的人，后续去了拓印实践（也再次参加了钱币分享）
        self.assertEqual(followups["拓印实践"]["persons"], 1)
        self.assertIn("I01", followups["拓印实践"]["person_ids"])

    def test_tentative_path_depends_on_withdrawable_judgement(self):
        result = run_analysis(fixture_bundle())
        # 存疑口径把 I02 并入 I01，相关人员被标记为依赖可撤回判断
        self.assertIn("I01", result.tentative.topic_paths.depends_on_tentative)
        # 确定口径下没有任何 tentative 依赖
        self.assertEqual(result.firm.topic_paths.depends_on_tentative, [])

    def test_repeat_headcount_syncs_with_identity_correction(self):
        result = run_analysis(fixture_bundle())
        # 确定口径 1 名复访者；存疑合并后 I02 的 E1 变成同人同场次重复，
        # 复访人数仍为 1，但首访人数从 2 降为 1——数字随身份更正同步变化
        self.assertEqual(result.firm.participation.headcount_repeat, 1)
        self.assertEqual(result.tentative.participation.headcount_first_visit, 1)
        self.assertEqual(result.firm.participation.headcount_first_visit, 2)


if __name__ == "__main__":
    unittest.main()
