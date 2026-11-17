"""Rewrites text for the voice: phone numbers are read digit by digit, in groups with a pause.

A number written as 937-316-8025 is read by the voice as one fast string. The data keeps the
normal format; this turns it into "9 3 7, 3 1 6, 8 0 2 5" only at the moment it is spoken.
"""

import re

_PHONE = re.compile(r"(?<![\d-])(?:1[-. ])?(\d{3})[-. ](\d{3})[-. ](\d{4})(?![\d-])")


def _digits(group: str) -> str:
    return " ".join(group)


def speakable(text: str) -> str:
    return _PHONE.sub(
        lambda m: ", ".join(_digits(g) for g in m.groups()),
        text,
    )
