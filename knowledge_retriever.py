import json
import re
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "1.21.11"

BASE_DIR = Path(__file__).resolve().parent

COMMANDS_FILE = (
    BASE_DIR
    / "knowledge"
    / "commands"
    / "java"
    / VERSION
    / "commands.jsonl"
)

SEMANTIC_FILE = (
    BASE_DIR
    / "knowledge"
    / "descriptions"
    / "semantic_commands.json"
)

LOOT_TABLES_DIR = (
    BASE_DIR
    / "knowledge"
    / "loot_tables"
    / "java"
    / VERSION
    / "tables"
)

ENTITIES_FILE = (
    BASE_DIR
    / "knowledge"
    / "entities"
    / "java"
    / VERSION
    / "entities.json"
)

ITEMS_FILE = (
    BASE_DIR
    / "knowledge"
    / "items"
    / "java"
    / VERSION
    / "items.json"
)

PREDICATES_FILE = (
    BASE_DIR
    / "knowledge"
    / "predicates"
    / "java"
    / VERSION
    / "predicates.json"
)

TAGS_FILE = (
    BASE_DIR
    / "knowledge"
    / "tags"
    / "java"
    / VERSION
    / "function_tags.json"
)


# ============================================================
# BASIC TOKENIZATION AND MORPHOLOGY
# ============================================================

def word_variants(word: str) -> set:
    word = word.lower()
    variants = {word}

    if word.endswith("ies") and len(word) > 4:
        variants.add(word[:-3] + "y")
        variants.add(word[:-1])
    elif word.endswith("ves") and len(word) > 4:
        variants.add(word[:-3] + "f")
        variants.add(word[:-3] + "fe")
    elif word.endswith(("sses", "shes", "ches", "xes")) and len(word) > 4:
        variants.add(word[:-2])
    elif word.endswith("oes") and len(word) > 4:
        variants.add(word[:-2])
        variants.add(word[:-1])
    elif word.endswith("s") and not word.endswith("ss") and len(word) > 2:
        variants.add(word[:-1])

    return variants


def tokenize(text):
    if not text:
        return set()

    raw_tokens = set(
        re.findall(
            r"[a-z0-9_]+",
            str(text).lower()
        )
    )

    expanded = set()
    for token in raw_tokens:
        expanded.update(word_variants(token))

    return expanded


# ============================================================
# LOAD COMMAND SYNTAX KNOWLEDGE
# ============================================================

def load_syntax_knowledge():

    records = []

    if not COMMANDS_FILE.exists():
        return records

    with open(
        COMMANDS_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:

            line = line.strip()

            if line:
                records.append(
                    json.loads(line)
                )

    return records


# ============================================================
# LOAD SEMANTIC COMMAND KNOWLEDGE
# ============================================================

def load_semantic_knowledge():

    if not SEMANTIC_FILE.exists():
        return {}

    with open(
        SEMANTIC_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    return {
        command["command"]: command
        for command in data.get("commands", [])
    }


# ============================================================
# LOAD LOOT TABLE KNOWLEDGE
# ============================================================

def load_loot_table_knowledge():

    tables = []

    if not LOOT_TABLES_DIR.exists():
        return tables

    for file_path in LOOT_TABLES_DIR.rglob("*.json"):

        # Ignore metadata files.
        if file_path.name in {"_list.json", "_all.json"}:
            continue

        try:

            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

            relative_path = file_path.relative_to(
                LOOT_TABLES_DIR
            ).as_posix()

            tables.append(
                {
                    "version": VERSION,
                    "edition": "Java",
                    "path": relative_path,
                    "type": data.get("type"),
                    "pool_count": len(
                        data.get("pools", [])
                    ),
                    "data": data
                }
            )

        except Exception:
            continue

    return tables


# ============================================================
# LOAD ENTITY KNOWLEDGE
# ============================================================

def load_entity_knowledge():

    if ENTITIES_FILE.exists():
        with open(ENTITIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    # Check root knowledge/entities/entities.json
    root_entities_file = BASE_DIR / "knowledge" / "entities" / "entities.json"
    if root_entities_file.exists():
        with open(root_entities_file, "r", encoding="utf-8") as f:
            return json.load(f)

    # Fallback to generated reports
    fallback_file = BASE_DIR / "generated" / "reports" / "registries.json"
    if fallback_file.exists():
        with open(fallback_file, "r", encoding="utf-8") as f:
            regs = json.load(f)

        entity_types = regs.get("minecraft:entity_type", {}).get("entries", {})
        entities = []

        for full_id in entity_types:
            name = full_id.split(":", 1)[1] if ":" in full_id else full_id
            disp = name.replace("_", " ").title()
            lt_rel = f"entities/{name}.json"
            has_lt = (LOOT_TABLES_DIR / lt_rel).exists()

            entities.append({
                "id": full_id,
                "name": name,
                "display_name": disp,
                "loot_table": lt_rel if has_lt else None,
                "version": VERSION,
                "edition": "Java"
            })

        return entities

    return []


# ============================================================
# LOAD ITEM KNOWLEDGE
# ============================================================

def load_item_knowledge():

    if ITEMS_FILE.exists():
        with open(ITEMS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    # Check root knowledge/items/items.json
    root_items_file = BASE_DIR / "knowledge" / "items" / "items.json"
    if root_items_file.exists():
        with open(root_items_file, "r", encoding="utf-8") as f:
            return json.load(f)

    # Fallback to generated reports
    fallback_file = BASE_DIR / "generated" / "reports" / "items.json"
    if fallback_file.exists():
        with open(fallback_file, "r", encoding="utf-8") as f:
            raw_items = json.load(f)

        items = []

        for full_id in raw_items:
            name = full_id.split(":", 1)[1] if ":" in full_id else full_id
            disp = name.replace("_", " ").title()

            aliases = [name]
            if name.endswith("_ingot"):
                aliases.append(name[:-6])
            elif name.endswith("_dust"):
                aliases.append(name[:-5])
            elif name.endswith("_shard"):
                aliases.append(name[:-6])
            elif name == "lapis_lazuli":
                aliases.append("lapis")

            items.append({
                "id": full_id,
                "name": name,
                "display_name": disp,
                "aliases": sorted(list(set(aliases))),
                "version": VERSION,
                "edition": "Java"
            })

        return items

    return []


# ============================================================
# LOAD PREDICATE KNOWLEDGE
# ============================================================

def load_predicate_knowledge():
    if PREDICATES_FILE.exists():
        try:
            with open(PREDICATES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


# ============================================================
# LOAD FUNCTION TAG KNOWLEDGE
# ============================================================

def load_tag_knowledge():
    if TAGS_FILE.exists():
        try:
            with open(TAGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


# ============================================================
# SEARCH EXACT COMMAND
# ============================================================

def search_syntax(records, command):

    command = command.lower().strip()

    return [
        record
        for record in records
        if record.get("command", "").lower() == command
    ]


# ============================================================
# SEARCH EXACT SEMANTIC COMMAND
# ============================================================

def search_semantic(semantic_data, command):

    command = command.lower().strip()

    return semantic_data.get(command)


# ============================================================
# SCORE SEMANTIC COMMAND RESULT
# ============================================================

def score_semantic_result(query, command_data):

    query_tokens = tokenize(query)

    searchable_text = []

    searchable_text.append(
        command_data.get("command", "")
    )

    searchable_text.append(
        command_data.get("description", "")
    )

    purposes = command_data.get(
        "purpose",
        []
    )

    if isinstance(purposes, list):
        searchable_text.extend(purposes)
    else:
        searchable_text.append(
            str(purposes)
        )

    subcommands = command_data.get(
        "important_subcommands",
        []
    )

    if isinstance(subcommands, list):
        searchable_text.extend(subcommands)
    else:
        searchable_text.append(
            str(subcommands)
        )

    text = " ".join(
        str(value)
        for value in searchable_text
    )

    result_tokens = tokenize(text)

    overlap = query_tokens.intersection(
        result_tokens
    )

    if not overlap:
        return 0

    score = len(overlap)

    command_name = command_data.get(
        "command",
        ""
    ).lower()

    if command_name in query_tokens:
        score += 5

    return score


# ============================================================
# SEARCH ALL SEMANTIC COMMAND KNOWLEDGE
# ============================================================

def search_semantic_relevant(
    semantic_data,
    query,
    limit=10
):

    results = []

    for command, data in semantic_data.items():

        score = score_semantic_result(
            query,
            data
        )

        if score > 0:

            results.append(
                {
                    "command": command,
                    "score": score,
                    "data": data
                }
            )

    results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return results[:limit]


# ============================================================
# SEARCH COMMAND SYNTAX RELEVANT TO QUERY
# ============================================================

def search_syntax_relevant(
    records,
    query,
    limit=20
):

    query_tokens = tokenize(query)

    scored_results = []

    for record in records:

        command = record.get(
            "command",
            ""
        )

        syntax = record.get(
            "syntax",
            ""
        )

        tokens = record.get(
            "tokens",
            []
        )

        searchable_text = " ".join(
            [
                str(command),
                str(syntax),
                " ".join(
                    str(token)
                    for token in tokens
                )
            ]
        )

        record_tokens = tokenize(
            searchable_text
        )

        overlap = query_tokens.intersection(
            record_tokens
        )

        if not overlap:
            continue

        score = len(overlap)

        if command.lower() in query_tokens:
            score += 5

        scored_results.append(
            {
                "command": command,
                "syntax": syntax,
                "arguments": record.get(
                    "arguments",
                    []
                ),
                "permissions": record.get(
                    "permissions",
                    []
                ),
                "score": score
            }
        )

    scored_results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return scored_results[:limit]


# ============================================================
# CREATE SEARCHABLE TEXT FOR LOOT TABLE
# ============================================================

def loot_table_search_text(table):

    path = table.get(
        "path",
        ""
    )

    data = table.get(
        "data",
        {}
    )

    searchable_parts = [
        path,
        path.replace("/", " "),
        path.replace(".json", ""),
        data.get("type", "")
    ]

    for pool in data.get("pools", []):

        searchable_parts.append(
            str(pool.get("rolls", ""))
        )

        searchable_parts.append(
            str(pool.get("bonus_rolls", ""))
        )

        for entry in pool.get(
            "entries",
            []
        ):

            entry_type = entry.get(
                "type",
                ""
            )

            entry_name = entry.get(
                "name",
                ""
            )

            searchable_parts.append(
                str(entry_type)
            )

            searchable_parts.append(
                str(entry_name)
            )

            for function in entry.get(
                "functions",
                []
            ):

                searchable_parts.append(
                    str(function.get(
                        "function",
                        ""
                    ))
                )

                searchable_parts.append(
                    str(function)
                )

            for condition in entry.get(
                "conditions",
                []
            ):

                searchable_parts.append(
                    str(condition)
                )

    return " ".join(
        str(value)
        for value in searchable_parts
    )

def summarize_loot_table(table):

    data = table.get(
        "data",
        {}
    )

    summary = {
        "path": table.get("path", ""),
        "type": data.get("type"),
        "pool_count": len(
            data.get("pools", [])
        ),
        "entries": [],
        "functions": [],
        "conditions": []
    }

    for pool in data.get("pools", []):

        for entry in pool.get(
            "entries",
            []
        ):

            entry_info = {
                "type": entry.get("type"),
                "name": entry.get("name")
            }

            if entry_info["type"] or entry_info["name"]:
                summary["entries"].append(
                    entry_info
                )

            for function in entry.get(
                "functions",
                []
            ):

                summary["functions"].append(
                    function
                )

            for condition in entry.get(
                "conditions",
                []
            ):

                summary["conditions"].append(
                    condition
                )

    return summary

# ============================================================
# SCORE LOOT TABLE
# ============================================================

def score_loot_table(query, table):

    query_tokens = tokenize(query)

    path = table.get(
        "path",
        ""
    ).lower()

    path_tokens = tokenize(path)

    searchable_text = loot_table_search_text(
        table
    )

    result_tokens = tokenize(
        searchable_text
    )

    overlap = query_tokens.intersection(
        result_tokens
    )

    score = len(overlap)

    # --------------------------------------------------------
    # Detect loot-related query
    # --------------------------------------------------------

    loot_words = {
        "drop",
        "drops",
        "loot",
        "loot_table",
        "loottable",
        "reward",
        "rewards"
    }

    is_loot_query = bool(
        query_tokens.intersection(
            loot_words
        )
    )

    # --------------------------------------------------------
    # Path matching
    # --------------------------------------------------------

    path_overlap = query_tokens.intersection(
        path_tokens
    )

    score += len(path_overlap) * 4

    # --------------------------------------------------------
    # Exact filename matching
    # --------------------------------------------------------

    filename = Path(path).stem.lower()

    if filename in query_tokens:
        score += 10

    # --------------------------------------------------------
    # Canonical entity loot table
    # --------------------------------------------------------

    if path.startswith("entities/"):

        entity_name = filename

        if entity_name in query_tokens:

            # Strong preference for the actual
            # entities/<entity>.json table.
            score += 25

    # --------------------------------------------------------
    # Penalize nested/non-canonical tables
    # --------------------------------------------------------

    if filename in query_tokens:

        if not path.startswith("entities/"):

            # Example:
            # charged_creeper/zombie.json
            #
            # This contains "zombie" in the filename,
            # but it is NOT the normal zombie loot table.

            score -= 12

    # --------------------------------------------------------
    # Loot wording
    # --------------------------------------------------------

    if is_loot_query:
        score += 2

    return max(score, 0)
    
# ============================================================
# SEARCH LOOT TABLES RELEVANT TO QUERY
# ============================================================

def search_loot_tables_relevant(
    loot_tables,
    query,
    limit=10
):

    results = []

    for table in loot_tables:

        score = score_loot_table(
            query,
            table
        )

        if score <= 0:
            continue

        summary = summarize_loot_table(
            table
        )

        summary["score"] = score
        summary["data"] = table["data"]

        results.append(
            summary
        )

    # --------------------------------------------------------
    # Sort by relevance
    # --------------------------------------------------------

    results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    if not results:
        return []

    # --------------------------------------------------------
    # Remove very weak results
    #
    # Keep results that are at least 25% as relevant
    # as the best result.
    # --------------------------------------------------------

    best_score = results[0]["score"]

    minimum_score = max(
        3,
        best_score * 0.25
    )

    filtered_results = [
        result
        for result in results
        if result["score"] >= minimum_score
    ]

    return filtered_results[:limit]


# ============================================================
# SCORE ENTITY RELEVANCE
# ============================================================

def score_entity(query, entity):

    query_tokens = tokenize(query)
    query_lower = query.lower()

    name = entity.get("name", "").lower()
    entity_id = entity.get("id", "").lower()
    entity_tokens = set(name.split("_"))

    score = 0
    multi_name = name.replace("_", " ")

    if len(entity_tokens) > 1 and multi_name in query_lower:
        score += 40
    elif name in query_tokens or entity_id in query_tokens:
        score += 30

    overlap = query_tokens.intersection(entity_tokens)
    score += len(overlap) * 5

    unmatched = entity_tokens - query_tokens
    score -= len(unmatched) * 10

    return max(score, 0)


# ============================================================
# SEARCH ENTITIES RELEVANT TO QUERY
# ============================================================

def search_entities_relevant(
    entities,
    query,
    limit=10
):

    results = []

    for entity in entities:

        score = score_entity(
            query,
            entity
        )

        if score <= 0:
            continue

        entry = dict(entity)
        entry["score"] = score

        results.append(entry)

    results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    if not results:
        return []

    best_score = results[0]["score"]
    minimum_score = max(
        10,
        best_score * 0.5
    )

    filtered_results = [
        result
        for result in results
        if result["score"] >= minimum_score
    ]

    return filtered_results[:limit]


# ============================================================
# SCORE ITEM RELEVANCE
# ============================================================

def score_item(query, item):

    query_tokens = tokenize(query)
    query_lower = query.lower()

    name = item.get("name", "").lower()
    item_id = item.get("id", "").lower()
    item_tokens = set(name.split("_"))
    aliases = [a.lower() for a in item.get("aliases", [])]

    score = 0
    multi_name = name.replace("_", " ")
    matched_exact = False

    if len(item_tokens) > 1 and multi_name in query_lower:
        score += 40
        matched_exact = True
    elif name in query_tokens or item_id in query_tokens:
        score += 30
        matched_exact = True
    else:
        for alias in aliases:
            if alias in query_tokens:
                score += 25
                matched_exact = True
                break

    overlap = query_tokens.intersection(item_tokens)
    score += len(overlap) * 5

    if not matched_exact:
        unmatched = item_tokens - query_tokens
        score -= len(unmatched) * 8

    return max(score, 0)


# ============================================================
# SEARCH ITEMS RELEVANT TO QUERY
# ============================================================

def search_items_relevant(
    items,
    query,
    limit=10
):

    results = []

    for item in items:

        score = score_item(
            query,
            item
        )

        if score <= 0:
            continue

        entry = dict(item)
        entry["score"] = score

        results.append(entry)

    results.sort(
        key=lambda it: it["score"],
        reverse=True
    )

    if not results:
        return []

    best_score = results[0]["score"]
    minimum_score = max(
        15,
        best_score * 0.5
    )

    filtered_results = [
        result
        for result in results
        if result["score"] >= minimum_score
    ]

    return filtered_results[:limit]


# ============================================================
# SCORE PREDICATE RELEVANCE
# ============================================================

def score_predicate(query, predicate):
    query_tokens = tokenize(query)
    query_lower = query.lower()

    name = predicate.get("name", "").lower()
    cond = predicate.get("condition", "").lower()
    desc = predicate.get("description", "").lower()

    score = 0
    if name in query_tokens or cond in query_tokens:
        score += 40
    if name.replace("_", " ") in query_lower:
        score += 30

    name_tokens = set(name.split("_"))
    overlap = query_tokens.intersection(name_tokens)
    score += len(overlap) * 15

    desc_tokens = tokenize(desc)
    desc_overlap = query_tokens.intersection(desc_tokens)
    score += len(desc_overlap) * 5

    if "predicate" in query_tokens or "condition" in query_tokens:
        score += 10

    return score


# ============================================================
# SEARCH PREDICATES RELEVANT TO QUERY
# ============================================================

def search_predicates_relevant(
    predicates,
    query,
    limit=5
):
    results = []

    for predicate in predicates:
        score = score_predicate(query, predicate)
        if score <= 0:
            continue

        entry = dict(predicate)
        entry["score"] = score
        results.append(entry)

    results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return results[:limit]


# ============================================================
# SCORE FUNCTION TAG RESULT
# ============================================================

def score_tag(
    query,
    tag_info
):
    query_tokens = tokenize(query)
    query_lower = query.lower()

    name = tag_info.get("name", "").lower()
    full_tag = tag_info.get("tag", "").lower()
    desc = tag_info.get("description", "").lower()

    score = 0
    if name in query_tokens or full_tag in query_tokens:
        score += 50
    if name in query_lower:
        score += 30

    desc_tokens = tokenize(desc)
    overlap = query_tokens.intersection(desc_tokens)
    score += len(overlap) * 5

    if any(t in query_tokens for t in ["tag", "loop", "tick", "load", "every", "polling"]):
        score += 20

    return score


# ============================================================
# SEARCH FUNCTION TAGS RELEVANT TO QUERY
# ============================================================

def search_tags_relevant(
    tags,
    query,
    limit=5
):
    results = []

    for tag_info in tags:
        score = score_tag(query, tag_info)
        if score <= 0:
            continue

        entry = dict(tag_info)
        entry["score"] = score
        results.append(entry)

    results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return results[:limit]


# ============================================================
# MINECRAFT KNOWLEDGE RETRIEVER
# ============================================================

class MinecraftKnowledgeRetriever:

    def __init__(
        self,
        version=VERSION
    ):

        self.version = version

        self.syntax_records = (
            load_syntax_knowledge()
        )

        self.semantic_data = (
            load_semantic_knowledge()
        )

        self.loot_tables = (
            load_loot_table_knowledge()
        )

        self.entities = (
            load_entity_knowledge()
        )

        self.items = (
            load_item_knowledge()
        )

        self.predicates = (
            load_predicate_knowledge()
        )

        self.tags = (
            load_tag_knowledge()
        )

    # --------------------------------------------------------
    # GENERAL SEARCH
    # --------------------------------------------------------

    def search(
        self,
        query,
        limit=10
    ):

        semantic_results = (
            search_semantic_relevant(
                self.semantic_data,
                query,
                limit
            )
        )

        syntax_results = (
            search_syntax_relevant(
                self.syntax_records,
                query,
                limit
            )
        )

        loot_results = (
            search_loot_tables_relevant(
                self.loot_tables,
                query,
                limit
            )
        )

        entity_results = (
            search_entities_relevant(
                self.entities,
                query,
                limit
            )
        )

        item_results = (
            search_items_relevant(
                self.items,
                query,
                limit
            )
        )

        predicate_results = (
            search_predicates_relevant(
                self.predicates,
                query,
                limit
            )
        )

        tag_results = (
            search_tags_relevant(
                self.tags,
                query,
                limit
            )
        )

        return {
            "version": self.version,
            "semantic": semantic_results,
            "syntax": syntax_results,
            "loot_tables": loot_results,
            "entities": entity_results,
            "items": item_results,
            "predicates": predicate_results,
            "tags": tag_results
        }

    # --------------------------------------------------------
    # EXACT COMMAND SEARCH
    # --------------------------------------------------------

    def search_command(
        self,
        command
    ):

        if command.startswith("/"):
            command = command[1:]

        syntax_results = search_syntax(
            self.syntax_records,
            command
        )

        semantic_result = search_semantic(
            self.semantic_data,
            command
        )

        return {
            "version": self.version,
            "command": command,
            "semantic": semantic_result,
            "syntax": syntax_results
        }


# ============================================================
# DISPLAY KNOWLEDGE
# ============================================================

def display_knowledge(
    syntax_results,
    semantic_result
):

    print()
    print("=" * 60)
    print("MINECRAFT KNOWLEDGE")
    print("=" * 60)

    # --------------------------------------------------------
    # Semantic information
    # --------------------------------------------------------

    if semantic_result:

        print()
        print("DESCRIPTION:")

        print(
            semantic_result.get(
                "description",
                "N/A"
            )
        )

        purposes = semantic_result.get(
            "purpose",
            []
        )

        if purposes:

            print()
            print("PURPOSE:")

            for purpose in purposes:

                print(
                    f"  - {purpose}"
                )

        subcommands = semantic_result.get(
            "important_subcommands",
            []
        )

        if subcommands:

            print()
            print(
                "IMPORTANT SUBCOMMANDS:"
            )

            print(
                "  "
                + ", ".join(subcommands)
            )

    else:

        print()
        print(
            "No semantic information found."
        )

    # --------------------------------------------------------
    # Syntax information
    # --------------------------------------------------------

    print()
    print(
        f"SYNTAX RECORDS: "
        f"{len(syntax_results)}"
    )

    if syntax_results:

        print()

        for record in syntax_results:

            print(
                "  "
                + record["syntax"]
            )

    print()
    print("=" * 60)
    print()


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Loading Minecraft knowledge..."
    )

    retriever = MinecraftKnowledgeRetriever()

    print(
        f"Loaded "
        f"{len(retriever.syntax_records)} "
        f"syntax records."
    )

    print(
        f"Loaded "
        f"{len(retriever.semantic_data)} "
        f"semantic commands."
    )

    print(
        f"Loaded "
        f"{len(retriever.loot_tables)} "
        f"loot tables."
    )

    print(
        f"Loaded "
        f"{len(retriever.entities)} "
        f"entities, "
        f"{len(retriever.items)} "
        f"items."
    )

    print()
    print(
        "Minecraft Knowledge Retriever"
    )
    print(
        "============================="
    )

    print()
    print("Try:")

    print("  execute")
    print("  scoreboard")
    print("  summon")
    print("  give")
    print("  effect")
    print("  zombie drops")
    print("  zombie diamonds")
    print("  chest loot")

    print()
    print(
        "You can also enter natural language."
    )

    print()
    print("Type 'exit' to quit.")
    print()

    while True:

        query = input(
            "Query: "
        ).strip()

        if query.lower() == "exit":
            break

        if not query:
            continue

        results = retriever.search(
            query,
            limit=10
        )

        print()
        print("=" * 60)
        print(
            "RELEVANT MINECRAFT KNOWLEDGE"
        )
        print("=" * 60)

        # ----------------------------------------------------
        # SEMANTIC RESULTS
        # ----------------------------------------------------

        print()
        print(
            "SEMANTIC RESULTS:"
        )

        if results["semantic"]:

            for result in results["semantic"]:

                print(
                    f"  "
                    f"[{result['score']}] "
                    f"/{result['command']}"
                )

                print(
                    "      "
                    + result["data"].get(
                        "description",
                        "N/A"
                    )
                )

        else:

            print(
                "  No semantic results."
            )

        # ----------------------------------------------------
        # SYNTAX RESULTS
        # ----------------------------------------------------

        print()
        print(
            "SYNTAX RESULTS:"
        )

        if results["syntax"]:

            for result in results["syntax"]:

                print(
                    f"  "
                    f"[{result['score']}] "
                    f"{result['syntax']}"
                )

        else:

            print(
                "  No syntax results."
            )

        # ----------------------------------------------------
        # LOOT TABLE RESULTS
        # ----------------------------------------------------

        print()
        print(
            "LOOT TABLE RESULTS:"
        )

        if results["loot_tables"]:

            for result in results["loot_tables"]:

                print(
                    f"  "
                    f"[{result['score']}] "
                    f"{result['path']}"
                )

                print(
                    f"      Type: "
                    f"{result['type']}"
                )

                print(
                    f"      Pools: "
                    f"{result['pool_count']}"
                )

                entries = result.get(
                    "entries",
                    []
                )

                if entries:
                    print("      Entries:")

                    for entry in entries[:10]:

                        entry_type = entry.get(
                            "type",
                            ""
                        )

                        entry_name = entry.get(
                            "name",
                            ""
                        )

                        print(
                            f"        - "
                            f"{entry_type}: "
                            f"{entry_name}"
                        )

        else:

            print(
                "  No loot-table results."
            )

        # ----------------------------------------------------
        # ENTITY RESULTS
        # ----------------------------------------------------

        print()
        print(
            "ENTITY RESULTS:"
        )

        if results.get("entities"):

            for result in results["entities"]:

                print(
                    f"  "
                    f"[{result['score']}] "
                    f"{result['id']}"
                )

                if result.get("loot_table"):
                    print(
                        f"      Loot Table: "
                        f"{result['loot_table']}"
                    )

        else:

            print(
                "  No entity results."
            )

        # ----------------------------------------------------
        # ITEM RESULTS
        # ----------------------------------------------------

        print()
        print(
            "ITEM RESULTS:"
        )

        if results.get("items"):

            for result in results["items"]:

                print(
                    f"  "
                    f"[{result['score']}] "
                    f"{result['id']}"
                )

                if result.get("aliases"):
                    print(
                        f"      Aliases: "
                        f"{', '.join(result['aliases'])}"
                    )

        else:

            print(
                "  No item results."
            )

        print()
        print("=" * 60)
        print()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()