"""事后反馈处理。

两条硬规则：

1. 反馈只归属于填写反馈的那个身份（token -> person），**同一家庭成员
   不互相继承学习反馈**：即使 household_token 相同，也不能把 A 的反馈
   算到 B 的路径上。
2. 反馈同样受同意约束：反馈对应（人, 场次）已撤回同意时，该条反馈
   退出个人级分析，仅可在满足 k-匿名时进入匿名汇总。

输出按专题汇总"愿意再来/感兴趣的后续专题"，并标注每条结论的证据等级
（确定口径 / 依赖可撤回关联）。
"""

from dataclasses import dataclass, field
from typing import Dict, List

from .consent import ConsentResolver
from .identity import IdentityResolution
from .models import Bundle
from .participation import ParticipationView


@dataclass
class FeedbackView:
    view: str
    # topic -> 后续意向专题 -> 人数与证据
    topic_interest: Dict[str, Dict[str, dict]] = field(default_factory=dict)
    person_feedback: Dict[str, List[dict]] = field(default_factory=dict)
    excluded: List[dict] = field(default_factory=list)
    household_isolation_checks: List[dict] = field(default_factory=list)


def build_feedback_view(
    bundle: Bundle,
    resolution: IdentityResolution,
    participation: ParticipationView,
    consent: ConsentResolver,
) -> FeedbackView:
    view = FeedbackView(view=resolution.view)
    tentative_tokens = {
        token
        for dependency in resolution.tentative_dependencies
        for token in (dependency["left_token"], dependency["right_token"])
    }

    # 家庭隔离核查：同一 household 下不同 person 的反馈条数应各自独立
    household_feedback: Dict[str, Dict[str, int]] = {}

    for item in bundle.feedback:
        person = resolution.person_for(item.identity_token)
        if person is None:
            view.excluded.append(
                {
                    "feedback_id": item.feedback_id,
                    "reason": "身份无法解析到当前口径中的参与者",
                }
            )
            continue

        decision = consent.for_token_event(item.identity_token, item.event_id)
        if decision.state != "granted":
            view.excluded.append(
                {
                    "feedback_id": item.feedback_id,
                    "person_id": person,
                    "event_id": item.event_id,
                    "consent_state": decision.state,
                    "reason": "同意非 granted，反馈不进入个人级分析",
                }
            )
            continue

        # 反馈必须对应本人真实到场的场次，防止把反馈挂到未参与的活动上
        timeline = participation.timelines.get(person, [])
        attended_events = {
            record.event_id
            for record in timeline
            if record.included_in_individual_path
        }
        if item.event_id not in attended_events:
            view.excluded.append(
                {
                    "feedback_id": item.feedback_id,
                    "person_id": person,
                    "event_id": item.event_id,
                    "reason": "反馈场次不在本人同意有效的到场记录中",
                }
            )
            continue

        topic = next(
            (
                record.topic
                for record in timeline
                if record.event_id == item.event_id
            ),
            item.event_id,
        )
        evidence_level = (
            "tentative"
            if any(
                token in tentative_tokens
                for token in resolution.tokens_of(person)
            )
            else "firm"
        )
        record = {
            "feedback_id": item.feedback_id,
            "event_id": item.event_id,
            "topic": topic,
            "interested_topics": item.interested_topics,
            "score": item.score,
            "evidence_level": evidence_level,
        }
        view.person_feedback.setdefault(person, []).append(record)

        for wanted in item.interested_topics:
            bucket = view.topic_interest.setdefault(topic, {}).setdefault(
                wanted,
                {"persons": set(), "firm_persons": set(), "person_ids": []},
            )
            bucket["persons"].add(person)
            if evidence_level == "firm":
                bucket["firm_persons"].add(person)

    for topic, interests in view.topic_interest.items():
        for wanted, bucket in interests.items():
            bucket["person_count"] = len(bucket["persons"])
            bucket["firm_person_count"] = len(bucket["firm_persons"])
            bucket["person_ids"] = sorted(bucket.pop("persons"))
            bucket.pop("firm_persons")

    # 家庭隔离核查：按 person 统计实际采纳的反馈条数，每人只统计一次，
    # 家庭归属经登记反查（同一 person 可能有多条登记，取其家庭集合）
    person_households: Dict[str, set] = {}
    for reg in bundle.registrations:
        person = resolution.person_for(reg.identity_token)
        if person is not None:
            person_households.setdefault(person, set()).add(reg.household_token)
    for person, records in view.person_feedback.items():
        for household in person_households.get(person, set()):
            household_feedback.setdefault(household, {})[person] = len(records)

    for household, per_person in sorted(household_feedback.items()):
        view.household_isolation_checks.append(
            {
                "household_token": household,
                "feedback_by_person": {
                    person: count for person, count in sorted(per_person.items())
                },
                "rule": "反馈按 person 独立归属，家庭成员之间不继承、不串用",
            }
        )
    return view
