"""输入契约与加载校验测试。"""

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from pathway_tool.cli import main
from pathway_tool.loading import InputError, load_bundle

from fixtures import fixture_bundle


class LoadingValidationTests(unittest.TestCase):
    def test_unknown_registration_status_is_rejected(self):
        bundle = fixture_bundle()
        bundle.registrations[0] = dataclasses.replace(
            bundle.registrations[0], status="walk-in"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_csv_bundle(Path(tmp), bundle)
            with self.assertRaises(InputError):
                load_bundle(path)

    def test_unknown_link_strength_is_rejected(self):
        bundle = fixture_bundle()
        bundle.links[0] = dataclasses.replace(
            bundle.links[0], link_strength="maybe"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_csv_bundle(Path(tmp), bundle)
            with self.assertRaises(InputError):
                load_bundle(path)

    def test_column_mismatch_is_rejected(self):
        bundle = fixture_bundle()
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_csv_bundle(Path(tmp), bundle)
            (path / "events.csv").write_text("event_id,date,topic\n", encoding="utf-8")
            with self.assertRaises(InputError):
                load_bundle(path)

    def test_cli_analyze_and_diff_end_to_end(self):
        import contextlib
        import io

        bundle = fixture_bundle()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_csv_bundle(Path(tmp) / "data", bundle)
            out_a = Path(tmp) / "reports_a"
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(
                    ["analyze", "--data", str(data_dir),
                     "--out", str(out_a), "--k", "2"]
                )
            self.assertEqual(code, 0)
            self.assertTrue((out_a / "participation_report.json").exists())
            self.assertTrue((out_a / "participation_report.md").exists())
            # 再跑一轮（新数据轮次），对比口径
            out_b = Path(tmp) / "reports_b"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(["analyze", "--data", str(data_dir),
                          "--out", str(out_b), "--k", "2"]),
                    0,
                )
                self.assertEqual(
                    main([
                        "diff",
                        "--previous", str(out_a / "caliber_snapshot.json"),
                        "--current", str(out_b / "caliber_snapshot.json"),
                    ]),
                    0,
                )
                self.assertEqual(main(["audit", "--data", str(data_dir)]), 0)


def _write_csv_bundle(root: Path, bundle) -> Path:
    import csv

    root.mkdir(parents=True, exist_ok=True)
    manifest = {"tables": []}

    def write(name, columns, rows, key=None):
        with (root / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        table = {"file": name, "columns": columns}
        if key:
            table["key"] = key
        manifest["tables"].append(table)

    write("events.csv", ["event_id", "date", "topic", "series_version"],
          [{"event_id": e.event_id, "date": e.date.isoformat(),
            "topic": e.topic, "series_version": e.series_version} for e in bundle.events],
          key="event_id")
    write("registrations.csv",
          ["registration_id", "event_id", "identity_token", "household_token",
           "channel", "status", "consent"],
          [r.__dict__ for r in bundle.registrations], key="registration_id")
    write("identity_links.csv",
          ["left_token", "right_token", "link_strength", "valid_from", "valid_to", "review"],
          [{"left_token": l.left_token, "right_token": l.right_token,
            "link_strength": l.link_strength,
            "valid_from": l.valid_from.isoformat() if l.valid_from else "",
            "valid_to": l.valid_to.isoformat() if l.valid_to else "",
            "review": l.review} for l in bundle.links], key="left_token")
    write("consent_events.csv",
          ["consent_id", "identity_token", "event_id", "status", "effective_at"],
          [{"consent_id": c.consent_id, "identity_token": c.identity_token,
            "event_id": c.event_id or "", "status": c.status,
            "effective_at": c.effective_at.isoformat()} for c in bundle.consent_events],
          key="consent_id")
    # touches 允许同一身份对同场次有多条接触记录，因此不设唯一键
    write("touches.csv",
          ["identity_token", "event_id", "touch_type", "touch_date"],
          [{"identity_token": t.identity_token, "event_id": t.event_id,
            "touch_type": t.touch_type,
            "touch_date": t.touch_date.isoformat()} for t in bundle.touches])
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return root


if __name__ == "__main__":
    unittest.main()
