from __future__ import annotations

from typing import Any


class CategoryResolver:
    """
    Deterministic fallback category resolver.

    Only used if the LLM omits a category.
    """
    TOPIC_RULES = [
        (
            "climate",
            {
                "e1 climate change",
                "climate change",
            },
        ),
    ]

    TITLE_RULES = [
        (
            "cyber",
            {
                "cyber",
                "cybersecurity",
                "cyber security",
            },
        ),
        (
            "geopolitical",
            {
                "geopolitical",
                "geopolitics",
            },
        ),
        (
            "operational",
            {
                "execution",
                "operational",
            },
        ),
        (
            "governance",
            {
                "corruption",
                "bribery",
                "governance",
            },
        ),
        (
            "workforce",
            {
                "workforce",
                "worker",
                "injury",
                "injuries",
                "labour",
            },
        ),
    ]

    CONTEXT_RULES = [
        (
            "cyber",
            {
                "cyber",
                "ransomware",
                "data breach",
            },
        ),
        (
            "geopolitical",
            {
                "geopolitical",
                "sanctions",
                "trade tensions",
                "political tensions",
            },
        ),
        (
            "regulatory",
            {
                "regulatory",
                "regulation",
                "tariff",
                "tariffs",
                "export control",
                "compliance",
                "fines",
                "permit",
            },
        ),
        (
            "climate",
            {
                "climate",
                "carbon",
                "emissions",
                "ghg",
                "biodiversity",
            },
        ),
        (
            "operational",
            {
                "execution",
                "production",
                "quality",
                "timeline",
                "project delivery",
            },
        ),
        (
            "supply_chain",
            {
                "supply chain",
                "supplier",
                "logistics",
                "component availability",
            },
        ),
        (
            "workforce",
            {
                "employee",
                "workforce",
                "worker",
                "injury",
                "injuries",
                "labour",
                "health and safety",
            },
        ),
        (
            "governance",
            {
                "corruption",
                "bribery",
                "fraud",
                "ethics",
            },
        ),
        (
            "market",
            {
                "market",
                "auction",
                "competition",
                "demand",
                "grid expansion",
            },
        ),
        (
            "financial",
            {
                "financial",
                "economic loss",
                "margin",
                "cost implication",
            },
        ),
    ]

    @classmethod
    def resolve_from_topic(
        cls,
        topic: str | None,
    ) -> str | None:
        """
        Resolve category from a strong source taxonomy signal.

        Returns None when the source topic is not sufficiently
        specific to determine one canonical risk category.
        """

        if not topic:
            return None

        normalized_topic = (
            str(topic)
            .strip()
            .lower()
        )

        for category, topic_terms in cls.TOPIC_RULES:
            if any(
                term in normalized_topic
                for term in topic_terms
            ):
                return category

        return None

    @classmethod
    def resolve(
        cls,
        risk: dict[str, Any],
        *,
        topic: str | None = None,
    ) -> str:

        title = str(
            risk.get(
                "title",
                "",
            )
        ).lower()

        for (
            category,
            keywords,
        ) in cls.TITLE_RULES:

            if any(
                keyword in title
                for keyword in keywords
            ):
                return category

        context = " ".join(
            [
                title,
                str(
                    risk.get(
                        "description",
                        "",
                    )
                ).lower(),
                str(
                    topic or ""
                ).lower(),
            ]
        )

        for (
            category,
            keywords,
        ) in cls.CONTEXT_RULES:

            if any(
                keyword in context
                for keyword in keywords
            ):
                return category

        return "other"