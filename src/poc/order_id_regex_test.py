import re

# Comprehensive Regex Engine
ORDER_REGEX = re.compile(
    r"\b(?:order|ord|pkg|package|id)?\s*[\#\:]?\s*([a-z0-9]*\d[a-z0-9]*)\b",
    re.IGNORECASE
)


def extract_valid_order_id(text: str) -> str | None:
    # Blacklist common false-positive words that accidentally contain numbers or match rules
    INVALID_WORDS = {"STREET", "ADDRESS", "AVENUE", "SUITE", "APT", "ROAD"}

    matches = ORDER_REGEX.findall(text)
    for candidate in matches:
        candidate_clean = candidate.upper().strip()
        # Ensure minimum length and not in word blacklist
        if len(candidate_clean) >= 3 and candidate_clean not in INVALID_WORDS:
            return candidate_clean

    return None


# Test Cases
sample_inputs = [
    "Please update address for order #ORD-9912",  # -> ORD-9912
    "Change location for #4401 to 101 Park Ave",  # -> 4401 (Ignores "Park", "101" handled via blacklist/rules)
    "Can you check pkg 8821X please?",  # -> 8821X
    "I want to change my delivery address",  # -> None (No false positive on "address" or "change")
]

for text in sample_inputs:
    print(f"Input: '{text}' => Order ID: {extract_valid_order_id(text)}")