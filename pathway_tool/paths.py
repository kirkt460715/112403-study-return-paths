"""专题衔接路径分析。

教研人员关心"参加过钱币分享的人是否愿意再来体验拓印或参加后续专题"，
因此本模块输出：

* 每位同意有效参与者的专题序列（按场次日期，含系列轮次）；
* 专题衔接矩阵：(from_topic, to_topic) -> 去重人数及人员清单，
  同人的同一条衔接只计一次；
* 指定专题的后续去向：从某专题出发的人后来去了哪些专题、各多少人；
* 复访人数（用于活动安排）与参与口径直接同源，身份关联更正后自动同步。

存疑口径下依赖 possible 合并的人员会在 ``depends_on_tentative`` 中列出。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .identity import IdentityResolution
from .participation import ParticipationView


@dataclass
class TopicPathView:
    view: str
    person_sequences: Dict[str, List[dict]] = field(default_factory=dict)
    transitions: Dict[Tuple[str, str], dict] = field(default_factory=dict)
    topic_followups: Dict[str, List[dict]] = field(default_factory=dict)
    depends_on_tentative: List[str] = field(default_factory=list)

    def transition_count(self, from_topic: str, to_topic: str) -> int:
        return self.transitions.get((from_topic, to_topic), {}).get("persons", 0)


def build_topic_paths(
    resolution: IdentityResolution,
    participation: ParticipationView,
) -> TopicPathView:
    view = TopicPathView(view=resolution.view)

    # 存疑口径中，凡是由 possible 关联把多个 token 拼成的人，
    # 其路径结论都依赖可撤回判断
    tentative_tokens = set()
    for dependency in resolution.tentative_dependencies:
        tentative_tokens.add(dependency["left_token"])
        tentative_tokens.add(dependency["right_token"])

    for person, timeline in participation.timelines.items():
        eligible = [item for item in timeline if item.included_in_individual_path]
        if not eligible:
            continue
        sequence = [
            {
                "event_id": item.event_id,
                "date": item.date,
                "topic": item.topic,
                "series_version": item.series_version,
                "is_makeup": item.is_makeup,
                "channel": item.channel,
            }
            for item in eligible
        ]
        view.person_sequences[person] = sequence
        if any(
            token in tentative_tokens
            for token in resolution.tokens_of(person)
        ):
            view.depends_on_tentative.append(person)

        # 相邻专题衔接（同专题连续两场也算复访衔接）
        for earlier, later in zip(sequence, sequence[1:]):
            key = (earlier["topic"], later["topic"])
            entry = view.transitions.setdefault(
                key,
                {
                    "from_topic": key[0],
                    "to_topic": key[1],
                    "person_ids": set(),
                    "examples": [],
                },
            )
            if person not in entry["person_ids"]:
                entry["person_ids"].add(person)
                entry["examples"].append(
                    {
                        "person_id": person,
                        "from_event": earlier["event_id"],
                        "to_event": later["event_id"],
                    }
                )

    for key, entry in view.transitions.items():
        entry["persons"] = len(entry["person_ids"])
        entry["person_ids"] = sorted(entry["person_ids"])

    # 专题后续去向（不止相邻，包含该专题之后的全部专题）
    followups: Dict[str, Dict[str, set]] = {}
    for person, sequence in view.person_sequences.items():
        seen_from = set()
        for index, step in enumerate(sequence):
            later_topics = {
                later["topic"] for later in sequence[index + 1 :]
            }
            if step["topic"] not in seen_from:
                seen_from.add(step["topic"])
            for topic in later_topics:
                followups.setdefault(step["topic"], {}).setdefault(
                    topic, set()
                ).add(person)
    for topic, targets in sorted(followups.items()):
        view.topic_followups[topic] = [
            {
                "next_topic": next_topic,
                "persons": len(persons),
                "person_ids": sorted(persons),
            }
            for next_topic, persons in sorted(targets.items())
        ]

    view.depends_on_tentative = sorted(set(view.depends_on_tentative))
    return view
