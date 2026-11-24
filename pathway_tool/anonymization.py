"""匿名汇总与历史结果保留依据。

撤回同意的记录不能再用于**个人路径分析**，但已经不可识别到个人、
且满足 k-匿名的**总体结果**可以继续保留。本模块把这一判断显式化：

1. 汇总只按"活动 / 专题 / 渠道 / 系列轮次"这类总体维度计数，
   不输出任何 person_id 或可回溯到个人的组合。
2. 每个汇总单元格要求组内人数 >= ``k``（默认 3，可配置），
   不足则抑制（suppressed）。
3. 对"此前已对外报告"的历史单元格（通过 previous 快照提供），
   给出三选一的明确依据：

   * ``retain``：撤回后重新计数仍满足 k-匿名，历史口径可继续保留；
   * ``retain_historical_only``：当前已不满足 k-匿名，
     历史报告作为既定事实存档可留，但**不得在新报告中重新发布**；
   * ``remove``：无法证明匿名化条件（如组内可被反推到个人），
     应从后续发布中移除并记录原因。

参与匿名池的记录包含同意有效者与撤回者（撤回者仅以计数形式存在），
但 denied/unknown 不进入。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .consent import ConsentResolver
from .identity import IdentityResolution
from .models import Bundle, PARTICIPATION_STATUSES
from .participation import ParticipationView


@dataclass
class AggregateCell:
    dimensions: Dict[str, str]
    headcount: int
    granted_headcount: int
    withdrawn_headcount: int
    k: int
    status: str  # releasable / suppressed
    retention_decision: Optional[str] = None
    basis: str = ""
    previous_headcount: Optional[int] = None


@dataclass
class AnonymizationView:
    k: int
    cells: List[AggregateCell] = field(default_factory=list)
    withdrawn_records: List[dict] = field(default_factory=list)
    policy: Dict[str, str] = field(default_factory=dict)


def _attendance_records(
    bundle: Bundle,
    resolution: IdentityResolution,
    consent: ConsentResolver,
):
    """产出用于汇总的匿名参与记录（不含 person_id 输出到单元格）。"""

    records = []
    events_by_id = {event.event_id: event for event in bundle.events}
    for reg in bundle.registrations:
        if reg.status not in PARTICIPATION_STATUSES:
            continue
        decision = consent.for_registration(reg)
        if decision.state not in ("granted", "withdrawn"):
            continue
        event = events_by_id[reg.event_id]
        records.append(
            {
                "event_id": reg.event_id,
                "topic": event.topic,
                "series_version": event.series_version,
                "channel": reg.channel or "未填写",
                "consent_state": decision.state,
                "is_makeup": reg.status == "makeup",
            }
        )
    return records


def build_anonymization(
    bundle: Bundle,
    resolution: IdentityResolution,
    participation: ParticipationView,
    consent: ConsentResolver,
    k: int = 3,
    previous_cells: Optional[Dict[str, int]] = None,
) -> AnonymizationView:
    view = AnonymizationView(
        k=k,
        policy={
            "rule": "单元格按总体维度计数，不含个人标识；组内人数 < k 时抑制",
            "withdrawn_handling": "撤回记录退出个人路径，仅以计数进入匿名池",
            "retention_reference": "retain / retain_historical_only / remove",
        },
    )

    # 撤回记录清单（用于口径说明，本身不携带 person 级输出到汇总单元格）
    for person, timeline in participation.timelines.items():
        for record in timeline:
            if not record.included_in_individual_path and record.consent_state in (
                "withdrawn",
            ):
                view.withdrawn_records.append(
                    {
                        "event_id": record.event_id,
                        "topic": record.topic,
                        "channel": record.channel,
                        "consent_state": record.consent_state,
                        "consent_basis": record.consent_basis,
                        "note": "已退出个人路径分析；仅可在 k-匿名单元格中以计数出现",
                    }
                )

    records = _attendance_records(bundle, resolution, consent)
    grouped: Dict[tuple, dict] = {}
    for record in records:
        dims = (
            ("event_id", record["event_id"]),
            ("topic", record["topic"]),
            ("series_version", record["series_version"]),
            ("channel", record["channel"]),
        )
        bucket = grouped.setdefault(
            dims,
            {"headcount": 0, "granted": 0, "withdrawn": 0},
        )
        bucket["headcount"] += 1
        if record["consent_state"] == "granted":
            bucket["granted"] += 1
        else:
            bucket["withdrawn"] += 1

    previous_cells = previous_cells or {}
    for dims, counts in sorted(grouped.items()):
        dim_dict = dict(dims)
        cell_key = "|".join(f"{key}={value}" for key, value in dims)
        previous = previous_cells.get(cell_key)
        releasable = counts["headcount"] >= k
        cell = AggregateCell(
            dimensions=dim_dict,
            headcount=counts["headcount"],
            granted_headcount=counts["granted"],
            withdrawn_headcount=counts["withdrawn"],
            k=k,
            status="releasable" if releasable else "suppressed",
            previous_headcount=previous,
        )

        if releasable:
            cell.retention_decision = "retain"
            cell.basis = (
                f"撤回后组内仍有 {counts['headcount']} 人（>= k={k}），"
                "单元格不可识别到个人，历史与当前汇总均可保留"
            )
        elif previous is not None:
            cell.retention_decision = "retain_historical_only"
            cell.basis = (
                f"当前组内仅 {counts['headcount']} 人（< k={k}），"
                "新报告抑制该单元格；历史报告作为已发布的匿名事实可存档保留，"
                "但不得重新发布或与新数据拼接反推个人"
            )
        else:
            cell.retention_decision = "remove"
            cell.basis = (
                f"组内 {counts['headcount']} 人 < k={k} 且无历史发布依据，"
                "不满足匿名汇总条件，不予发布"
            )
        view.cells.append(cell)

    return view
