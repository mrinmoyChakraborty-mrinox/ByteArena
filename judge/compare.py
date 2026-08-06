"""Output comparison for the exact_match checker.

Normalizes output before comparing: strips trailing whitespace from every
line, and drops trailing empty lines. This is the standard lenient exact
match used by most judges — differences that are pure trailing-whitespace
do not count as WA.
"""


def normalize(text: str) -> str:
    lines = text.split("\n")
    cleaned = [line.rstrip() for line in lines]
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return "\n".join(cleaned) + "\n"


def compare(actual: str, expected: str) -> bool:
    return normalize(actual) == normalize(expected)
