import json
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "1.21.11"
EDITION = "Java"

BASE_DIR = Path(__file__).parent

INPUT_FILE = (
    BASE_DIR
    / "source"
    / VERSION
    / "generated"
    / "reports"
    / "commands.json"
)

OUTPUT_FILE = (
    BASE_DIR
    / "knowledge"
    / "commands"
    / "java"
    / VERSION
    / "commands.jsonl"
)


# ============================================================
# LOAD COMMAND TREE
# ============================================================

print("Loading command tree...")

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    command_tree = json.load(f)

print("Command tree loaded successfully.")


# ============================================================
# CONVERT A NODE INTO A TOKEN
# ============================================================

def node_to_token(node_name, node):
    """
    Converts a Minecraft command-tree node into a readable token.

    Literal:
        "give"

    Argument:
        "<targets>"
    """

    node_type = node.get("type")

    if node_type == "literal":
        return node_name

    if node_type == "argument":
        return f"<{node_name}>"

    return node_name


# ============================================================
# GET ARGUMENT INFORMATION
# ============================================================

def get_argument_info(node_name, node):
    """
    Extracts useful information from an argument node.
    """

    if node.get("type") != "argument":
        return None

    argument = {
        "name": node_name,
        "parser": node.get("parser")
    }

    if "properties" in node:
        argument["properties"] = node["properties"]

    return argument


# ============================================================
# WALK THE COMMAND TREE
# ============================================================

records = []


def walk_node(node_name, node, path, arguments, permissions):
    """
    Recursively walks through the entire Minecraft command tree.

    Every executable node represents a valid command syntax path.
    """

    node_type = node.get("type")

    # --------------------------------------------------------
    # Add current node to command path
    # --------------------------------------------------------

    token = node_to_token(node_name, node)

    new_path = path + [token]

    # --------------------------------------------------------
    # Collect argument information
    # --------------------------------------------------------

    new_arguments = list(arguments)

    argument_info = get_argument_info(node_name, node)

    if argument_info:
        new_arguments.append(argument_info)

    # --------------------------------------------------------
    # Collect permission information
    # --------------------------------------------------------

    new_permissions = list(permissions)

    if "requires" in node:
        new_permissions.append(node["requires"])

    if "permission" in node:
        new_permissions.append(node["permission"])

    # --------------------------------------------------------
    # If executable, save this command syntax
    # --------------------------------------------------------

    if node.get("executable") is True:

        command_name = path[0] if path else node_name

        record = {
            "command": command_name,
            "version": VERSION,
            "edition": EDITION,
            "syntax": " ".join(new_path),
            "tokens": new_path,
            "arguments": new_arguments,
            "permissions": new_permissions
        }

        records.append(record)

    # --------------------------------------------------------
    # Recursively process children
    # --------------------------------------------------------

    children = node.get("children", {})

    for child_name, child_node in children.items():

        walk_node(
            child_name,
            child_node,
            new_path,
            new_arguments,
            new_permissions
        )


# ============================================================
# PROCESS ROOT COMMANDS
# ============================================================

print("Processing command tree...")

root_children = command_tree.get("children", {})

for command_name, command_node in root_children.items():

    walk_node(
        command_name,
        command_node,
        [],
        [],
        []
    )


# ============================================================
# REMOVE DUPLICATES
# ============================================================

unique_records = []
seen = set()

for record in records:

    key = (
        record["command"],
        record["syntax"]
    )

    if key not in seen:

        seen.add(key)
        unique_records.append(record)


records = unique_records


# ============================================================
# WRITE JSONL
# ============================================================

print("Writing JSONL file...")

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:

    for record in records:

        f.write(
            json.dumps(
                record,
                ensure_ascii=False
            )
            + "\n"
        )


# ============================================================
# FINAL INFORMATION
# ============================================================

print()
print("==========================================")
print("Conversion completed successfully!")
print("==========================================")
print()
print(f"Input file : {INPUT_FILE}")
print(f"Output file: {OUTPUT_FILE}")
print()
print(f"Command syntax records generated: {len(records)}")
print()