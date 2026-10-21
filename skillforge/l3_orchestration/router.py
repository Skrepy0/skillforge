"""意图路由：关键词匹配 + 置信度，低置信度触发澄清。"""

from __future__ import annotations

from skillforge.shared.config import RoutingConfig
from skillforge.shared.types import RouteDecision


class Router:
    def __init__(self, config: RoutingConfig) -> None:
        self.config = config

    def route(self, request: str) -> RouteDecision:
        text = request.lower()
        scores: list[tuple[str, float]] = []

        for skill, keywords in self.config.keywords.items():
            hits = sum(1 for kw in keywords if kw.lower() in text)
            if hits:
                # 命中词数 / 关键词总数，归一化到 0–1
                scores.append((skill, hits / max(len(keywords), 1)))

        if not scores:
            return RouteDecision(skill=None, confidence=0.0, needs_clarification=True)

        scores.sort(key=lambda x: x[1], reverse=True)
        top_skill, top_score = scores[0]

        if top_score < self.config.similarity_threshold:
            return RouteDecision(
                skill=None,
                confidence=top_score,
                candidates=scores,
                needs_clarification=True,
            )

        if len(scores) > 1 and top_score - scores[1][1] < self.config.clarify_gap:
            return RouteDecision(
                skill=None,
                confidence=top_score,
                candidates=scores,
                needs_clarification=True,
            )

        return RouteDecision(skill=top_skill, confidence=top_score, candidates=scores)
