"""
ai/numeric_interpreter.py - Generic Natural-Language Numeric Interpretation (Step 17.2)

Provides deterministic semantic interpretation of natural-language numeric expressions
and property modifications into the Step 17.1 semantic contract (PropertyModification,
SemanticValue, SemanticNumericValue).

This layer is strictly Minecraft-independent:
- No command syntax generation.
- No effect amplifier calculations (e.g. "10 times faster" stays multiplier=10, NOT amplifier=9).
- No request-specific phrase hacks.
- Reusable for arbitrary semantic properties and numeric relationships.
"""

import re
from typing import Any, Dict, List, Optional, Tuple, Union

from ai.semantic_models import (
    PropertyModification,
    SemanticNumericValue,
    SemanticValue,
    SUPPORTED_OPERATIONS,
    SUPPORTED_VALUE_KINDS,
)


WORD_TO_NUMBER: Dict[str, Union[int, float]] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
}

STANDALONE_MULTIPLIERS: Dict[str, Union[int, float]] = {
    "twice": 2,
    "double": 2,
    "triple": 3,
    "quadruple": 4,
}

ADJECTIVE_TO_PROPERTY: Dict[str, Optional[str]] = {
    "faster": "speed",
    "fast": "speed",
    "slower": "speed",
    "slow": "speed",
    "stronger": None,  # Ambiguous / underspecified property
    "strong": None,
    "weaker": None,    # Ambiguous / underspecified property
    "weak": None,
    "tougher": None,
    "tough": None,
}

COMPARATIVE_ADJECTIVE_OPERATIONS: Dict[str, str] = {
    "faster": "add",
    "slower": "subtract",
    "higher": "add",
    "lower": "subtract",
    "stronger": "add",
    "weaker": "subtract",
    "tougher": "add",
    "more": "add",
    "less": "subtract",
    "greater": "add",
    "smaller": "subtract",
}

KNOWN_PROPERTY_SYNONYMS: Dict[str, str] = {
    "speed": "speed",
    "movement speed": "speed",
    "movement_speed": "speed",
    "attack damage": "attack_damage",
    "attack_damage": "attack_damage",
    "damage": "attack_damage",
    "health": "health",
    "max health": "health",
    "max_health": "health",
    "jump height": "jump_height",
    "jump_height": "jump_height",
    "gravity": "gravity",
    "fall damage": "fall_damage",
    "fall_damage": "fall_damage",
    "armor": "armor",
    "defense": "defense",
}

COMBAT_OR_EVENT_DAMAGE_PATTERNS = [
    r"\b(?:take|takes|taking|took|deal|deals|dealing|dealt|receive|receives|receiving|received|cause|causes|causing|caused|inflict|inflicts|inflicting|shares?)\s+(?:the\s+)?(?:same\s+)?damage\b",
    r"\bdamage\s+(?:taken|dealt|received|caused|inflicted|for\s+everyone|for\s+all)\b",
    r"\b(?:fall|drowning|fire|lava|poison|freeze|lightning|magic|explosion|void|starvation)\s+damage\b",
    r"\bimmune\s+to\b",
]

DESCRIPTIVE_OR_RELATIONAL_PATTERNS = [
    r"\b(?:shares?|sharing|shared|sync|synchronize|synchronizing|link|linked|linking)\b",
    r"\b(?:whenever|when\s+a\b|when\s+one\b|if\s+one\b|if\s+a\b|every\s+time|each\s+time)\b",
    r"\b(?:scoreboard|display|show|track)\b",
    r"\b(?:immune|immunity|resist|resistant)\s+to\b",
]


def is_combat_or_event_damage_context(text: str) -> bool:
    norm = text.lower()
    return any(re.search(pat, norm) for pat in COMBAT_OR_EVENT_DAMAGE_PATTERNS)


def is_descriptive_or_relational_context(text: str) -> bool:
    norm = text.lower()
    return any(re.search(pat, norm) for pat in DESCRIPTIVE_OR_RELATIONAL_PATTERNS)


def _load_known_entity_names() -> set:
    try:
        from knowledge_retriever import load_entity_knowledge
        entities = load_entity_knowledge()
        if isinstance(entities, list):
            return {
                ent["name"].lower()
                for ent in entities
                if isinstance(ent, dict) and "name" in ent
            }
    except Exception:
        pass
    return set()


_KNOWN_ENTITIES: Optional[set] = None


def get_known_entity_names() -> set:
    global _KNOWN_ENTITIES
    if _KNOWN_ENTITIES is None:
        _KNOWN_ENTITIES = _load_known_entity_names()
    return _KNOWN_ENTITIES


def _validate_not_boolean(value: Any) -> None:
    """Explicitly reject booleans from being treated as numeric or string values."""
    if isinstance(value, bool):
        raise ValueError("Semantic value cannot be a boolean.")


def _clean_number(token: str) -> Union[int, float]:
    """
    Parse a numeric token into an int or float, checking for malformed expressions.
    """
    token_str = token.strip().lower()

    # Reject malformed multi-dot patterns (e.g. 10.5.2)
    if re.search(r"\b\d+\.\d+\.\d+\b", token_str):
        raise ValueError(f"Malformed numeric expression with multiple decimal points: '{token}'")

    # Reject consecutive signs (e.g. ++5, --5)
    if re.search(r"(\+\+|--|\+-|-\+)", token_str):
        raise ValueError(f"Malformed numeric expression with consecutive signs: '{token}'")

    # Word number check
    if token_str in WORD_TO_NUMBER:
        return WORD_TO_NUMBER[token_str]

    try:
        val = float(token_str)
        return int(val) if val.is_integer() else val
    except ValueError:
        raise ValueError(f"Malformed or non-numeric expression: '{token}'")


class NumericSemanticInterpreter:
    """
    Interprets natural-language numeric expressions and property modifications
    into structured PropertyModification models without Minecraft command syntax.
    """

    def __init__(self):
        pass

    def interpret_value(self, raw_input: Any) -> SemanticValue:
        """
        Directly interpret a value, string, or number into a SemanticValue
        (multiplier, percentage, relative, absolute, or qualitative).
        """
        _validate_not_boolean(raw_input)

        if isinstance(raw_input, (int, float)):
            return SemanticNumericValue(kind="absolute", value=raw_input)

        if not isinstance(raw_input, str):
            raise ValueError(f"Cannot interpret value of type {type(raw_input).__name__}")

        text = raw_input.strip()
        if not text:
            raise ValueError("Cannot interpret empty value string.")

        self._check_malformed_syntax(text)

        # 1. Standalone multiplier word
        lower = text.lower()
        if lower in STANDALONE_MULTIPLIERS:
            return SemanticNumericValue(kind="multiplier", value=STANDALONE_MULTIPLIERS[lower])

        # 2. Pattern <num>x or <num> x
        m_x = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*[xX]", text)
        if m_x:
            num = _clean_number(m_x.group(1))
            return SemanticNumericValue(kind="multiplier", value=num)

        # 3. Pattern <num> times
        m_times = re.fullmatch(r"([a-zA-Z0-9\.\+-]+)\s+times", text, re.IGNORECASE)
        if m_times:
            num = _clean_number(m_times.group(1))
            return SemanticNumericValue(kind="multiplier", value=num)

        # 4. Pattern <num>% or <num> percent
        m_pct = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(?:%|percent|percentage)", text, re.IGNORECASE)
        if m_pct:
            num = _clean_number(m_pct.group(1))
            return SemanticNumericValue(kind="percentage", value=num, unit="%")

        # 5. Explicit signed number (+5 or -5)
        m_signed = re.fullmatch(r"([+-]\d+(?:\.\d+)?)", text)
        if m_signed:
            num = _clean_number(m_signed.group(1))
            return SemanticNumericValue(kind="relative", value=num)

        # 6. Plain number
        try:
            num = _clean_number(text)
            return SemanticNumericValue(kind="absolute", value=num)
        except ValueError:
            pass

        # 7. Word number plain
        if lower in WORD_TO_NUMBER:
            return SemanticNumericValue(kind="absolute", value=WORD_TO_NUMBER[lower])

        # 8. Qualitative descriptor
        return SemanticValue(kind="qualitative", value=text)

    def _check_malformed_syntax(self, text: str) -> None:
        """Reject obvious malformed numeric strings."""
        if re.search(r"\b\d+\.\d+\.\d+\b", text):
            raise ValueError(f"Malformed numeric expression with multiple decimal points: '{text}'")
        if re.search(r"(\+\+|--|\+-|-\+)", text):
            raise ValueError(f"Malformed numeric expression with consecutive signs: '{text}'")
        if re.search(r"(?:%%|\b(?:times\s+times|percent\s+percent)\b)", text, re.IGNORECASE):
            raise ValueError(f"Malformed numeric expression with repeated symbols/keywords: '{text}'")

    def interpret(
        self,
        text: str,
        default_property: Optional[str] = None,
        default_target: Optional[str] = None,
    ) -> PropertyModification:
        """
        Parse a single natural-language phrase into a PropertyModification.
        Handles missing properties, missing values, qualitative values, multipliers,
        percentages, relative updates, absolute sets, and ambiguous expressions.
        """
        _validate_not_boolean(text)
        if not isinstance(text, str):
            raise ValueError(f"Expected string input, got {type(text).__name__}")

        raw_text = text.strip()
        if not raw_text:
            raise ValueError("Input text cannot be empty.")

        self._check_malformed_syntax(raw_text)

        norm_text = raw_text.lower()

        # -------------------------------------------------------------
        # 1. Target & Property Extraction
        # -------------------------------------------------------------
        extracted_target = default_target
        extracted_property = default_property
        property_missing = False

        # Check target words (player, me, selectors, or generic entities)
        if re.search(r"\b(?:me|player|my)\b", norm_text):
            extracted_target = "player"
        elif re.search(r"\b@[apse](\[[^\]]*\])?\b", norm_text):
            m_sel = re.search(r"(@[apse](?:\[[^\]]*\])?)", norm_text)
            if m_sel:
                extracted_target = m_sel.group(1)
        else:
            # 1. Check grammatical patterns: e.g. "make (the|a|an|every|all) <target> (stronger|faster|...)"
            # or "make <target>'s <property>"
            m_target = re.search(
                r"\b(?:make|set|increase|decrease|reduce|change)\s+(?:the\s+|a\s+|an\s+|every\s+|all\s+)?([a-zA-Z_]+)(?:'s)?\s+",
                norm_text,
            )
            if m_target:
                candidate = m_target.group(1).lower()
                if candidate not in {"speed", "attack", "health", "armor", "damage", "me", "player", "my", "the", "a", "an", "all", "every"}:
                    extracted_target = candidate

            # 2. Check known entity names from Minecraft knowledge if still not extracted
            if not extracted_target:
                known_ents = get_known_entity_names()
                for ent in sorted(known_ents, key=len, reverse=True):
                    if re.search(rf"\b{re.escape(ent)}s?\b", norm_text):
                        extracted_target = ent
                        break

        # Check explicit property names in text first (sort longer multi-word keys first)
        for syn, canon in sorted(KNOWN_PROPERTY_SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True):
            if re.search(rf"\b{re.escape(syn)}\b", norm_text):
                # Disambiguate 'damage': do not map to attack_damage if referring to combat/event/hazard damage
                if syn == "damage":
                    if is_combat_or_event_damage_context(norm_text):
                        continue
                    # 'damage' without 'attack' is only an entity attribute if accompanied by an arithmetic/modification indicator
                    has_mod_indicator = bool(
                        re.search(r"\b(increase|boost|gain|raise|add|reduce|decrease|lower|drop|subtract|set|make|change|modify|adjust|alter|double|twice|triple)\b", norm_text)
                        or re.search(r"\bby\s+[+-]?\d+", norm_text)
                        or re.search(r"\bto\s+[+-]?\d+", norm_text)
                        or re.search(r"[+-]\d+", norm_text)
                        or re.search(r"\b(?:\d+\s*[xX]|\d+\s+times|\d+\s*%|\d+\s+percent)\b", norm_text)
                    )
                    if not has_mod_indicator:
                        continue
                extracted_property = canon
                property_missing = False
                break

        # If no explicit property, check adjective mappings (e.g. "faster" -> "speed", "stronger" -> missing)
        if not extracted_property:
            for adj, prop_name in ADJECTIVE_TO_PROPERTY.items():
                if re.search(rf"\b{adj}\b", norm_text):
                    if prop_name is None:
                        property_missing = True
                        extracted_property = None
                    else:
                        extracted_property = prop_name
                    break

        # Check generic property extraction via grammatical patterns:
        # e.g., "set <property> to", "increase <property> by", "reduce <property> by"
        if not extracted_property and not property_missing:
            m_gen = re.search(
                r"\b(?:set|increase|reduce|decrease|make|change)\s+(?:the\s+)?(?:[a-zA-Z_]+\s+)?([a-zA-Z_]+(?:\s+[a-zA-Z_]+)?)\s+(?:to|by|=)\b",
                norm_text,
            )
            if m_gen:
                candidate = m_gen.group(1).strip()
                if candidate not in {"me", "my", "the", "a", "an"}:
                    extracted_property = candidate.replace(" ", "_")

        # -------------------------------------------------------------
        # 2. Ambiguity Detection (e.g. "make me faster by 10")
        # -------------------------------------------------------------
        # Comparative adjective + "by <number>" without explicit multiplier/percent keywords:
        m_ambig = re.search(
            r"\b(faster|slower|stronger|weaker|higher|lower)\s+by\s+([+-]?\d+(?:\.\d+)?)\b(?!\s*(?:%|percent|times|[xX]))",
            norm_text,
        )
        if m_ambig:
            adj = m_ambig.group(1)
            raw_num = _clean_number(m_ambig.group(2))
            prop = ADJECTIVE_TO_PROPERTY.get(adj)
            missing_params = ["value"]
            if prop is None:
                missing_params.append("property")

            extra = {
                "ambiguous": True,
                "ambiguous_number": raw_num,
                "reason": (
                    f"Ambiguous numeric relationship: '{adj} by {raw_num}' does not specify "
                    "whether the value represents relative (+), multiplier (x), percentage (%), or absolute level."
                ),
            }
            if extracted_target:
                extra["target"] = extracted_target

            return PropertyModification(
                property=prop,
                operation="add" if adj in {"faster", "stronger", "higher"} else "subtract",
                value=None,
                missing=missing_params,
                source_text=raw_text,
                extra_metadata=extra,
            )

        # -------------------------------------------------------------
        # 3. Multiplier Recognition
        # -------------------------------------------------------------
        # Standalone multiplier words: twice, double, triple, quadruple
        for word, factor in STANDALONE_MULTIPLIERS.items():
            if re.search(rf"\b{word}\b", norm_text):
                missing_list = []
                if not extracted_property:
                    missing_list.append("property")
                extra = {}
                if extracted_target:
                    extra["target"] = extracted_target

                return PropertyModification(
                    property=extracted_property,
                    operation="multiply",
                    value=SemanticNumericValue(kind="multiplier", value=factor),
                    missing=missing_list,
                    source_text=raw_text,
                    extra_metadata=extra,
                )

        # Multiplier regex: <num>x or <num> x
        m_x = re.search(r"\b([+-]?\d+(?:\.\d+)?)\s*[xX]\b", raw_text)
        if m_x:
            num = _clean_number(m_x.group(1))
            missing_list = []
            if not extracted_property:
                missing_list.append("property")
            extra = {}
            if extracted_target:
                extra["target"] = extracted_target

            return PropertyModification(
                property=extracted_property,
                operation="multiply",
                value=SemanticNumericValue(kind="multiplier", value=num),
                missing=missing_list,
                source_text=raw_text,
                extra_metadata=extra,
            )

        # Multiplier regex: <num> times or <word> times
        m_times = re.search(r"\b([a-zA-Z0-9\.\+-]+)\s+times\b", norm_text)
        if m_times:
            num = _clean_number(m_times.group(1))
            missing_list = []
            if not extracted_property:
                missing_list.append("property")
            extra = {}
            if extracted_target:
                extra["target"] = extracted_target

            return PropertyModification(
                property=extracted_property,
                operation="multiply",
                value=SemanticNumericValue(kind="multiplier", value=num),
                missing=missing_list,
                source_text=raw_text,
                extra_metadata=extra,
            )

        # -------------------------------------------------------------
        # 4. Percentage Recognition
        # -------------------------------------------------------------
        m_pct = re.search(
            r"\b([+-]?\d+(?:\.\d+)?|[a-zA-Z]+)\s*(?:%|\bpercent\b|\bpercentage\b)",
            norm_text,
        )
        if m_pct:
            num = _clean_number(m_pct.group(1))
            # Determine operation (add vs subtract vs set)
            op = "add"
            if re.search(r"\b(?:reduce|decrease|lower|drop|subtract|less|down)\b", norm_text):
                op = "subtract"
            elif re.search(r"\b(?:set|to|=)\b", norm_text):
                op = "set"

            missing_list = []
            if not extracted_property:
                missing_list.append("property")
            extra = {}
            if extracted_target:
                extra["target"] = extracted_target

            return PropertyModification(
                property=extracted_property,
                operation=op,
                value=SemanticNumericValue(kind="percentage", value=num, unit="%"),
                missing=missing_list,
                source_text=raw_text,
                extra_metadata=extra,
            )

        # -------------------------------------------------------------
        # 5. Relative Numeric Values (increase/decrease by <num>, signed <num>)
        # -------------------------------------------------------------
        # 5a. Comparative Numeric Expressions (<number> faster / <number> slower)
        # e.g., "5 faster", "10 slower", "make me 5 faster", "make zombie 5 stronger"
        m_comp = re.search(
            r"\b([+-]?\d+(?:\.\d+)?|[a-zA-Z]+)\s*(?:(?:points?|levels?|units?|blocks?)\s+)?(faster|slower|higher|lower|stronger|weaker|tougher|more|less|greater|smaller)\b(?!\s*(?:%|percent|percentage|times|[xX]))",
            norm_text,
        )
        if m_comp:
            token = m_comp.group(1).lower()
            adj = m_comp.group(2).lower()
            if re.match(r"^[+-]?\d+(?:\.\d+)?$", token) or token in WORD_TO_NUMBER:
                num = _clean_number(token)
                op = COMPARATIVE_ADJECTIVE_OPERATIONS.get(adj, "add")
                prop = extracted_property or ADJECTIVE_TO_PROPERTY.get(adj)

                missing_list = []
                if not prop:
                    missing_list.append("property")
                extra = {}
                if extracted_target:
                    extra["target"] = extracted_target

                return PropertyModification(
                    property=prop,
                    operation=op,
                    value=SemanticNumericValue(kind="relative", value=num),
                    missing=missing_list,
                    source_text=raw_text,
                    extra_metadata=extra,
                )

        # 5b. Verb-based relative modifications (increase/decrease by <num>, signed <num>)
        m_rel = re.search(
            r"\b(increase|boost|gain|raise|add|reduce|decrease|lower|drop|subtract|change|modify|adjust|alter)\b.*?\b(?:by\s+)?([+-]?\d+(?:\.\d+)?)\b(?!\s*(?:%|percent|percentage|times|[xX]))",
            norm_text,
        )
        if m_rel:
            verb = m_rel.group(1)
            num = _clean_number(m_rel.group(2))

            missing_list = []
            if not extracted_property:
                missing_list.append("property")
            extra = {}
            if extracted_target:
                extra["target"] = extracted_target

            # Ambiguous operation verbs: cannot determine whether relative increase, multiplier, percentage, or set
            if verb in {"change", "modify", "adjust", "alter"}:
                missing_list.append("operation")
                extra["ambiguous_operation"] = True
                extra["reason"] = f"Operation unspecified: cannot determine how '{verb} by {num}' modifies {extracted_property or 'the property'}."
                return PropertyModification(
                    property=extracted_property,
                    operation=None,
                    value=SemanticNumericValue(kind="relative", value=num),
                    missing=missing_list,
                    source_text=raw_text,
                    extra_metadata=extra,
                )

            op = "subtract" if verb in {"reduce", "decrease", "lower", "drop", "subtract"} else "add"

            return PropertyModification(
                property=extracted_property,
                operation=op,
                value=SemanticNumericValue(kind="relative", value=num),
                missing=missing_list,
                source_text=raw_text,
                extra_metadata=extra,
            )

        # Standalone "by <num>" with sign or relative context
        m_by = re.search(r"\bby\s+([+-]?\d+(?:\.\d+)?)\b(?!\s*(?:%|percent|percentage|times|[xX]))", norm_text)
        if m_by:
            num = _clean_number(m_by.group(1))
            op = "subtract" if num < 0 else "add"
            missing_list = []
            if not extracted_property:
                missing_list.append("property")
            extra = {}
            if extracted_target:
                extra["target"] = extracted_target

            return PropertyModification(
                property=extracted_property,
                operation=op,
                value=SemanticNumericValue(kind="relative", value=num),
                missing=missing_list,
                source_text=raw_text,
                extra_metadata=extra,
            )

        # -------------------------------------------------------------
        # 6. Absolute Numeric Values (set to <num>, <prop> = <num>, make <prop> <num>)
        # -------------------------------------------------------------
        # e.g. "set speed to 10", "set to 10", "attack damage = 20"
        m_set = re.search(
            r"\b(?:set|make|change)?\b.*?(?:to|=)\s*([+-]?\d+(?:\.\d+)?)\b(?!\s*(?:%|percent|percentage|times|[xX]))",
            norm_text,
        )
        if m_set:
            num = _clean_number(m_set.group(1))
            missing_list = []
            if not extracted_property:
                missing_list.append("property")
            extra = {}
            if extracted_target:
                extra["target"] = extracted_target

            return PropertyModification(
                property=extracted_property,
                operation="set",
                value=SemanticNumericValue(kind="absolute", value=num),
                missing=missing_list,
                source_text=raw_text,
                extra_metadata=extra,
            )

        # e.g. "make speed 10", "make <entity> attack damage 10"
        m_make_num = re.search(
            r"\bmake\s+.*?\b([+-]?\d+(?:\.\d+)?)\b(?!\s*(?:%|percent|percentage|times|[xX]))",
            norm_text,
        )
        if m_make_num and extracted_property:
            num = _clean_number(m_make_num.group(1))
            extra = {}
            if extracted_target:
                extra["target"] = extracted_target

            return PropertyModification(
                property=extracted_property,
                operation="set",
                value=SemanticNumericValue(kind="absolute", value=num),
                missing=[],
                source_text=raw_text,
                extra_metadata=extra,
            )

        # -------------------------------------------------------------
        # 7. Qualitative Values (no numeric magnitude)
        # -------------------------------------------------------------
        for adj, prop_name in ADJECTIVE_TO_PROPERTY.items():
            if re.search(rf"\b{adj}\b", norm_text):
                missing_list = []
                if prop_name is None:
                    missing_list.append("property")
                extra = {}
                if extracted_target:
                    extra["target"] = extracted_target

                # Qualitative requests do not have arithmetic operations; preserve operation as None
                return PropertyModification(
                    property=prop_name,
                    operation=None,
                    value=SemanticValue(kind="qualitative", value=adj),
                    missing=missing_list,
                    source_text=raw_text,
                    extra_metadata=extra,
                )

        # -------------------------------------------------------------
        # 8. Missing Numeric Values (operation + property, but missing number)
        # -------------------------------------------------------------
        # e.g. "increase speed", "increase attack damage", "set health", "reduce damage"
        if extracted_property:
            op = None
            if re.search(r"\b(?:increase|boost|gain|raise|add|up)\b", norm_text):
                op = "add"
            elif re.search(r"\b(?:reduce|decrease|lower|drop|subtract)\b", norm_text):
                op = "subtract"
            elif re.search(r"\b(?:set|make)\b", norm_text):
                op = "set"

            if op is not None:
                extra = {}
                if extracted_target:
                    extra["target"] = extracted_target

                return PropertyModification(
                    property=extracted_property,
                    operation=op,
                    value=None,
                    missing=["value"],
                    source_text=raw_text,
                    extra_metadata=extra,
                )

        # -------------------------------------------------------------
        # 9. Fallback / Minimal Representation
        # -------------------------------------------------------------
        missing_list = []
        if not extracted_property:
            missing_list.append("property")
        missing_list.append("operation")
        missing_list.append("value")

        return PropertyModification(
            property=extracted_property,
            operation=None,
            value=None,
            missing=missing_list,
            source_text=raw_text,
            extra_metadata={"target": extracted_target} if extracted_target else {},
        )

    def interpret_compound(self, text: str) -> Dict[str, Any]:
        """
        Split a compound request (e.g. joined by 'and', 'then', ';') into
        recognized PropertyModification items while preserving other non-property requirements.
        """
        _validate_not_boolean(text)
        if not isinstance(text, str):
            raise ValueError(f"Expected string input, got {type(text).__name__}")

        raw_text = text.strip()
        if not raw_text:
            raise ValueError("Input text cannot be empty.")

        clauses = [
            c.strip()
            for c in re.split(r"\s+(?:and|then|also|, and)\s+|;\s*", raw_text, flags=re.IGNORECASE)
            if c.strip()
        ]

        modifications: List[PropertyModification] = []
        other_requirements: List[str] = []

        for clause in clauses:
            norm_c = clause.lower()
            # Determine if this clause looks like a property modification
            is_property_clause = False

            # Check if this clause is relational or descriptive gameplay (e.g. "players share health")
            # without an explicit numeric assignment
            has_explicit_number = bool(
                re.search(r"\b(?:by|to|=)\s*[+-]?\d+(?:\.\d+)?\b", norm_c)
                or re.search(r"[+-]\d+(?:\.\d+)?\b", norm_c)
                or re.search(r"\b(?:\d+\s*[xX]|\d+\s+times|\d+\s*%|\d+\s+percent)\b", norm_c)
            )
            has_multiplier = any(re.search(rf"\b{m}\b", norm_c) for m in STANDALONE_MULTIPLIERS)
            has_qualitative = any(re.search(rf"\b{adj}\b", norm_c) for adj in ADJECTIVE_TO_PROPERTY)
            has_concrete_mod = has_explicit_number or has_multiplier or has_qualitative

            if not has_concrete_mod and is_descriptive_or_relational_context(norm_c):
                # Pure relational, conditional event, or descriptive clause without numbers
                is_property_clause = False
            else:
                for adj in ADJECTIVE_TO_PROPERTY:
                    if re.search(rf"\b{adj}\b", norm_c):
                        is_property_clause = True
                        break
                if not is_property_clause:
                    for mult in STANDALONE_MULTIPLIERS:
                        if re.search(rf"\b{mult}\b", norm_c):
                            is_property_clause = True
                            break
                if not is_property_clause:
                    if re.search(r"\b(?:\d+\s*[xX]|\d+\s+times|\d+\s*%|\d+\s+percent)\b", norm_c):
                        is_property_clause = True
                if not is_property_clause:
                    # Require an arithmetic or modification verb/indicator to treat a property mention as a modification
                    has_arithmetic_indicator = bool(
                        re.search(r"\b(increase|boost|gain|raise|add|reduce|decrease|lower|drop|subtract|set|make|change|modify|adjust|alter)\b", norm_c)
                        or has_explicit_number
                    )
                    if has_arithmetic_indicator:
                        for prop in sorted(KNOWN_PROPERTY_SYNONYMS.keys(), key=len, reverse=True):
                            if re.search(rf"\b{re.escape(prop)}\b", norm_c):
                                if prop == "damage" and is_combat_or_event_damage_context(norm_c):
                                    continue
                                is_property_clause = True
                                break

            if is_property_clause:
                try:
                    mod = self.interpret(clause)
                    # A genuine property modification must have an operation, a value, or an explicit ambiguous modifier.
                    # If BOTH operation is None and value is None, it is a descriptive or relational statement, NOT a property modification.
                    if mod.operation is None and mod.value is None and not mod.extra_metadata.get("ambiguous"):
                        other_requirements.append(clause)
                    else:
                        modifications.append(mod)
                except Exception:
                    other_requirements.append(clause)
            else:
                other_requirements.append(clause)

        return {
            "source_text": raw_text,
            "modifications": modifications,
            "other_requirements": other_requirements,
        }


def interpret_numeric_expression(
    text: str,
    default_property: Optional[str] = None,
    default_target: Optional[str] = None,
) -> PropertyModification:
    """Convenience function for interpreting a numeric expression."""
    interpreter = NumericSemanticInterpreter()
    return interpreter.interpret(
        text, default_property=default_property, default_target=default_target
    )


def extract_property_modifications(text: str) -> List[PropertyModification]:
    """Convenience function extracting all property modifications from a text."""
    interpreter = NumericSemanticInterpreter()
    compound = interpreter.interpret_compound(text)
    return compound["modifications"]
