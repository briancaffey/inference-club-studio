import re


def sanitize_text(text: str) -> str:
    """Sanitize text for TTS input.

    Handles curly quotes, parentheses, special dashes, speaker tags, etc.
    """
    s = text

    # Strip speaker tags like [S1], [S2]
    s = re.sub(r"\[S\d+\]\s*", "", s)

    # Curly single quotes → straight
    s = s.replace("\u2018", "'")  # '
    s = s.replace("\u2019", "'")  # '

    # Curly double quotes → straight
    s = s.replace("\u201c", '"')  # "
    s = s.replace("\u201d", '"')  # "

    # Em dash / en dash → comma or hyphen
    s = s.replace("\u2014", ", ")  # —
    s = s.replace("\u2013", "-")   # –

    # Ellipsis character → three dots
    s = s.replace("\u2026", "...")

    # Remove parentheses and their contents
    s = re.sub(r"\s*\([^)]*\)", "", s)

    # Collapse multiple spaces
    s = re.sub(r"  +", " ", s)

    # Strip leading/trailing whitespace
    s = s.strip()

    return s
