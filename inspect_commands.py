import json
from pathlib import Path
from collections import Counter


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "1.21.11"

BASE_DIR = Path(__file__).parent

INPUT_FILE = (
    BASE_DIR
    / "knowledge"
    / "commands"
    / "java"
    / VERSION
    / "commands.jsonl"
)


# ============================================================
# LOAD JSONL
# ============================================================

print("Loading commands.jsonl...")

records = []

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    for line_number, line in enumerate(f, start=1):

        line = line.strip()

        if not line:
            continue

        try:
            records.append(json.loads(line))

        except json.JSONDecodeError as e:
            print()
            print("ERROR: Invalid JSON")
            print(f"Line: {line_number}")
            print(e)
            raise


print(f"Loaded {len(records)} records.")


# ============================================================
# 1. TOP-LEVEL COMMANDS
# ============================================================

commands = sorted(
    set(record["command"] for record in records)
)

print()
print("==========================================")
print("1. TOP-LEVEL COMMANDS")
print("==========================================")

print(f"Unique commands: {len(commands)}")

print()
print("Commands:")

for command in commands:
    print(f"  /{command}")


# ============================================================
# 2. PARSER TYPES
# ============================================================

parser_counter = Counter()

for record in records:

    for argument in record.get("arguments", []):

        parser = argument.get("parser")

        if parser:
            parser_counter[parser] += 1


print()
print("==========================================")
print("2. ARGUMENT PARSERS")
print("==========================================")

print(f"Unique parser types: {len(parser_counter)}")

print()

for parser, count in parser_counter.most_common():

    print(f"{parser:45} {count}")


# ============================================================
# 3. PERMISSIONS
# ============================================================

permission_records = []

for record in records:

    permissions = record.get("permissions", [])

    if permissions:
        permission_records.append(record)


print()
print("==========================================")
print("3. PERMISSIONS")
print("==========================================")

print(
    f"Records containing permissions: "
    f"{len(permission_records)}"
)

if permission_records:

    permission_counter = Counter()

    for record in permission_records:

        for permission in record["permissions"]:
            permission_counter[str(permission)] += 1

    print()

    for permission, count in permission_counter.most_common():

        print(f"{permission:45} {count}")

else:

    print("No permissions were recorded.")


# ============================================================
# 4. DUPLICATE SYNTAXES
# ============================================================

syntax_counter = Counter()

for record in records:

    syntax = record.get("syntax")

    if syntax:
        syntax_counter[syntax] += 1


duplicates = {
    syntax: count
    for syntax, count in syntax_counter.items()
    if count > 1
}


print()
print("==========================================")
print("4. DUPLICATE SYNTAXES")
print("==========================================")

print(f"Duplicate syntax entries: {len(duplicates)}")

if duplicates:

    print()
    for syntax, count in list(duplicates.items())[:20]:

        print(f"{count}x  {syntax}")

else:

    print("No duplicate syntaxes found.")


# ============================================================
# 5. RECORDS WITHOUT SYNTAX
# ============================================================

missing_syntax = []

for index, record in enumerate(records):

    if not record.get("syntax"):

        missing_syntax.append(index)


print()
print("==========================================")
print("5. MISSING SYNTAX")
print("==========================================")

print(f"Records without syntax: {len(missing_syntax)}")


# ============================================================
# 6. RECORDS WITHOUT ARGUMENT INFORMATION
# ============================================================

argument_records = 0
no_argument_records = 0

for record in records:

    if record.get("arguments"):
        argument_records += 1
    else:
        no_argument_records += 1


print()
print("==========================================")
print("6. ARGUMENT INFORMATION")
print("==========================================")

print(f"Records with arguments:    {argument_records}")
print(f"Records without arguments: {no_argument_records}")


# ============================================================
# 7. VERSION / EDITION CHECK
# ============================================================

versions = Counter(
    record.get("version")
    for record in records
)

editions = Counter(
    record.get("edition")
    for record in records
)


print()
print("==========================================")
print("7. VERSION / EDITION")
print("==========================================")

print("Versions:")

for version, count in versions.items():
    print(f"  {version}: {count}")

print()

print("Editions:")

for edition, count in editions.items():
    print(f"  {edition}: {count}")


# ============================================================
# 8. LONGEST COMMANDS
# ============================================================

longest = sorted(
    records,
    key=lambda record: len(record.get("tokens", [])),
    reverse=True
)


print()
print("==========================================")
print("8. LONGEST COMMAND SYNTAXES")
print("==========================================")

for record in longest[:10]:

    print(
        f"{len(record.get('tokens', [])):2} tokens  "
        f"{record.get('syntax')}"
    )


# ============================================================
# 9. COMMAND RECORD COUNT
# ============================================================

command_counts = Counter(
    record["command"]
    for record in records
)


print()
print("==========================================")
print("9. RECORDS PER COMMAND")
print("==========================================")

for command, count in command_counts.most_common():

    print(f"/{command:25} {count}")


# ============================================================
# 10. FINAL SUMMARY
# ============================================================

print()
print("==========================================")
print("FINAL SUMMARY")
print("==========================================")

print(f"Version:                    {VERSION}")
print(f"Total syntax records:       {len(records)}")
print(f"Unique commands:             {len(commands)}")
print(f"Unique argument parsers:     {len(parser_counter)}")
print(f"Duplicate syntaxes:          {len(duplicates)}")
print(f"Records with permissions:    {len(permission_records)}")
print(f"Records missing syntax:       {len(missing_syntax)}")
print(f"Records with arguments:       {argument_records}")

print()
print("Inspection completed.")