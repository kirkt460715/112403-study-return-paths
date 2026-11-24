"""按清单（manifest）读取 CSV 并做行级校验。

设计要点：

* 清单声明每张表的列名与稳定主键；列顺序不符或主键重复直接报错，
  避免静默错列导致身份张冠李戴。
* 空字段保留为空字符串（日期字段解析为 ``None``）。
* 提供 ``bundle_from_rows`` 供测试用内存数据构造，无需落盘。
* 反馈表为可选输入：清单中声明则必须可读，未声明则不加载。
"""

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from .models import (
    Bundle,
    CONSENT_STATES,
    ConsentEvent,
    Event,
    Feedback,
    IdentityLink,
    KNOWN_REG_STATUSES,
    LINK_STRENGTHS,
    REG_CONSENT_STATES,
    Registration,
    REVIEW_STATES,
    Touch,
)


class InputError(ValueError):
    """输入数据不满足契约时抛出。"""


def _parse_date(value: str, context: str) -> Optional[date]:
    value = value.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f"{context}: 非法日期 {value!r}") from exc


def _parse_datetime(value: str, context: str) -> datetime:
    value = value.strip()
    if not value:
        raise InputError(f"{context}: 同意事件时间不能为空")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f"{context}: 非法时间 {value!r}") from exc


def _read_csv(path: Path, columns: List[str], context: str) -> List[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != columns:
            raise InputError(
                f"{context}: 列不匹配，期望 {columns}，实际 {reader.fieldnames}"
            )
        return list(reader)


def _check_key(rows: List[dict], key: Optional[str], context: str) -> None:
    if not key:
        return
    values = [row[key] for row in rows]
    if any(v == "" for v in values):
        raise InputError(f"{context}: 主键 {key} 存在空值")
    if len(values) != len(set(values)):
        raise InputError(f"{context}: 主键 {key} 重复")


def _events(rows: List[dict]) -> List[Event]:
    result = []
    seen = set()
    for i, row in enumerate(rows, start=2):
        ctx = f"events.csv 第{i}行"
        event = Event(
            event_id=row["event_id"].strip(),
            date=_parse_date(row["date"], ctx),
            topic=row["topic"].strip(),
            series_version=row["series_version"].strip(),
        )
        if not event.event_id or event.date is None:
            raise InputError(f"{ctx}: event_id/date 不能为空")
        if event.event_id in seen:
            raise InputError(f"{ctx}: event_id 重复")
        seen.add(event.event_id)
        result.append(event)
    return result


def _registrations(rows: List[dict]) -> List[Registration]:
    result = []
    for i, row in enumerate(rows, start=2):
        ctx = f"registrations.csv 第{i}行"
        status = row["status"].strip()
        if status not in KNOWN_REG_STATUSES:
            raise InputError(
                f"{ctx}: 未知登记状态 {status!r}，"
                f"已知状态为 {KNOWN_REG_STATUSES}（需扩展状态口径时显式配置）"
            )
        consent = row["consent"].strip()
        if consent not in REG_CONSENT_STATES:
            raise InputError(f"{ctx}: 登记同意值 {consent!r} 不在口径内")
        reg = Registration(
            registration_id=row["registration_id"].strip(),
            event_id=row["event_id"].strip(),
            identity_token=row["identity_token"].strip(),
            household_token=row["household_token"].strip(),
            channel=row["channel"].strip(),
            status=status,
            consent=consent,
        )
        if not reg.registration_id or not reg.event_id:
            raise InputError(f"{ctx}: registration_id/event_id 不能为空")
        result.append(reg)
    return result


def _links(rows: List[dict]) -> List[IdentityLink]:
    result = []
    for i, row in enumerate(rows, start=2):
        ctx = f"identity_links.csv 第{i}行"
        strength = row["link_strength"].strip()
        review = row["review"].strip()
        if strength not in LINK_STRENGTHS:
            raise InputError(f"{ctx}: 未知关联强度 {strength!r}")
        if review not in REVIEW_STATES:
            raise InputError(f"{ctx}: 未知审核状态 {review!r}")
        left, right = row["left_token"].strip(), row["right_token"].strip()
        if not left or not right or left == right:
            raise InputError(f"{ctx}: 关联两端必须为不同的非空身份标记")
        result.append(
            IdentityLink(
                left_token=left,
                right_token=right,
                link_strength=strength,
                valid_from=_parse_date(row["valid_from"], ctx),
                valid_to=_parse_date(row["valid_to"], ctx),
                review=review,
            )
        )
    return result


def _consent_events(rows: List[dict]) -> List[ConsentEvent]:
    result = []
    for i, row in enumerate(rows, start=2):
        ctx = f"consent_events.csv 第{i}行"
        status = row["status"].strip()
        if status not in CONSENT_STATES:
            raise InputError(f"{ctx}: 未知同意状态 {status!r}")
        result.append(
            ConsentEvent(
                consent_id=row["consent_id"].strip(),
                identity_token=row["identity_token"].strip(),
                event_id=row["event_id"].strip() or None,
                effective_at=_parse_datetime(row["effective_at"], ctx),
                status=status,
            )
        )
    return result


def _touches(rows: List[dict]) -> List[Touch]:
    result = []
    for i, row in enumerate(rows, start=2):
        ctx = f"touches.csv 第{i}行"
        result.append(
            Touch(
                identity_token=row["identity_token"].strip(),
                event_id=row["event_id"].strip(),
                touch_type=row["touch_type"].strip(),
                touch_date=_parse_date(row["touch_date"], ctx),
            )
        )
    return result


def _feedback(rows: List[dict], columns: List[str]) -> List[Feedback]:
    result = []
    for i, row in enumerate(rows, start=2):
        ctx = f"feedback.csv 第{i}行"
        raw_score = row["score"].strip() if "score" in columns else ""
        score: Optional[int]
        if raw_score:
            try:
                score = int(raw_score)
            except ValueError as exc:
                raise InputError(f"{ctx}: score 非整数 {raw_score!r}") from exc
        else:
            score = None
        topics = [
            item.strip()
            for item in row.get("interested_topics", "").split(";")
            if item.strip()
        ]
        result.append(
            Feedback(
                feedback_id=row["feedback_id"].strip(),
                identity_token=row["identity_token"].strip(),
                event_id=row["event_id"].strip(),
                interested_topics=topics,
                score=score,
                comment=row.get("comment", "").strip(),
            )
        )
    return result


_FEEDBACK_COLUMNS = [
    "feedback_id",
    "identity_token",
    "event_id",
    "interested_topics",
    "score",
    "comment",
]


def load_bundle(data_dir: Path) -> Bundle:
    """按清单读取整个数据目录。"""

    data_dir = Path(data_dir)
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    tables: Dict[str, List[dict]] = {}
    files: Dict[str, str] = {}
    for table in manifest["tables"]:
        name = table["file"]
        rows = _read_csv(data_dir / name, table["columns"], name)
        _check_key(rows, table.get("key"), name)
        tables[name] = rows
        files[name.removesuffix(".csv")] = name

    feedback: List[Feedback] = []
    if "feedback.csv" in tables:
        feedback = _feedback(tables["feedback.csv"], manifest_feedback_columns(manifest))

    return Bundle(
        events=_events(tables["events.csv"]),
        registrations=_registrations(tables["registrations.csv"]),
        links=_links(tables["identity_links.csv"]),
        consent_events=_consent_events(tables["consent_events.csv"]),
        touches=_touches(tables["touches.csv"]),
        feedback=feedback,
        source_files=files,
    )


def manifest_feedback_columns(manifest: dict) -> List[str]:
    for table in manifest["tables"]:
        if table["file"] == "feedback.csv":
            return table["columns"]
    return _FEEDBACK_COLUMNS


def bundle_from_rows(
    *,
    events=None,
    registrations=None,
    links=None,
    consent_events=None,
    touches=None,
    feedback=None,
) -> Bundle:
    """由内存中的 dict 行构造 Bundle，供测试与单轮重跑使用。

    日期/时间字段可直接传入 ``date``/``datetime``，也可传入 ISO 字符串。
    """

    def as_date(value):
        if value is None or isinstance(value, date):
            return value
        return date.fromisoformat(value)

    def as_dt(value):
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value)

    event_objs = [
        Event(
            event_id=r["event_id"],
            date=as_date(r["date"]),
            topic=r["topic"],
            series_version=r["series_version"],
        )
        for r in (events or [])
    ]
    reg_objs = [Registration(**r) for r in (registrations or [])]
    link_objs = [
        IdentityLink(
            left_token=r["left_token"],
            right_token=r["right_token"],
            link_strength=r["link_strength"],
            valid_from=as_date(r.get("valid_from")),
            valid_to=as_date(r.get("valid_to")),
            review=r["review"],
        )
        for r in (links or [])
    ]
    consent_objs = [
        ConsentEvent(
            consent_id=r["consent_id"],
            identity_token=r["identity_token"],
            event_id=r.get("event_id"),
            status=r["status"],
            effective_at=as_dt(r["effective_at"]),
        )
        for r in (consent_events or [])
    ]
    touch_objs = [
        Touch(
            identity_token=r["identity_token"],
            event_id=r["event_id"],
            touch_type=r["touch_type"],
            touch_date=as_date(r["touch_date"]),
        )
        for r in (touches or [])
    ]
    feedback_objs = [Feedback(**r) for r in (feedback or [])]
    return Bundle(
        events=event_objs,
        registrations=reg_objs,
        links=link_objs,
        consent_events=consent_objs,
        touches=touch_objs,
        feedback=feedback_objs,
    )
