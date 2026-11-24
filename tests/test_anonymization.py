"""匿名汇总、k-匿名抑制与历史保留依据测试。"""

import unittest

from pathway_tool.analysis import run_analysis

from fixtures import fixture_bundle


class AnonymizationTests(unittest.TestCase):
    def test_cells_below_k_are_suppressed(self):
        result = run_analysis(fixture_bundle(), k=3)
        for cell in result.anonymization_firm.cells:
            if cell.headcount < 3:
                self.assertEqual(cell.status, "suppressed")
            else:
                self.assertEqual(cell.status, "releasable")

    def test_retain_basis_when_group_still_meets_k_after_withdrawal(self):
        result = run_analysis(fixture_bundle(), k=1)
        # k=1 时所有单元格都满足匿名条件，撤回记录所在单元格仍判 retain
        withdrawn_cell = next(
            cell for cell in result.anonymization_firm.cells
            if cell.withdrawn_headcount > 0
        )
        self.assertEqual(withdrawn_cell.retention_decision, "retain")
        self.assertIn("撤回后", withdrawn_cell.basis)

    def test_historical_cell_kept_as_archive_but_not_republished(self):
        previous = {
            "event_id=E3|topic=晋商金融|series_version=S2|channel=web": 1,
        }
        result = run_analysis(
            fixture_bundle(), k=3, previous_anonymous_cells=previous
        )
        cell = next(
            cell for cell in result.anonymization_firm.cells
            if cell.dimensions["event_id"] == "E3"
        )
        self.assertEqual(cell.status, "suppressed")
        self.assertEqual(cell.retention_decision, "retain_historical_only")
        self.assertIsNotNone(cell.previous_headcount)

    def test_no_history_under_k_is_removed(self):
        result = run_analysis(fixture_bundle(), k=3)
        small_cell = next(
            cell for cell in result.anonymization_firm.cells
            if cell.headcount < 3 and cell.previous_headcount is None
        )
        self.assertEqual(small_cell.retention_decision, "remove")

    def test_aggregate_cells_carry_no_person_identifiers(self):
        result = run_analysis(fixture_bundle(), k=1)
        for cell in result.anonymization_firm.cells:
            self.assertNotIn("person_id", cell.dimensions)
            self.assertNotIn("identity_token", cell.dimensions)


if __name__ == "__main__":
    unittest.main()
