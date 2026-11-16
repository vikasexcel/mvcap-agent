"""Staff directory lookup by spoken name.

Matching is about spelling, not meaning: speech recognition often mangles names, so each
word the caller said is compared to the person's last, legal-first and preferred-first
names with a small tolerance for misspelling. Extensions are never returned to the model.
"""

import difflib
import re
from dataclasses import dataclass

from dataset import Dataset, Target, norm

MATCH_CUTOFF = 0.8
EXACT = 0.99  # a score at or above this means every word matched a name as spoken
_FILLER = {
    "mr",
    "mrs",
    "ms",
    "miss",
    "dr",
    "doctor",
    "the",
    "please",
    "to",
    "speak",
    "with",
}


@dataclass(frozen=True)
class Person:
    id: int
    display: str
    title: str
    # How the call can reach them: a transfer target, or None with the reason why not.
    target: Target | None
    blocked: str | None
    score: float = 1.0


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z']+", norm(text)) if t and t not in _FILLER]


def _person(row: dict, index: int, score: float = 1.0) -> Person:
    pid = row.get("id", index)
    preferred = row.get("first_preferred") or row.get("first_legal") or ""
    display = f"{preferred} {row['last_name']}".strip()
    if row.get("internal_only"):
        return Person(
            pid, display, row.get("title") or "", None, "internal_only", score
        )
    if row.get("extension"):
        return Person(
            pid,
            display,
            row.get("title") or "",
            Target("extension", row["extension"]),
            None,
            score,
        )
    if row.get("direct_phone"):
        return Person(
            pid,
            display,
            row.get("title") or "",
            Target("phone", row["direct_phone"]),
            None,
            score,
        )
    return Person(pid, display, row.get("title") or "", None, "no_extension", score)


def _score(query: list[str], row: dict) -> float:
    names = set(
        _tokens(
            " ".join(
                filter(
                    None,
                    [
                        row["last_name"],
                        row.get("first_legal"),
                        row.get("first_preferred"),
                    ],
                )
            )
        )
    )
    total = 0.0
    for word in query:
        best = max(
            (difflib.SequenceMatcher(None, word, n).ratio() for n in names), default=0.0
        )
        if best < MATCH_CUTOFF:
            return 0.0  # every word the caller said has to match something
        total += best
    return total / len(query)


def search(ds: Dataset, name: str, limit: int = 5) -> list[Person]:
    query = _tokens(name)
    if not query:
        return []
    scored = [(_score(query, row), i, row) for i, row in enumerate(ds.directory)]
    scored = sorted((s for s in scored if s[0] > 0), key=lambda s: -s[0])
    if not scored:
        return []
    best = scored[0][0]
    # Keep everyone who matches about as well as the best match: ambiguous names stay ambiguous.
    return [_person(row, i, score) for score, i, row in scored if score >= best - 0.05][
        :limit
    ]


def get(ds: Dataset, person_id: int) -> Person | None:
    for i, row in enumerate(ds.directory):
        if row.get("id", i) == person_id:
            return _person(row, i)
    return None
