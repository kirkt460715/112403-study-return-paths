"""输入记录的数据类与状态口径常量。

所有字段保留输入的字面含义；空字符串表示该字段未填写，
由后续模块决定如何处理，而不是在加载阶段静默改写。
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

# 登记/签到状态：attended 正常签到，makeup 补录，cancelled 取消。
# 前两者计入实际参与，cancelled 不计入。
PARTICIPATION_STATUSES = ("attended", "makeup")
CANCEL_STATUSES = ("cancelled",)
KNOWN_REG_STATUSES = PARTICIPATION_STATUSES + CANCEL_STATUSES

LINK_STRENGTHS = ("confirmed", "possible", "distinct")
REVIEW_STATES = ("approved", "pending", "rejected")
CONSENT_STATES = ("granted", "withdrawn", "denied")
REG_CONSENT_STATES = ("yes", "no", "withdrawn", "")
TOUCH_TYPES_KNOWN = ()  # 接触类型为开放枚举，未知值不报错


@dataclass(frozen=True)
class Event:
    event_id: str
    date: date
    topic: str
    series_version: str


@dataclass(frozen=True)
class Registration:
    registration_id: str
    event_id: str
    identity_token: str  # 可能为空字符串：仅留下家庭预约编号
    household_token: str
    channel: str
    status: str
    consent: str  # yes / no / withdrawn / 空，登记时的同意快照


@dataclass(frozen=True)
class IdentityLink:
    left_token: str
    right_token: str
    link_strength: str  # confirmed / possible / distinct
    valid_from: Optional[date]
    valid_to: Optional[date]  # 空表示长期有效；valid_to 为含当日
    review: str


@dataclass(frozen=True)
class ConsentEvent:
    consent_id: str
    identity_token: str
    event_id: Optional[str]  # 空表示对该人的全局同意事件
    status: str
    effective_at: datetime


@dataclass(frozen=True)
class Touch:
    identity_token: str
    event_id: str
    touch_type: str
    touch_date: date


@dataclass(frozen=True)
class Feedback:
    """事后反馈（可选表）。feedback_id 为稳定行标识。"""

    feedback_id: str
    identity_token: str
    event_id: str
    interested_topics: List[str] = field(default_factory=list)
    score: Optional[int] = None
    comment: str = ""


@dataclass
class Bundle:
    """一次分析所读取的全部输入。"""

    events: List[Event]
    registrations: List[Registration]
    links: List[IdentityLink]
    consent_events: List[ConsentEvent]
    touches: List[Touch]
    feedback: List[Feedback]
    source_files: dict = field(default_factory=dict)  # 表名 -> 文件名
