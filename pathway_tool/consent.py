"""同意状态解析。

规则（按优先级）：

1. ``consent_events`` 中针对该（身份标记, 场次）的事件，取 ``effective_at``
   最晚的一条；场次级记录优先于全局记录。
2. 没有同意事件时，回退到该登记上的同意快照 ``registrations.consent``
   （yes→granted，no→denied，withdrawn→withdrawn）。
3. 两者都无法判断时记为 ``unknown``，按"无同意"处理并写入异常清单，
   绝不默认视为已同意。

撤回的后果：

* 该（人, 场次）的参与记录退出一切**个人路径分析**，其渠道、路径、
  反馈均不得归因到这个人。
* 已不可识别到个人的**匿名汇总**（满足 k-匿名）可以继续保留，
  依据由 :mod:`pathway_tool.anonymization` 给出。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .models import Bundle, Registration
from .identity import IdentityResolution

_REG_CONSENT_MAP = {
    "yes": "granted",
    "no": "denied",
    "withdrawn": "withdrawn",
    "": "unknown",
}


@dataclass
class ConsentDecision:
    state: str  # granted / withdrawn / denied / unknown
    basis: str
    source_id: Optional[str]  # consent_id 或 registration_id
    effective_at: Optional[datetime] = None


def _withdrawal_first(existing: ConsentDecision, new: ConsentDecision) -> bool:
    """同一人同场次出现多条记录时，撤回状态优先。"""

    if new.state == "withdrawn":
        return True
    if existing.state == "withdrawn":
        return False
    # 其余情况以证据时间更晚者为准；无时间信息时保留原值
    if new.effective_at and existing.effective_at:
        return new.effective_at > existing.effective_at
    return False


class ConsentResolver:
    def __init__(self, bundle: Bundle):
        self._bundle = bundle
        # (token, event_id) 与 (token, None=全局) 各自的时间线
        self._timelines: Dict[Tuple[str, Optional[str]], List] = {}
        for event in bundle.consent_events:
            self._timelines.setdefault(
                (event.identity_token, event.event_id), []
            ).append(event)
        for rows in self._timelines.values():
            rows.sort(key=lambda item: item.effective_at)
        self._reg_index = {
            reg.registration_id: reg for reg in bundle.registrations
        }

    def for_token_event(self, token: str, event_id: str) -> ConsentDecision:
        # 场次级优先，其次全局，均取最晚一条
        specific = self._timelines.get((token, event_id))
        general = self._timelines.get((token, None))
        chosen = None
        if specific and general:
            chosen = max(
                [specific[-1], general[-1]], key=lambda item: item.effective_at
            )
        elif specific:
            chosen = specific[-1]
        elif general:
            chosen = general[-1]
        if chosen is not None:
            return ConsentDecision(
                state=chosen.status,
                basis="consent_event",
                source_id=chosen.consent_id,
                effective_at=chosen.effective_at,
            )

        # 回退：登记快照。以该 token 在该场次的登记为准（理论上只有一条）
        for reg in self._bundle.registrations:
            if reg.identity_token == token and reg.event_id == event_id:
                return ConsentDecision(
                    state=_REG_CONSENT_MAP[reg.consent],
                    basis="registration_snapshot",
                    source_id=reg.registration_id,
                )
        return ConsentDecision(state="unknown", basis="no_evidence", source_id=None)

    def for_registration(self, reg: Registration) -> ConsentDecision:
        """对一条登记解析同意；匿名参与者按登记快照处理。"""

        if reg.identity_token:
            return self.for_token_event(reg.identity_token, reg.event_id)
        return ConsentDecision(
            state=_REG_CONSENT_MAP[reg.consent],
            basis="registration_snapshot",
            source_id=reg.registration_id,
        )

    def person_event_states(
        self, resolution: IdentityResolution
    ) -> Dict[str, Dict[str, ConsentDecision]]:
        """返回 person_id -> event_id -> 该人在该场次的同意决定。

        一个 person 在同场次可能由多个 token 留下记录；只要任一组件已撤回，
        该（人, 场次）按撤回处理（撤回优先于授权），并在 basis 中说明。
        """

        result: Dict[str, Dict[str, ConsentDecision]] = {}
        for reg in self._bundle.registrations:
            if reg.identity_token:
                person = resolution.person_for(reg.identity_token)
            else:
                # 匿名参与者 id 在解析阶段生成，登记本身没有 token，
                # 这里按登记反查匿名 person
                person = self._anon_person_for_reg(reg, resolution)
            if person is None:
                continue
            decision = self.for_registration(reg)
            bucket = result.setdefault(person, {})
            existing = bucket.get(reg.event_id)
            if existing is None or _withdrawal_first(existing, decision):
                bucket[reg.event_id] = decision
        return result

    @staticmethod
    def _anon_person_for_reg(reg: Registration, resolution: IdentityResolution):
        for entry in resolution.anonymous_participants:
            if entry["registration_id"] == reg.registration_id:
                return entry["person_id"]
        return None
