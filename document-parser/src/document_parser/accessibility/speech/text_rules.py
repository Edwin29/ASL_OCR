"""TEXT focus item -> Korean utterance string (plan document §8.2-§8.3):
assembles a mixed TEXT/MATH block's `spans` back into one utterance in their
original order, delegating MATH spans to `math_rules`.
"""

from __future__ import annotations

from typing import Any

from document_parser.accessibility.speech.math_rules import math_focus_item_to_speech


def text_focus_item_to_speech(item: dict[str, Any]) -> str:
    return describe_content_nodes(item.get("spans", []))


def describe_content_nodes(content_nodes: list[dict[str, Any]]) -> str:
    """Shared by TEXT spans, table cell `content_nodes`, and preserved visual
    text -- all three are lists of the same {kind: TEXT|MATH, ...} shape."""
    parts: list[str] = []
    join_next_text = False
    for node in content_nodes:
        if node.get("kind") == "MATH":
            spoken = math_focus_item_to_speech(node)
            join_next_text = node.get("standalone_accessibility") is False
        else:
            spoken = str(node.get("text", "")).strip()
        if spoken:
            if node.get("kind") != "MATH" and join_next_text and parts:
                parts[-1] += spoken
            else:
                parts.append(spoken)
        if node.get("kind") != "MATH":
            join_next_text = False
    return " ".join(parts)


def visual_focus_item_to_speech(item: dict[str, Any]) -> str:
    """Plan document §8.6: always announce the visual's existence, even when
    no text was preserved from it."""
    preserved = item.get("preserved_content", [])
    if not preserved:
        return "현재 지원하지 않는 그래프 또는 도형 영역입니다."
    body = describe_content_nodes(preserved)
    return f"현재 지원하지 않는 그래프 또는 도형 영역입니다. 인식된 글자는 다음과 같습니다. {body}"
