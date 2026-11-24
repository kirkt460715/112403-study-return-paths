"""口径快照与差异对比。

每次运行都会固化一个"口径快照"，使得历史对外报告采用的口径可以被
重新解释，而不是在身份关联更正后被悄悄覆盖：

* 输入指纹：各表文件名 + 行数 + 内容 SHA-256；
* 参数：as_of、k、参与状态口径、关联采纳规则；
* 关键结果：两个身份口径下的首访/复访人数、衔接矩阵计数；
* 关联与同意证据清单。

``diff_snapshots`` 对比两份快照，输出关键人数与证据的变化，
报告中据此解释"同一指标为什么前后不一样"。
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from .models import Bundle


def fingerprint_bundle(bundle: Bundle) -> Dict[str, dict]:
    """对每张输入表计算行数与内容哈希（合成数据，无个人信息）。"""

    def digest(rows) -> dict:
        payload = json.dumps(
            [row.__dict__ if hasattr(row, "__dict__") else row for row in rows],
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        return {
            "rows": len(rows),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    return {
        "events": digest(bundle.events),
        "registrations": digest(bundle.registrations),
        "identity_links": digest(bundle.links),
        "consent_events": digest(bundle.consent_events),
        "touches": digest(bundle.touches),
        "feedback": digest(bundle.feedback),
    }


@dataclass
class CaliberSnapshot:
    caliber_id: str
    created_at: str
    as_of: str
    k: int
    status_policy: Dict[str, List[str]]
    link_policy: Dict[str, str]
    input_fingerprint: Dict[str, dict]
    key_results: Dict[str, dict]
    link_audit: List[dict] = field(default_factory=list)
    tentative_dependencies: List[dict] = field(default_factory=list)
    consent_summary: Dict[str, int] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "caliber_id": self.caliber_id,
            "created_at": self.created_at,
            "as_of": self.as_of,
            "k": self.k,
            "status_policy": self.status_policy,
            "link_policy": self.link_policy,
            "input_fingerprint": self.input_fingerprint,
            "key_results": self.key_results,
            "link_audit": self.link_audit,
            "tentative_dependencies": self.tentative_dependencies,
            "consent_summary": self.consent_summary,
            "note": self.note,
        }

    def write(self, path: Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_snapshot(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def diff_snapshots(previous: dict, current: dict) -> dict:
    """对比两份口径快照，输出参数、输入与关键结果的差异。"""

    changes = {
        "previous_caliber_id": previous.get("caliber_id"),
        "current_caliber_id": current.get("caliber_id"),
        "parameter_changes": [],
        "input_changes": [],
        "result_changes": [],
        "evidence_changes": [],
    }

    for param in ("as_of", "k"):
        if previous.get(param) != current.get(param):
            changes["parameter_changes"].append(
                {
                    "field": param,
                    "previous": previous.get(param),
                    "current": current.get(param),
                }
            )

    for table, current_fp in current.get("input_fingerprint", {}).items():
        previous_fp = previous.get("input_fingerprint", {}).get(table)
        if previous_fp != current_fp:
            changes["input_changes"].append(
                {
                    "table": table,
                    "previous": previous_fp,
                    "current": current_fp,
                }
            )

    for view in ("firm", "tentative"):
        prev_results = previous.get("key_results", {}).get(view, {})
        curr_results = current.get("key_results", {}).get(view, {})
        for metric in sorted(set(prev_results) | set(curr_results)):
            if prev_results.get(metric) != curr_results.get(metric):
                changes["result_changes"].append(
                    {
                        "view": view,
                        "metric": metric,
                        "previous": prev_results.get(metric),
                        "current": curr_results.get(metric),
                    }
                )

    prev_deps = {
        (d["left_token"], d["right_token"])
        for d in previous.get("tentative_dependencies", [])
    }
    curr_deps = {
        (d["left_token"], d["right_token"])
        for d in current.get("tentative_dependencies", [])
    }
    for added in sorted(curr_deps - prev_deps):
        changes["evidence_changes"].append(
            {"change": "dependency_added", "link": list(added)}
        )
    for removed in sorted(prev_deps - curr_deps):
        changes["evidence_changes"].append(
            {"change": "dependency_removed", "link": list(removed)}
        )

    changes["explanation"] = _explain(changes)
    return changes


def _explain(changes: dict) -> List[str]:
    lines = []
    if changes["input_changes"]:
        lines.append(
            "输入数据发生变化："
            + "、".join(item["table"] for item in changes["input_changes"])
        )
    if changes["evidence_changes"]:
        lines.append(
            "身份关联证据有更正，相关个人路径与复访人数已按新证据重算"
        )
    if changes["result_changes"] and not changes["input_changes"]:
        lines.append("参数或口径变化导致结果差异")
    if not lines:
        lines.append("两份快照在参数、输入与关键结果上无差异")
    return lines
