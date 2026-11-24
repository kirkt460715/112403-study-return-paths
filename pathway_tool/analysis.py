"""一次完整分析的编排。

流程固定，便于按新一轮报名/到场反复运行：

1. 身份解析（确定 + 存疑两个口径，产出关联审计）；
2. 同意状态解析；
3. 两个口径各自的参与、渠道、专题路径分析；
4. 反馈分析（可选输入）；
5. 匿名汇总与历史保留依据；
6. 固化口径快照。

所有结论都带 ``evidence_level``：``firm`` 来自确定身份，
``tentative`` 依赖可撤回的关联判断。
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional

from .anonymization import AnonymizationView, build_anonymization
from .caliber import CaliberSnapshot, fingerprint_bundle
from .channel import ChannelRow, build_channel_view
from .consent import ConsentResolver
from .feedback import FeedbackView, build_feedback_view
from .identity import IdentityResolution, resolve_identities
from .models import (
    CANCEL_STATUSES,
    KNOWN_REG_STATUSES,
    PARTICIPATION_STATUSES,
    Bundle,
)
from .participation import ParticipationView, build_participation
from .paths import TopicPathView, build_topic_paths

LINK_POLICY = {
    "firm": "仅采纳 valid_from/valid_to 有效期内且 review=approved 的 confirmed 关联",
    "tentative": "在 firm 基础上追加 possible 关联（含 pending），逐条列为可撤回依赖",
    "distinct": "任何口径下的硬约束，违反即报 IdentityConflictError",
    "household": "household_token 仅用于家庭分组与匿名编号，不用于合并人",
}


@dataclass
class ViewResult:
    participation: ParticipationView
    channels: Dict[str, ChannelRow]
    topic_paths: TopicPathView
    evidence_level: str


@dataclass
class AnalysisResult:
    bundle: Bundle
    as_of: date
    k: int
    firm_resolution: IdentityResolution
    tentative_resolution: IdentityResolution
    link_audit: list
    firm: ViewResult
    tentative: ViewResult
    feedback_firm: FeedbackView
    feedback_tentative: FeedbackView
    anonymization_firm: AnonymizationView
    anonymization_tentative: AnonymizationView
    snapshot: CaliberSnapshot
    anomalies: Dict[str, List[dict]] = field(default_factory=dict)

    def view(self, name: str) -> ViewResult:
        return self.firm if name == "firm" else self.tentative


def _build_view_result(
    bundle: Bundle,
    resolution: IdentityResolution,
    consent: ConsentResolver,
    evidence_level: str,
) -> ViewResult:
    participation = build_participation(bundle, resolution, consent)
    channels = build_channel_view(bundle, resolution, participation)
    topic_paths = build_topic_paths(resolution, participation)
    return ViewResult(
        participation=participation,
        channels=channels,
        topic_paths=topic_paths,
        evidence_level=evidence_level,
    )


def _consent_summary(bundle: Bundle, consent: ConsentResolver) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for reg in bundle.registrations:
        state = consent.for_registration(reg).state
        counts[state] = counts.get(state, 0) + 1
    return dict(sorted(counts.items()))


def _key_results(firm: ViewResult, tentative: ViewResult) -> Dict[str, dict]:
    def pack(view: ViewResult) -> dict:
        return {
            "first_visit_persons": view.participation.headcount_first_visit,
            "repeat_persons": view.participation.headcount_repeat,
            "eligible_attendance": view.participation.attendance_count,
            "withdrawn_attendance": view.participation.withdrawn_attendance_count,
            "distinct_topic_transitions": len(view.topic_paths.transitions),
        }

    return {"firm": pack(firm), "tentative": pack(tentative)}


def run_analysis(
    bundle: Bundle,
    *,
    as_of: Optional[date] = None,
    k: int = 3,
    previous_anonymous_cells: Optional[Dict[str, int]] = None,
    now: Optional[datetime] = None,
) -> AnalysisResult:
    now = now or datetime.now()
    if as_of is None:
        as_of = max(event.date for event in bundle.events)

    firm_resolution, tentative_resolution, audits = resolve_identities(
        bundle, as_of
    )
    consent = ConsentResolver(bundle)

    firm = _build_view_result(bundle, firm_resolution, consent, "firm")
    tentative = _build_view_result(
        bundle, tentative_resolution, consent, "tentative"
    )

    feedback_firm = build_feedback_view(
        bundle, firm_resolution, firm.participation, consent
    )
    feedback_tentative = build_feedback_view(
        bundle, tentative_resolution, tentative.participation, consent
    )

    anon_firm = build_anonymization(
        bundle,
        firm_resolution,
        firm.participation,
        consent,
        k=k,
        previous_cells=previous_anonymous_cells,
    )
    anon_tentative = build_anonymization(
        bundle,
        tentative_resolution,
        tentative.participation,
        consent,
        k=k,
        previous_cells=previous_anonymous_cells,
    )

    snapshot = CaliberSnapshot(
        caliber_id=now.strftime("caliber-%Y%m%d-%H%M%S"),
        created_at=now.isoformat(timespec="seconds"),
        as_of=as_of.isoformat(),
        k=k,
        status_policy={
            "participation": list(PARTICIPATION_STATUSES),
            "cancel": list(CANCEL_STATUSES),
            "all_known": list(KNOWN_REG_STATUSES),
        },
        link_policy=LINK_POLICY,
        input_fingerprint=fingerprint_bundle(bundle),
        key_results=_key_results(firm, tentative),
        link_audit=[
            {
                "left_token": audit.link.left_token,
                "right_token": audit.link.right_token,
                "link_strength": audit.link.link_strength,
                "review": audit.link.review,
                "active": audit.active,
                "reason": audit.reason,
            }
            for audit in audits
        ],
        tentative_dependencies=tentative_resolution.tentative_dependencies,
        consent_summary=_consent_summary(bundle, consent),
        note="确定口径结论可对外；存疑口径数字依赖可撤回关联，须随附证据标记",
    )

    # 两个口径各自的异常分别保留（同一条登记在不同口径可能分属不同人）
    anomalies = {
        "firm": firm.participation.anomalies,
        "tentative": tentative.participation.anomalies,
    }

    return AnalysisResult(
        bundle=bundle,
        as_of=as_of,
        k=k,
        firm_resolution=firm_resolution,
        tentative_resolution=tentative_resolution,
        link_audit=audits,
        firm=firm,
        tentative=tentative,
        feedback_firm=feedback_firm,
        feedback_tentative=feedback_tentative,
        anonymization_firm=anon_firm,
        anonymization_tentative=anon_tentative,
        snapshot=snapshot,
        anomalies=anomalies,
    )
