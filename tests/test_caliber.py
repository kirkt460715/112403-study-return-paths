"""口径快照与差异对比测试。"""

import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from pathway_tool.analysis import run_analysis
from pathway_tool.caliber import diff_snapshots, load_snapshot
from pathway_tool.reporting import write_reports

from fixtures import fixture_bundle


class CaliberTests(unittest.TestCase):
    def test_snapshot_is_written_and_reloadable(self):
        result = run_analysis(fixture_bundle())
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_reports(result, Path(tmp))
            snapshot = load_snapshot(paths["caliber"])
            self.assertEqual(snapshot["caliber_id"], result.snapshot.caliber_id)
            self.assertIn("firm", snapshot["key_results"])
            # 输入指纹包含每张表的哈希
            self.assertIn("registrations", snapshot["input_fingerprint"])
            self.assertEqual(len(snapshot["input_fingerprint"]["registrations"]["sha256"]), 64)

    def test_diff_detects_identity_correction_and_result_change(self):
        before = run_analysis(fixture_bundle())
        # 身份更正：possible 关联升级为 confirmed 并审核通过
        bundle_after = fixture_bundle()
        bundle_after.links[1] = type(bundle_after.links[1])(
            left_token="I02", right_token="I1A", link_strength="confirmed",
            valid_from=date(2026, 9, 1), valid_to=None, review="approved",
        )
        after = run_analysis(bundle_after)
        changes = diff_snapshots(before.snapshot.to_dict(), after.snapshot.to_dict())
        # 输入与证据均变化，确定口径首访人数由 2 变为 1
        self.assertTrue(changes["input_changes"])
        metric_change = next(
            item for item in changes["result_changes"]
            if item["view"] == "firm" and item["metric"] == "first_visit_persons"
        )
        self.assertEqual((metric_change["previous"], metric_change["current"]), (2, 1))
        self.assertTrue(
            any(item["change"] == "dependency_removed" for item in changes["evidence_changes"])
        )

    def test_identical_inputs_produce_no_diff(self):
        snapshot = run_analysis(fixture_bundle()).snapshot.to_dict()
        changes = diff_snapshots(snapshot, dict(snapshot))
        self.assertEqual(changes["result_changes"], [])
        self.assertEqual(changes["input_changes"], [])


if __name__ == "__main__":
    unittest.main()
