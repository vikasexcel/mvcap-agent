"""Turns a keyword (and an optional follow-up answer) into what the call should do.

The model only chooses the keyword and relays the caller's answer. Everything that is
said or done is read from the dataset here, so wording and targets are never invented.
"""

import difflib
from dataclasses import dataclass, field
from typing import Literal

from dataset import MAX_ALIAS_DEPTH, Dataset, Target, norm, target_of

Status = Literal["unknown", "need_answer", "invalid_answer", "act"]
Then = Literal["end", "transfer", "continue"]


@dataclass
class Outcome:
    status: Status
    speak: list[str] = field(default_factory=list)
    then: Then | None = None
    target: Target | None = None
    options: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    rule: str = ""


def _status_lines(ds: Dataset, names: set[str]) -> list[str]:
    lines = []
    for update in ds.status_updates:
        applies = {norm(n) for n in (update.get("applies_to") or [])}
        if applies & names:
            lines.append(update["text"])
    return lines


def _act(ds: Dataset, row: dict, rule: str) -> Outcome:
    action = row["action"]
    speak = [row["message"]] if row.get("message") else []
    # Plain transfers, and scripted messages that don't already announce it.
    if action in {"transfer", "say_transfer"} and (
        not speak or "transfer" not in speak[0].lower()
    ):
        speak.append(
            ds.setting("default_transfer_message", "One moment while I transfer you.")
        )
    if row.get("voicemail_note") and action in {"transfer", "say_transfer"}:
        speak.append(ds.setting("voicemail_note", ""))
    then: Then = {
        "say_end": "end",
        "refer": "end",
        "transfer": "transfer",
        "say_transfer": "transfer",
        "followup": "continue",
    }[action]
    return Outcome(
        "act",
        speak=[s for s in speak if s],
        then=then,
        target=target_of(row),
        rule=rule,
    )


def resolve(
    ds: Dataset, keyword: str, answer: str | None = None, _depth: int = 0
) -> Outcome:
    row = ds.find_keyword(keyword)
    if row is None or _depth > MAX_ALIAS_DEPTH:
        names = [r["keyword"] for r in ds.keywords.values()]
        close = difflib.get_close_matches(keyword, names, n=3, cutoff=0.6)
        return Outcome("unknown", suggestions=close, rule=keyword)

    asked_as = {norm(keyword)}
    canonical = ds.canonical(keyword)
    if canonical is None:
        return Outcome("unknown", rule=keyword)
    asked_as.add(norm(canonical["keyword"]))
    status = _status_lines(ds, asked_as) if answer is None else []

    if canonical["action"] != "ask":
        outcome = _act(ds, canonical, canonical["keyword"])
        outcome.speak = status + outcome.speak
        return outcome

    branches = ds.branches.get(norm(canonical["keyword"]), [])
    options = [b["answer"] for b in branches if norm(b["answer"]) != "other"]
    if answer is None:
        return Outcome(
            "need_answer",
            speak=[*status, canonical["question"]],
            options=options,
            rule=canonical["keyword"],
        )

    wanted = norm(answer).removesuffix(" county")
    chosen = next((b for b in branches if norm(b["answer"]) == wanted), None)
    if chosen is None:
        # A near miss ("Montgmery") is the model's slip, not a county we don't cover: ask it to
        # retry with an exact option rather than silently using the catch-all branch.
        near = difflib.get_close_matches(
            wanted, [norm(o) for o in options], n=1, cutoff=0.7
        )
        if not near:
            chosen = next((b for b in branches if norm(b["answer"]) == "other"), None)
    if chosen is None:
        return Outcome("invalid_answer", options=options, rule=canonical["keyword"])
    if chosen["action"] == "goto":
        return resolve(ds, chosen["goto_keyword"], None, _depth + 1)
    return _act(ds, chosen, f"{canonical['keyword']} / {chosen['answer']}")


def rule_index(ds: Dataset) -> str:
    """One line per rule for the system prompt: canonical keyword, its aliases, and answers."""
    lines = []
    for row in sorted(ds.canonical_keywords(), key=lambda r: norm(r["keyword"])):
        line = row["keyword"]
        aliases = ds.aliases_of(row["keyword"])
        if aliases:
            line += " (also: " + ", ".join(aliases) + ")"
        if row["action"] == "ask":
            options = [b["answer"] for b in ds.branches.get(norm(row["keyword"]), [])]
            line += " [answers: " + ", ".join(options) + "]"
        lines.append("- " + line)
    return "\n".join(lines)
