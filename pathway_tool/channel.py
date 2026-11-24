"""渠道实际参与效果与接触转化。

宣传人员需要的是"渠道带来的**实际参与**"而不是报名点击，因此所有指标
都以实际到场（attended/makeup）为分母：

* registrations：各渠道登记数（含取消，仅供对照）
* attended_person_events：实际到场人次（人-场次去重后）
* first_time_persons：该渠道作为**首访渠道**带来的首次参与人数
* touches / touched_persons：渠道接触条数与接触到的去重人数
* touched_and_attended_persons：接触后在对应场次实际到场、且同意有效
  的去重人数（接触 → 实际参与转化）
* 同场次多渠道接触只做接触计数，首访渠道以报名登记的 channel 为准

只统计同意有效（granted）的个人记录；撤回记录进入匿名汇总池。
"""

from dataclasses import dataclass, field
from typing import Dict, List

from .models import Bundle
from .identity import IdentityResolution
from .participation import ParticipationView


@dataclass
class ChannelRow:
    channel: str
    registrations: int = 0
    registrations_cancelled: int = 0
    attended_person_events: int = 0
    first_time_persons: int = 0
    repeat_person_events: int = 0
    touches: int = 0
    touched_persons: int = 0
    touched_and_attended_persons: int = 0
    evidence: List[str] = field(default_factory=list)


def build_channel_view(
    bundle: Bundle,
    resolution: IdentityResolution,
    participation: ParticipationView,
) -> Dict[str, ChannelRow]:
    rows: Dict[str, ChannelRow] = {}

    def row(channel: str) -> ChannelRow:
        name = channel or "未填写"
        return rows.setdefault(name, ChannelRow(channel=name))

    # 登记侧（含取消对照）
    for reg in bundle.registrations:
        entry = row(reg.channel)
        entry.registrations += 1
        if reg.status == "cancelled":
            entry.registrations_cancelled += 1

    # 到场侧（仅同意有效、可进入个人路径的记录）
    for person, timeline in participation.timelines.items():
        eligible = [item for item in timeline if item.included_in_individual_path]
        for index, record in enumerate(eligible):
            entry = row(record.channel)
            entry.attended_person_events += 1
            if index == 0:
                entry.first_time_persons += 1
                entry.evidence.append(
                    f"{person} 首访 {record.event_id} 渠道={record.channel or '未填写'}"
                )
            else:
                entry.repeat_person_events += 1

    # 接触侧：先按 (渠道, person) 去重，再映射到当前身份口径
    touched_persons: Dict[str, set] = {}
    for touch in bundle.touches:
        entry = row(touch.touch_type)
        entry.touches += 1
        person = resolution.person_for(touch.identity_token)
        if person is not None:
            touched_persons.setdefault(entry.channel, set()).add(person)

    # 同意有效的到场 (person, event) 集合
    eligible_attendance = {
        (person, record.event_id)
        for person, timeline in participation.timelines.items()
        for record in timeline
        if record.included_in_individual_path
    }

    # 接触 → 实际参与转化：同一人在该渠道接触过的场次中至少一场实际到场
    converted: Dict[str, set] = {}
    for touch in bundle.touches:
        name = touch.touch_type or "未填写"
        person = resolution.person_for(touch.identity_token)
        if person is not None and (person, touch.event_id) in eligible_attendance:
            converted.setdefault(name, set()).add(person)
    for name, persons in converted.items():
        rows[name].touched_and_attended_persons = len(persons)
    for name, persons in touched_persons.items():
        rows[name].touched_persons = len(persons)

    return dict(sorted(rows.items()))
