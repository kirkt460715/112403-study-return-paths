"""命令行入口：analyze（分析）、diff（口径对比）、audit（输入审计）。

用法示例：

    python3 run_pathway.py analyze --data data --out reports --k 3
    python3 run_pathway.py diff \\
        --previous reports/caliber_snapshot.json --current reports_new/caliber_snapshot.json
    python3 run_pathway.py audit --data data
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .caliber import diff_snapshots, load_snapshot
from .loading import InputError, load_bundle
from .analysis import run_analysis
from .identity import IdentityConflictError
from .reporting import render_markdown, to_dict, write_reports


def _cmd_analyze(args) -> int:
    try:
        bundle = load_bundle(Path(args.data))
        previous_cells = None
        if args.previous_anonymous:
            payload = json.loads(Path(args.previous_anonymous).read_text("utf-8"))
            previous_cells = payload.get("anonymous_cells")
        result = run_analysis(
            bundle,
            as_of=date.fromisoformat(args.as_of) if args.as_of else None,
            k=args.k,
            previous_anonymous_cells=previous_cells,
        )
    except (InputError, IdentityConflictError) as exc:
        print(f"分析中止：{exc}", file=sys.stderr)
        return 2

    if args.out:
        paths = write_reports(result, Path(args.out))
        for name, path in paths.items():
            print(f"{name}: {path}")
    else:
        if args.format == "markdown":
            print(render_markdown(result))
        else:
            print(json.dumps(to_dict(result), ensure_ascii=False, indent=2))
    return 0


def _cmd_diff(args) -> int:
    changes = diff_snapshots(
        load_snapshot(Path(args.previous)),
        load_snapshot(Path(args.current)),
    )
    print(json.dumps(changes, ensure_ascii=False, indent=2))
    return 0


def _cmd_audit(args) -> int:
    try:
        bundle = load_bundle(Path(args.data))
    except InputError as exc:
        print(f"输入审计失败：{exc}", file=sys.stderr)
        return 2
    # source_files 的键是文件名去后缀，需映射到 Bundle 字段名
    attr_by_table = {
        "events": "events",
        "registrations": "registrations",
        "identity_links": "links",
        "consent_events": "consent_events",
        "touches": "touches",
        "feedback": "feedback",
    }
    print("输入审计通过：")
    for name, filename in sorted(bundle.source_files.items()):
        table = getattr(bundle, attr_by_table[name])
        print(f"- {filename}: {len(table)} 行")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_pathway",
        description="参与路径分析工具（确定/存疑双口径，同意与匿名化内置）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="读取数据并产出参与路径报告")
    analyze.add_argument("--data", default="data", help="数据目录（含 manifest.json）")
    analyze.add_argument("--out", help="报告输出目录；不填则打印到标准输出")
    analyze.add_argument(
        "--format", choices=("json", "markdown"), default="json",
        help="标准输出格式（与 --out 互斥时生效）",
    )
    analyze.add_argument("--as-of", help="关联有效期评估日期 YYYY-MM-DD")
    analyze.add_argument("--k", type=int, default=3, help="k-匿名阈值，默认 3")
    analyze.add_argument(
        "--previous-anonymous",
        help="历史匿名单元格 JSON（键为维度串，值为历史人数），用于保留依据判断",
    )
    analyze.set_defaults(func=_cmd_analyze)

    diff = sub.add_parser("diff", help="对比两份口径快照并解释差异")
    diff.add_argument("--previous", required=True)
    diff.add_argument("--current", required=True)
    diff.set_defaults(func=_cmd_diff)

    audit = sub.add_parser("audit", help="只做输入契约审计")
    audit.add_argument("--data", default="data")
    audit.set_defaults(func=_cmd_audit)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
