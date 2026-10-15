import re


def normalise_phone(value):
    """Normalise Nigerian phone formats to E.164 (+234XXXXXXXXXX). Returns None if invalid.

    Accepts 08012345678, 8012345678, 2348012345678, +234 801 234 5678.
    Other international numbers (diaspora) are accepted if already in +E.164 form.
    """
    if not value:
        return None
    digits = re.sub(r"[^\d+]", "", str(value))
    if digits.startswith("+234"):
        digits = digits[4:]
    elif digits.startswith("234") and len(digits) == 13:
        digits = digits[3:]
    elif digits.startswith("+"):
        return digits if re.fullmatch(r"\+[1-9]\d{7,14}", digits) else None
    if digits.startswith("0"):
        digits = digits[1:]
    if re.fullmatch(r"[789][01]\d{8}", digits):
        return "+234" + digits
    return None
