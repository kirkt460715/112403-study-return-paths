"""报告序列化：机器可读 JSON 与人工可读 Markdown。

JSON 保留完整证据链（每条关联审计、每条可撤回依赖、每个汇总单元格的
保留依据）；Markdown 面向工作人员，先给确定结论，再给存疑结论，
并显著标注哪些数字依赖可撤回判断。
"""

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Dict, List

from .analysis import AnalysisResult, ViewResult
from .anonymization import AnonymizationView
from .feedback import FeedbackView


def _plain(obj):
    if is_dataclass(obj):
        return {key: _plain(value) for key, value in asdict(obj).items()}
    if isinstance(obj, dict):
        return {
            (str(key) if isinstance(key, tuple) else key): _plain(value)
            for key, value in obj.items()
        }
    if isinstance(obj, (list, tuple, set)):
        return [_plain(item) for item in obj]
    return obj


def _view_payload(view: ViewResult) -> dict:
    participation = view.participation
    return {
        "evidence_level": view.evidence_level,
        "headcounts": {
            "first_visit_persons": participation.headcount_first_visit,
            "repeat_persons": participation.headcount_repeat,
            "eligible_attendance": participation.attendance_count,
            "withdrawn_attendance_excluded": participation.withdrawn_attendance_count,
        },
        "first_visit": {
            person: {
                "event_id": record.event_id,
                "date": record.date,
                "topic": record.topic,
                "channel": record.channel,
                "is_makeup": record.is_makeup,
            }
            for person, record in participation.first_visit.items()
        },
        "timelines": {
            person: [
                {
                    "event_id": item.event_id,
                    "date": item.date,
                    "topic": item.topic,
                    "series_version": item.series_version,
                    "channel": item.channel,
                    "is_makeup": item.is_makeup,
                    "consent_state": item.consent_state,
                    "included_in_individual_path": item.included_in_individual_path,
                }
                for item in timeline
            ]
            for person, timeline in sorted(participation.timelines.items())
        },
        "channels": {
            name: _plain(row) for name, row in sorted(view.channels.items())
        },
        "topic_paths": {
            "person_sequences": _plain(view.topic_paths.person_sequences),
            "transitions": _plain(view.topic_paths.transitions),
            "topic_followups": _plain(view.topic_paths.topic_followups),
            "depends_on_tentative": view.topic_paths.depends_on_tentative,
        },
        "anomalies": participation.anomalies,
        "cancellations": participation.cancellations,
    }


def _anon_payload(anon: AnonymizationView) -> dict:
    return {
        "k": anon.k,
        "policy": anon.policy,
        "withdrawn_records": anon.withdrawn_records,
        "cells": [
            {
                "dimensions": cell.dimensions,
                "headcount": cell.headcount,
                "granted_headcount": cell.granted_headcount,
                "withdrawn_headcount": cell.withdrawn_headcount,
                "status": cell.status,
                "retention_decision": cell.retention_decision,
                "basis": cell.basis,
                "previous_headcount": cell.previous_headcount,
            }
            for cell in anon.cells
        ],
    }


def _feedback_payload(feedback: FeedbackView) -> dict:
    return {
        "topic_interest": _plain(feedback.topic_interest),
        "person_feedback": _plain(feedback.person_feedback),
        "excluded": feedback.excluded,
        "household_isolation_checks": feedback.household_isolation_checks,
    }


def to_dict(result: AnalysisResult) -> dict:
    return {
        "generated_as_of": result.as_of.isoformat(),
        "caliber": result.snapshot.to_dict(),
        "identity": {
            "firm": {
                "person_count": len(result.firm_resolution.person_tokens),
                "persons": result.firm_resolution.person_tokens,
                "household_persons": result.firm_resolution.household_persons,
                "anonymous_participants": result.firm_resolution.anonymous_participants,
            },
            "tentative": {
                "person_count": len(result.tentative_resolution.person_tokens),
                "persons": result.tentative_resolution.person_tokens,
                "household_persons": result.tentative_resolution.household_persons,
                "anonymous_participants": result.tentative_resolution.anonymous_participants,
                "dependencies": result.tentative_resolution.tentative_dependencies,
            },
            "link_audit": [
                {
                    "left_token": audit.link.left_token,
                    "right_token": audit.link.right_token,
                    "link_strength": audit.link.link_strength,
                    "review": audit.link.review,
                    "valid_from": audit.link.valid_from.isoformat()
                    if audit.link.valid_from
                    else None,
                    "valid_to": audit.link.valid_to.isoformat()
                    if audit.link.valid_to
                    else None,
                    "active": audit.active,
                    "reason": audit.reason,
                }
                for audit in result.link_audit
            ],
        },
        "firm_view": _view_payload(result.firm),
        "tentative_view": _view_payload(result.tentative),
        "feedback": {
            "firm": _feedback_payload(result.feedback_firm),
            "tentative": _feedback_payload(result.feedback_tentative),
        },
        "anonymous_aggregation": {
            "firm": _anon_payload(result.anonymization_firm),
            "tentative": _anon_payload(result.anonymization_tentative),
        },
        "anomalies_aggregated": result.anomalies,
    }


def render_markdown(result: AnalysisResult) -> str:
    lines: List[str] = []
    lines.append("# 参与路径分析报告（合成演练数据）")
    lines.append("")
    lines.append(
        f"- 评估时点 as_of：{result.as_of.isoformat()}；k-匿名阈值 k={result.k}"
    )
    lines.append(f"- 口径编号：{result.snapshot.caliber_id}")
    lines.append(
        "- 证据标记：**确定**=仅依赖 confirmed/approved 有效关联；"
        "**存疑**=依赖 possible/待审核关联，可被人工更正撤回"
    )
    lines.append("")

    lines.append("## 1. 身份关联审计")
    for audit in result.link_audit:
        link = audit.link
        lines.append(
            f"- {link.left_token} ↔ {link.right_token}（{link.link_strength}/"
            f"{link.review}，有效期 "
            f"{link.valid_from or '…'} ~ {link.valid_to or '长期'}）："
            f"{'采纳' if audit.active else '不采纳'} — {audit.reason}"
        )
    lines.append("")

    section = 2
    for label, view_name in (("确定口径", "firm"), ("存疑口径", "tentative")):
        view = result.view(view_name)
        p = view.participation
        lines.append(f"## {section}. {label}：首访与复访")
        lines.append("")
        lines.append(f"- 首次参与人数：**{p.headcount_first_visit}**")
        lines.append(f"- 复访人数（用于活动安排）：**{p.headcount_repeat}**")
        lines.append(f"- 同意有效到场人次：{p.attendance_count}")
        lines.append(
            f"- 撤回同意、已退出个人路径的到场：{p.withdrawn_attendance_count}"
        )
        lines.append("")
        lines.append("| 人 | 首访场次 | 日期 | 专题 | 首访渠道 | 补录 |")
        lines.append("|---|---|---|---|---|---|")
        for person, record in sorted(p.first_visit.items()):
            lines.append(
                f"| {person} | {record.event_id} | {record.date} | "
                f"{record.topic} | {record.channel} | {'是' if record.is_makeup else '否'} |"
            )
        lines.append("")
        section += 1

        lines.append(f"### {label}：渠道实际参与效果")
        lines.append("")
        lines.append(
            "| 渠道 | 登记数 | 其中取消 | 实际到场人次 | 首访人数 | 复访人次 | 接触条数 | 接触人数 | 接触后到场人数 |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for name, row in sorted(view.channels.items()):
            lines.append(
                f"| {name} | {row.registrations} | {row.registrations_cancelled} | "
                f"{row.attended_person_events} | {row.first_time_persons} | "
                f"{row.repeat_person_events} | {row.touches} | "
                f"{row.touched_persons} | {row.touched_and_attended_persons} |"
            )
        lines.append("")

        lines.append(f"### {label}：专题衔接（去重人数）")
        lines.append("")
        lines.append("| 起始专题 | 后续专题 | 人数 | 人员 |")
        lines.append("|---|---|---|---|")
        for (from_topic, to_topic), entry in sorted(
            view.topic_paths.transitions.items()
        ):
            lines.append(
                f"| {from_topic} | {to_topic} | {entry['persons']} | "
                f"{', '.join(entry['person_ids'])} |"
            )
        if not view.topic_paths.transitions:
            lines.append("| （无衔接记录） | | | |")
        lines.append("")
        if view_name == "tentative" and view.topic_paths.depends_on_tentative:
            lines.append(
                "> 依赖可撤回关联判断的人员："
                + ", ".join(view.topic_paths.depends_on_tentative)
            )
            lines.append("")

    lines.append(f"## {section}. 反馈与家庭隔离")
    section += 1
    feedback = result.feedback_firm
    if not result.bundle.feedback:
        lines.append("- 当前输入未提供反馈表（可选输入）；提供后按人独立归属，家庭成员不互相继承。")
    else:
        for topic, interests in sorted(feedback.topic_interest.items()):
            lines.append(f"- {topic} 参与者的后续意向：")
            for wanted, bucket in sorted(interests.items()):
                lines.append(
                    f"  - {wanted}：{bucket['person_count']} 人"
                    f"（其中确定口径 {bucket['firm_person_count']} 人）"
                )
        for check in feedback.household_isolation_checks:
            lines.append(
                f"- 家庭 {check['household_token']} 反馈按人独立计数："
                f"{check['feedback_by_person']}"
            )
        if feedback.excluded:
            lines.append("- 已排除的反馈：")
            for item in feedback.excluded:
                lines.append(f"  - {item}")
    lines.append("")

    lines.append(f"## {section}. 匿名汇总与历史保留依据")
    section += 1
    anon = result.anonymization_firm
    lines.append(f"- k-匿名阈值 k={anon.k}；撤回记录仅以计数进入匿名池。")
    lines.append("")
    lines.append("| 维度 | 总人数 | 同意有效 | 撤回 | 发布状态 | 保留决定 | 依据 |")
    lines.append("|---|---|---|---|---|---|---|")
    for cell in anon.cells:
        dims = " / ".join(f"{key}={value}" for key, value in cell.dimensions.items())
        lines.append(
            f"| {dims} | {cell.headcount} | {cell.granted_headcount} | "
            f"{cell.withdrawn_headcount} | {cell.status} | "
            f"{cell.retention_decision} | {cell.basis} |"
        )
    lines.append("")

    lines.append(f"## {section}. 异常与调整清单")
    for view_name, label in (("firm", "确定口径"), ("tentative", "存疑口径")):
        view_anomalies = result.anomalies.get(view_name, [])
        cancellations = result.view(view_name).participation.cancellations
        if not view_anomalies and not cancellations:
            lines.append(f"- {label}：无")
            continue
        lines.append(f"- {label}：")
        for item in view_anomalies:
            lines.append(f"  - {item}")
        for cancellation in cancellations:
            lines.append(f"  - 取消登记：{cancellation}")
    lines.append("")
    return "\n".join(lines)


def write_reports(result: AnalysisResult, out_dir: Path) -> Dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    import json

    json_path = out_dir / "participation_report.json"
    md_path = out_dir / "participation_report.md"
    caliber_path = out_dir / "caliber_snapshot.json"
    json_path.write_text(
        json.dumps(to_dict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(result), encoding="utf-8")
    result.snapshot.write(caliber_path)
    return {"json": json_path, "markdown": md_path, "caliber": caliber_path}
