"""分层身份解析。

输入侧只有三类线索：

1. 登记上的 ``identity_token``（可能缺失，仅有家庭预约编号）；
2. 人工维护的关联表 ``identity_links``，强度分为
   ``confirmed``（确定关联）、``possible``（可能关联）、
   ``distinct``（明确不同），并带有效期与审核状态；
3. ``household_token`` 家庭预约编号，只用于识别同家庭，**不用于合并人**。

解析产出两个口径：

* ``firm``（确定口径）：只采纳"在有效期内 + 已审核通过"的 confirmed 关联。
  该口径下的结论可作为确定结论对外使用。
* ``tentative``（存疑口径）：在 firm 基础上追加 possible 关联
  （含待审核 pending）。每条追加的关联都作为可撤回判断写入
  ``tentative_dependencies``，报告中凡依赖该口径的数字都会带证据标记。

``distinct`` 关联是硬约束：任何口径下被它明确区分的两个标记都不允许
合并，违反时抛出 :class:`IdentityConflictError`，交由人工核查。
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Set, Tuple

from .models import Bundle, IdentityLink

ANON_PREFIX = "ANON-"


class IdentityConflictError(ValueError):
    """关联证据互相矛盾（例如 confirmed 与 distinct 同时成立）。"""


class _UnionFind:
    def __init__(self, items):
        self.parent = {item: item for item in items}

    def find(self, item):
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != item:
            parent = self.parent[item]
            self.parent[item] = root
            item = parent
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # 取字典序较小者作为根，保证 person_id 稳定
            if ra > rb:
                ra, rb = rb, ra
            self.parent[rb] = ra


@dataclass
class LinkAudit:
    """单条关联在评估时点的可用性结论。"""

    link: IdentityLink
    active: bool
    reason: str  # active / expired / not_started / rejected / 强度说明


@dataclass
class IdentityResolution:
    view: str
    as_of: date
    # token -> person_id
    token_to_person: Dict[str, str]
    # person_id -> 该人包含的全部 token（含家庭匿名标记）
    person_tokens: Dict[str, List[str]]
    # household -> person_id 集合（仅作家庭分组，不合并人）
    household_persons: Dict[str, List[str]]
    # 本口径实际采纳的关联（(left,right) -> 关联记录）
    applied_links: Dict[Tuple[str, str], IdentityLink]
    # 存疑口径相对确定口径额外依赖的可撤回判断
    tentative_dependencies: List[dict] = field(default_factory=list)
    # 仅家庭编号、没有身份标记的匿名参与者说明
    anonymous_participants: List[dict] = field(default_factory=list)

    def person_for(self, token: str) -> Optional[str]:
        return self.token_to_person.get(token)

    def tokens_of(self, person_id: str) -> List[str]:
        return self.person_tokens.get(person_id, [])


def _audit_link(link: IdentityLink, as_of: date) -> LinkAudit:
    if link.review == "rejected":
        return LinkAudit(link, False, "rejected：审核已驳回，任何口径均不采纳")
    if link.valid_from and as_of < link.valid_from:
        return LinkAudit(link, False, "not_started：valid_from 尚未到达")
    if link.valid_to and as_of > link.valid_to:
        return LinkAudit(link, False, "expired：已超过 valid_to（含当日有效）")
    return LinkAudit(link, True, "active：评估时点有效")


def audit_links(bundle: Bundle, as_of: date) -> List[LinkAudit]:
    return [_audit_link(link, as_of) for link in bundle.links]


def _collect_tokens(bundle: Bundle) -> Set[str]:
    tokens: Set[str] = set()
    for reg in bundle.registrations:
        if reg.identity_token:
            tokens.add(reg.identity_token)
    for link in bundle.links:
        tokens.add(link.left_token)
        tokens.add(link.right_token)
    for consent in bundle.consent_events:
        tokens.add(consent.identity_token)
    for touch in bundle.touches:
        tokens.add(touch.identity_token)
    for feedback in bundle.feedback:
        if feedback.identity_token:
            tokens.add(feedback.identity_token)
    return tokens


def _build_view(
    bundle: Bundle,
    audits: List[LinkAudit],
    as_of: date,
    view: str,
) -> IdentityResolution:
    tokens = _collect_tokens(bundle)
    uf = _UnionFind(sorted(tokens))

    active_by_strength = {"confirmed": [], "possible": [], "distinct": []}
    for audit in audits:
        if audit.active:
            active_by_strength[audit.link.link_strength].append(audit.link)

    # 确定口径只采纳 confirmed；存疑口径追加 possible（含 pending）
    firm_links = active_by_strength["confirmed"]
    extra_links: List[IdentityLink] = []
    if view == "tentative":
        extra_links = active_by_strength["possible"]

    applied: Dict[Tuple[str, str], IdentityLink] = {}
    for link in firm_links + extra_links:
        uf.union(link.left_token, link.right_token)
        applied[(link.left_token, link.right_token)] = link

    # distinct 是硬约束：检查最终分组是否违反
    for link in active_by_strength["distinct"]:
        if uf.find(link.left_token) == uf.find(link.right_token):
            raise IdentityConflictError(
                f"关联冲突：{link.left_token} 与 {link.right_token} "
                f"被标记为 distinct，却被其他有效关联合并到同一人；"
                f"请人工核查后再运行分析"
            )

    token_to_person: Dict[str, str] = {token: uf.find(token) for token in tokens}
    person_tokens: Dict[str, List[str]] = {}
    for token, person in sorted(token_to_person.items()):
        person_tokens.setdefault(person, []).append(token)

    # 仅有家庭预约编号的登记：生成家庭范围内的匿名参与者，不与任何人合并
    anonymous_participants: List[dict] = []
    anon_reg_to_person: Dict[str, str] = {}
    anon_counter: Dict[str, int] = {}
    for reg in bundle.registrations:
        if reg.identity_token:
            continue
        anon_counter[reg.household_token] = anon_counter.get(reg.household_token, 0) + 1
        seq = anon_counter[reg.household_token]
        anon_id = f"{ANON_PREFIX}{reg.household_token}-{seq}"
        anon_reg_to_person[reg.registration_id] = anon_id
        if anon_id not in token_to_person:
            token_to_person[anon_id] = anon_id
            person_tokens[anon_id] = [anon_id]
            anonymous_participants.append(
                {
                    "person_id": anon_id,
                    "household_token": reg.household_token,
                    "reason": "登记未留身份标记，仅家庭预约编号；家庭内单独编号且不与他人合并",
                    "registration_id": reg.registration_id,
                }
            )

    # 家庭分组只用于提示同行关系，绝不作为合并人的依据
    household_persons: Dict[str, Set[str]] = {}
    for reg in bundle.registrations:
        if reg.identity_token:
            person = token_to_person[reg.identity_token]
        else:
            person = anon_reg_to_person[reg.registration_id]
        household_persons.setdefault(reg.household_token, set()).add(person)

    dependencies = []
    if view == "tentative":
        for link in extra_links:
            dependencies.append(
                {
                    "type": "possible_link",
                    "left_token": link.left_token,
                    "right_token": link.right_token,
                    "review": link.review,
                    "valid_from": link.valid_from.isoformat() if link.valid_from else None,
                    "valid_to": link.valid_to.isoformat() if link.valid_to else None,
                    "withdrawable": True,
                    "note": "可能关联/待审核判断，可被人工更正撤回；依赖该判断的结论不得作为确定结论",
                }
            )

    return IdentityResolution(
        view=view,
        as_of=as_of,
        token_to_person=token_to_person,
        person_tokens={pid: sorted(tks) for pid, tks in sorted(person_tokens.items())},
        household_persons={
            hh: sorted(persons) for hh, persons in sorted(household_persons.items())
        },
        applied_links=applied,
        tentative_dependencies=dependencies,
        anonymous_participants=anonymous_participants,
    )


def resolve_identities(
    bundle: Bundle, as_of: Optional[date] = None
) -> Tuple[IdentityResolution, IdentityResolution, List[LinkAudit]]:
    """同时产出确定口径、存疑口径与关联审计清单。"""

    if as_of is None:
        # 默认以数据中最晚活动日期为评估时点，保证演练场景可复现
        as_of = max(event.date for event in bundle.events)
    audits = audit_links(bundle, as_of)
    firm = _build_view(bundle, audits, as_of, "firm")
    tentative = _build_view(bundle, audits, as_of, "tentative")
    return firm, tentative, audits
