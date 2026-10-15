"""
MSG-02: mask phone numbers, emails, links and social handles in messages.
Masking errs on the side of caution: the anti-bypass strategy depends on it.
"""
import re

MASK = "[hidden]"

_NUMBER_WORDS = r"(?:zero|one|two|three|four|five|six|seven|eight|nine|oh)"
PATTERNS = [
    # emails, including "name at gmail dot com"
    re.compile(r"[\w.+-]+\s*(?:@|\(at\)|\[at\]|\sat\s)\s*[\w-]+\s*(?:\.|\(dot\)|\[dot\]|\sdot\s)\s*[a-z]{2,}", re.I),
    # URLs and bare domains
    re.compile(r"(?:https?://|www\.)\S+", re.I),
    re.compile(r"\b[\w-]+\.(?:com|ng|net|org|me|io|co|link|ly)(?:\.\w{2})?\b(?:/\S*)?", re.I),
    # phone-like digit runs (7+ digits allowing separators)
    re.compile(r"(?:\+?\d[\s\-().]*){7,}"),
    # numbers spelled out ("zero eight zero three ...")
    re.compile(rf"(?:\b{_NUMBER_WORDS}\b[\s,-]*){{5,}}", re.I),
    # social handles and platform mentions
    re.compile(r"(?<![\w])@[A-Za-z0-9_.]{3,}"),
    re.compile(r"\b(?:whats\s*app|watsapp|telegram|instagram|insta|ig|facebook|fb|snapchat|tiktok|signal)\b[^\n]{0,30}", re.I),
]


def mask(text):
    """Return (masked_text, was_masked)."""
    masked = text
    for pattern in PATTERNS:
        masked = pattern.sub(MASK, masked)
    return masked, masked != text
