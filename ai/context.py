from typing import Any, Dict, List

from knowledge_retriever import MinecraftKnowledgeRetriever


# ============================================================
# MINECRAFT KNOWLEDGE CONTEXT
# ============================================================

class MinecraftKnowledgeContext:

    def __init__(
        self,
        version="1.21.11",
        max_results=10
    ):

        self.version = version
        self.max_results = max_results

        self.retriever = MinecraftKnowledgeRetriever(
            version=version
        )

    # ========================================================
    # BUILD SEARCH QUERY
    # ========================================================

    def _build_query(
        self,
        understanding: Dict[str, Any]
    ) -> str:

        parts = []

        understood_request = understanding.get(
            "understood_request",
            ""
        )

        if understood_request:
            parts.append(
                understood_request
            )

        requirements = understanding.get(
            "requirements",
            []
        )

        for requirement in requirements:

            if not isinstance(
                requirement,
                dict
            ):
                continue

            subject = requirement.get(
                "subject"
            )

            target = requirement.get(
                "target"
            )

            intent = requirement.get(
                "intent"
            )

            description = requirement.get(
                "description"
            )

            if subject:
                parts.append(str(subject))

            if target:
                parts.append(str(target))

            if intent:
                parts.append(str(intent))

            if description:
                parts.append(
                    str(description)
                )

            details = requirement.get(
                "details",
                []
            )

            for detail in details:

                if isinstance(
                    detail,
                    dict
                ):

                    name = detail.get(
                        "name"
                    )

                    value = detail.get(
                        "value"
                    )

                    detail_description = (
                        detail.get(
                            "description"
                        )
                    )

                    if name:
                        parts.append(
                            str(name)
                        )

                    if value:
                        parts.append(
                            str(value)
                        )

                    if detail_description:
                        parts.append(
                            str(
                                detail_description
                            )
                        )

                elif isinstance(
                    detail,
                    str
                ):

                    parts.append(detail)

            conditions = requirement.get(
                "conditions",
                []
            )

            for condition in conditions:

                if condition:
                    parts.append(
                        str(condition)
                    )

            constraints = requirement.get(
                "constraints",
                []
            )

            for constraint in constraints:

                if constraint:
                    parts.append(
                        str(constraint)
                    )

        return " ".join(
            parts
        ).strip()

    # ========================================================
    # SEARCH KNOWLEDGE
    # ========================================================

    def retrieve(
        self,
        understanding: Dict[str, Any]
    ) -> Dict[str, Any]:

        query = self._build_query(
            understanding
        )

        if not query:

            return {
                "version": self.version,
                "query": "",
                "semantic": [],
                "syntax": [],
                "loot_tables": [],
                "entities": [],
                "items": [],
                "predicates": [],
                "tags": [],
                "scoreboards": []
            }

        results = self.retriever.search(
            query,
            limit=self.max_results
        )

        return {
            "version": self.version,
            "query": query,
            "semantic": results.get(
                "semantic",
                []
            ),
            "syntax": results.get(
                "syntax",
                []
            ),
            "loot_tables": results.get(
                "loot_tables",
                []
            ),
            "entities": results.get(
                "entities",
                []
            ),
            "items": results.get(
                "items",
                []
            ),
            "predicates": results.get(
                "predicates",
                []
            ),
            "tags": results.get(
                "tags",
                []
            ),
            "scoreboards": results.get(
                "scoreboards",
                []
            )
        }

    # ========================================================
    # FORMAT FOR PLANNER
    # ========================================================

    def build_planner_context(
        self,
        understanding: Dict[str, Any]
    ) -> Dict[str, Any]:

        knowledge = self.retrieve(
            understanding
        )

        requirements = (
            understanding.get(
                "requirements",
                []
            )
        )

        return {
            "minecraft": {
                "version": self.version,
                "edition": understanding.get(
                    "edition",
                    "Java"
                )
            },

            "user_request": understanding.get(
                "understood_request",
                ""
            ),

            "requirements": requirements,

            "knowledge": knowledge
        }


# ============================================================
# SIMPLE FUNCTION INTERFACE
# ============================================================

def retrieve_minecraft_context(
    understanding: Dict[str, Any],
    version="1.21.11",
    max_results=10
) -> Dict[str, Any]:

    context = MinecraftKnowledgeContext(
        version=version,
        max_results=max_results
    )

    return context.build_planner_context(
        understanding
    )