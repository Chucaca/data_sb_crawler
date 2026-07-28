"""Shared helpers for the crawlers."""
import re

# Handles "1,234", "1.2K", "3,4 N", "12 N", "1,2 Tr", "3.4M"
_NUMBER_RE = re.compile(r"([\d.,]+)\s*(N|K|Tr|M)?", re.IGNORECASE)
_MULTIPLIERS = {"n": 1_000, "k": 1_000, "tr": 1_000_000, "m": 1_000_000}


def parse_count(text):
    """Parses abbreviated Vietnamese/English engagement numbers into an int."""
    if not text:
        return 0
    match = _NUMBER_RE.search(text.strip())
    if not match:
        return 0
    number_part, suffix = match.groups()
    # Abbreviated forms use "," or "." as a decimal separator (e.g. "1,2 N" == 1200).
    # Plain large numbers use "," as a thousands separator (e.g. "12,345").
    if suffix:
        number_part = number_part.replace(",", ".")
        try:
            value = float(number_part)
        except ValueError:
            return 0
        return int(value * _MULTIPLIERS[suffix.lower()])
    try:
        return int(number_part.replace(",", "").replace(".", ""))
    except ValueError:
        return 0


def normalize_comment(text):
    """Lowercases, strips punctuation, and collapses whitespace so
    near-identical seeded comments (e.g. differing only in emoji/punctuation)
    group together under the same key."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
