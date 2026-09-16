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


if __name__ == "__main__":
    success = test_retriever()
    sys.exit(0 if success else 1)
