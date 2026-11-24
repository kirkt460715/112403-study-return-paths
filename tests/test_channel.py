"""渠道实际参与效果与接触转化测试。"""

import unittest

from pathway_tool.analysis import run_analysis

from fixtures import fixture_bundle


class ChannelTests(unittest.TestCase):
    def test_channel_metrics_measure_attendance_not_clicks(self):
        result = run_analysis(fixture_bundle())
        channels = result.firm.channels
        # school 渠道：1 条登记但已取消，实际到场为 0
        self.assertEqual(channels["school"].registrations, 1)
        self.assertEqual(channels["school"].registrations_cancelled, 1)
        self.assertEqual(channels["school"].attended_person_events, 0)
        # community 渠道带来确定口径下 2 名首访者
        self.assertEqual(channels["community"].first_time_persons, 2)

    def test_touch_conversion_counts_only_actual_attenders(self):
        result = run_analysis(fixture_bundle())
        channels = result.firm.channels
        # I03 收到 school_notice 但取消报名：接触 1 人，转化 0 人
        self.assertEqual(channels["school_notice"].touched_persons, 1)
        self.assertEqual(channels["school_notice"].touched_and_attended_persons, 0)
        # I01 收到 flyer 且 E1 实际到场：转化 1 人
        self.assertEqual(channels["flyer"].touched_and_attended_persons, 1)

    def test_withdrawn_touch_does_not_count_as_conversion(self):
        result = run_analysis(fixture_bundle())
        channels = result.firm.channels
        # I04 通过 web_page 接触 E3，但同意撤回：不计接触后到场
        self.assertEqual(channels["web_page"].touched_persons, 1)
        self.assertEqual(channels["web_page"].touched_and_attended_persons, 0)


if __name__ == "__main__":
    unittest.main()
