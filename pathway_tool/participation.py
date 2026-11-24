"""参与时间线、首访与复访。

口径：

* 实际参与只认 ``attended``（正常签到）与 ``makeup``（补录）；
  ``cancelled``（取消）不计参与，但会在异常/调整清单中保留，
  说明它如何影响首访、复访归属。
* 同一人同场次多条登记去重；冲突状态（既到场又取消）进入异常清单，
  以存在到场记录为准并标注。
* 首访 = 该人最早的实际到场场次；复访次数 = 到场场次数 - 1。
  补录会按场次日期重新排序，因此可能改变首访与复访归属，
  每条记录保留 ``makeup`` 标记以便解释。
* 同意撤回的（人, 场次）记录不进入个人路径，仅进入匿名汇总池
  （见 anonymization 模块），本模块同时保留其计数用于口径说明。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .models import (
    CANCEL_STATUSES,
    Bundle,
    PARTICIPATION_STATUSES,
    Registration,
)
from .consent import ConsentResolver
from .identity import IdentityResolution


@dataclass
class PersonEvent:
    person_id: str
    event_id: str
    date: str
    topic: str
    series_version: str
    channel: str
    registration_ids: List[str]
    statuses: List[str]
    is_makeup: bool
    consent_state: str
    consent_basis: str
    household_token: str
    included_in_individual_path: bool


@dataclass
class ParticipationView:
    view: str
    # person_id -> 按场次日期排序的到场记录（含已撤回，撤回记录带标记）
    timelines: Dict[str, List[PersonEvent]] = field(default_factory=dict)
    first_visit: Dict[str, PersonEvent] = field(default_factory=dict)
    participant_person_ids: List[str] = field(default_factory=list)
    eligible_path_person_ids: List[str] = field(default_factory=list)
    repeat_person_ids: List[str] = field(default_factory=list)
    anomalies: List[dict] = field(default_factory=list)
    cancellations: List[dict] = field(default_factory=list)
    withdrawn_attendance_count: int = 0

    @property
    def headcount_first_visit(self) -> int:
        return len(self.eligible_path_person_ids)

    @property
    def headcount_repeat(self) -> int:
        return len(self.repeat_person_ids)

    @property
    def attendance_count(self) -> int:
        return sum(
            len([event for event in timeline if event.included_in_individual_path])
            for timeline in self.timelines.values()
        )


def _person_for_reg(
    reg: Registration, resolution: IdentityResolution
) -> Optional[str]:
    if reg.identity_token:
        return resolution.person_for(reg.identity_token)
    for entry in resolution.anonymous_participants:
        if entry["registration_id"] == reg.registration_id:
            return entry["person_id"]
    return None


def build_participation(
    bundle: Bundle,
    resolution: IdentityResolution,
    consent: ConsentResolver,
) -> ParticipationView:
    events_by_id = {event.event_id: event for event in bundle.events}
    states = consent.person_event_states(resolution)
    view = ParticipationView(view=resolution.view)

    # (person, event) -> 聚合记录
    merged: Dict[tuple, PersonEvent] = {}
    merged_regs: Dict[tuple, List[str]] = {}

    for reg in bundle.registrations:
        event = events_by_id.get(reg.event_id)
        if event is None:
            view.anomalies.append(
                {
                    "type": "unknown_event",
                    "registration_id": reg.registration_id,
                    "event_id": reg.event_id,
                }
            )
            continue
        person = _person_for_reg(reg, resolution)
        if person is None:
            view.anomalies.append(
                {
                    "type": "unresolved_identity",
                    "registration_id": reg.registration_id,
                }
            )
            continue

        if reg.status in CANCEL_STATUSES:
            view.cancellations.append(
                {
                    "registration_id": reg.registration_id,
                    "person_id": person,
                    "event_id": reg.event_id,
                    "status": reg.status,
                    "note": "取消不计实际参与；若该场次另有到场登记则以到场为准",
                }
            )
            continue

        if reg.status not in PARTICIPATION_STATUSES:
            view.anomalies.append(
                {
                    "type": "unknown_status",
                    "registration_id": reg.registration_id,
                    "status": reg.status,
                }
            )
            continue

        key = (person, reg.event_id)
        decision = states.get(person, {}).get(reg.event_id)
        consent_state = decision.state if decision else "unknown"
        consent_basis = decision.basis if decision else "no_evidence"
        included = consent_state == "granted"

        if key not in merged:
            merged[key] = PersonEvent(
                person_id=person,
                event_id=reg.event_id,
                date=event.date.isoformat(),
                topic=event.topic,
                series_version=event.series_version,
                channel=reg.channel,
                registration_ids=[],
                statuses=[],
                is_makeup=False,
                consent_state=consent_state,
                consent_basis=consent_basis,
                household_token=reg.household_token,
                included_in_individual_path=included,
            )
            merged_regs[key] = []
        record = merged[key]
        record.registration_ids.append(reg.registration_id)
        record.statuses.append(reg.status)
        merged_regs[key].append(reg.registration_id)
        if reg.status == "makeup":
            record.is_makeup = True
        # 任一组件撤回即整个人-场次退出个人路径
        if not included:
            record.included_in_individual_path = False
            record.consent_state = consent_state
            record.consent_basis = consent_basis

    # 同人同场次多登记的冲突检查
    for (person, event_id), reg_ids in merged_regs.items():
        if len(reg_ids) > 1:
            view.anomalies.append(
                {
                    "type": "duplicate_person_event",
                    "person_id": person,
                    "event_id": event_id,
                    "registration_ids": reg_ids,
                    "resolution": "同人同场次去重为一次到场",
                }
            )

    # 取消与到场并存
    for cancel in view.cancellations:
        key = (cancel["person_id"], cancel["event_id"])
        if key in merged:
            view.anomalies.append(
                {
                    "type": "cancel_and_attend_conflict",
                    "person_id": cancel["person_id"],
                    "event_id": cancel["event_id"],
                    "registration_id": cancel["registration_id"],
                    "resolution": "存在到场/补录登记，按实际到场计一次",
                }
            )

    # 组装时间线与首访/复访
    for (person, event_id), record in merged.items():
        view.timelines.setdefault(person, []).append(record)

    for person, timeline in view.timelines.items():
        timeline.sort(key=lambda item: (item.date, item.event_id))
        view.participant_person_ids.append(person)
        eligible = [item for item in timeline if item.included_in_individual_path]
        withdrawn = [item for item in timeline if not item.included_in_individual_path]
        view.withdrawn_attendance_count += len(withdrawn)
        if eligible:
            view.eligible_path_person_ids.append(person)
            view.first_visit[person] = eligible[0]
            if len(eligible) > 1:
                view.repeat_person_ids.append(person)

    view.participant_person_ids.sort()
    view.eligible_path_person_ids.sort()
    view.repeat_person_ids.sort()
    return view
