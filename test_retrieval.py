import sys
from knowledge_retriever import MinecraftKnowledgeRetriever


def test_retriever():
    retriever = MinecraftKnowledgeRetriever()

    test_cases = [
        {
            "query": "zombie drops",
            "expected_entity": "minecraft:zombie",
            "expected_item": None,
            "expected_loot_table": "entities/zombie.json",
        },
        {
            "query": "zombie drops diamonds",
            "expected_entity": "minecraft:zombie",
            "expected_item": "minecraft:diamond",
            "expected_loot_table": "entities/zombie.json",
        },
        {
            "query": "skeleton drops iron",
            "expected_entity": "minecraft:skeleton",
            "expected_item": "minecraft:iron_ingot",
            "expected_loot_table": "entities/skeleton.json",
        },
        {
            "query": "creeper drops emeralds",
            "expected_entity": "minecraft:creeper",
            "expected_item": "minecraft:emerald",
            "expected_loot_table": "entities/creeper.json",
        },
        {
            "query": "make every zombie drop diamonds",
            "expected_entity": "minecraft:zombie",
            "expected_item": "minecraft:diamond",
            "expected_loot_table": "entities/zombie.json",
        },
        {
            "query": "give spiders a chance to drop diamonds",
            "expected_entity": "minecraft:spider",
            "expected_item": "minecraft:diamond",
            "expected_loot_table": "entities/spider.json",
        },
    ]

    all_passed = True
    print("=" * 70)
    print("RUNNING KNOWLEDGE RETRIEVAL TEST SUITE")
    print("=" * 70)

    for case in test_cases:
        query = case["query"]
        expected_entity = case["expected_entity"]
        expected_item = case["expected_item"]
        expected_loot_table = case["expected_loot_table"]

        results = retriever.search(query, limit=5)

        retrieved_entities = results.get("entities", [])
        retrieved_items = results.get("items", [])
        retrieved_loot_tables = results.get("loot_tables", [])

        top_entity = (
            retrieved_entities[0]["id"] if retrieved_entities else None
        )
        top_item = retrieved_items[0]["id"] if retrieved_items else None
        top_loot_table = (
            retrieved_loot_tables[0]["path"] if retrieved_loot_tables else None
        )

        entity_ok = top_entity == expected_entity
        item_ok = top_item == expected_item
        loot_ok = top_loot_table == expected_loot_table

        case_passed = entity_ok and item_ok and loot_ok
        if not case_passed:
            all_passed = False

        status = "PASS" if case_passed else "FAIL"
        print(f"\n[{status}] Query: '{query}'")
        print(
            f"  Target Entity:     {top_entity} (Expected: {expected_entity}) -> {'OK' if entity_ok else 'MISMATCH'}"
        )
        print(
            f"  Requested Item:    {top_item} (Expected: {expected_item}) -> {'OK' if item_ok else 'MISMATCH'}"
        )
        print(
            f"  Target Loot Table: {top_loot_table} (Expected: {expected_loot_table}) -> {'OK' if loot_ok else 'MISMATCH'}"
        )

    print("\n" + "=" * 70)
    if all_passed:
        print("ALL 6 TEST CASES PASSED SUCCESSFULLY!")
    else:
        print("SOME TEST CASES FAILED.")
    print("=" * 70)

    return all_passed


def test_scoreboard_retrieval():
    retriever = MinecraftKnowledgeRetriever()

    test_cases = [
        {
            "query": "track player deaths on sidebar",
            "expected_criteria": "deathCount",
            "expected_slot": "sidebar",
        },
        {
            "query": "multiply player score by 2",
            "expected_operation": "*=",
        },
        {
            "query": "display health below player name",
            "expected_criteria": "health",
            "expected_slot": "below_name",
        },
        {
            "query": "player trigger menu",
            "expected_criteria": "trigger",
        },
        {
            "query": "compare if player score is greater than high score",
            "expected_operator": ">",
        }
    ]

    all_passed = True
    print("\n" + "=" * 70)
    print("RUNNING SCOREBOARD KNOWLEDGE RETRIEVAL TEST SUITE")
    print("=" * 70)

    for case in test_cases:
        query = case["query"]
        results = retriever.search(query, limit=5)
        scoreboards = results.get("scoreboards", [])

        criteria_ok = True
        if "expected_criteria" in case:
            criteria_ok = any(
                s.get("criteria") == case["expected_criteria"] or s.get("name") == case["expected_criteria"]
                for s in scoreboards
            )

        slot_ok = True
        if "expected_slot" in case:
            slot_ok = any(
                s.get("slot") == case["expected_slot"] or s.get("name") == case["expected_slot"]
                for s in scoreboards
            )

        op_ok = True
        if "expected_operation" in case:
            op_ok = any(
                s.get("operator") == case["expected_operation"]
                for s in scoreboards
            )

        comp_ok = True
        if "expected_operator" in case:
            comp_ok = any(
                s.get("operator") == case["expected_operator"]
                for s in scoreboards
            )

        case_passed = criteria_ok and slot_ok and op_ok and comp_ok and len(scoreboards) > 0
        if not case_passed:
            all_passed = False

        status = "PASS" if case_passed else "FAIL"
        print(f"\n[{status}] Query: '{query}'")
        print(f"  Retrieved {len(scoreboards)} scoreboard knowledge items:")
        for s in scoreboards[:3]:
            print(f"    - {s.get('name')} ({s.get('category')}): {s.get('description', '')[:60]}...")

    print("\n" + "=" * 70)
    if all_passed:
        print("ALL SCOREBOARD RETRIEVAL TESTS PASSED SUCCESSFULLY!")
    else:
        print("SOME SCOREBOARD RETRIEVAL TESTS FAILED.")
    print("=" * 70)

    return all_passed


if __name__ == "__main__":
    success_loot = test_retriever()
    success_sb = test_scoreboard_retrieval()
    sys.exit(0 if (success_loot and success_sb) else 1)
