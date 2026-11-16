"""In-memory view of the MVCAP rules, directory, status updates and settings.

The dataset is built from plain table rows, so it can come from Supabase, the on-disk
cache, or the bundled snapshot interchangeably. `Dataset.problems()` is the validation
that keeps a bad edit from reaching a live call.
"""

import re
from dataclasses import dataclass, field
from typing import Any

EXTENSION_RE = re.compile(r"^\d{3}$")
PHONE_RE = re.compile(r"^\+1\d{10}$")
BRANCH_ACTIONS = {"say_end", "say_transfer", "transfer", "refer", "followup", "goto"}
KEYWORD_ACTIONS = BRANCH_ACTIONS - {"goto"} | {"alias", "ask"}
MAX_ALIAS_DEPTH = 5

TABLES = ("keywords", "keyword_branches", "directory", "status_updates", "settings")


def norm(text: str) -> str:
    # Speech-to-text often returns a curly apostrophe; the directory uses a straight one.
    straight = text.lower().replace("’", "'")  # noqa: RUF001
    return " ".join(straight.split())


@dataclass(frozen=True)
class Target:
    kind: str  # "extension" or "phone"
    value: str

    def __str__(self) -> str:
        return f"x{self.value}" if self.kind == "extension" else self.value


def target_of(row: dict) -> Target | None:
    if row.get("target_type") and row.get("target"):
        return Target(row["target_type"], row["target"])
    return None


@dataclass
class Dataset:
    keywords: dict[str, dict] = field(default_factory=dict)
    branches: dict[str, list[dict]] = field(default_factory=dict)
    directory: list[dict] = field(default_factory=list)
    status_updates: list[dict] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_tables(cls, tables: dict[str, list[dict]]) -> "Dataset":
        """Build a dataset from table rows. Inactive rows are dropped."""

        def live(name: str) -> list[dict]:
            return [r for r in tables.get(name, []) if r.get("active", True)]

        ds = cls()
        for row in live("keywords"):
            ds.keywords[norm(row["keyword"])] = row
        for row in live("keyword_branches"):
            ds.branches.setdefault(norm(row["keyword"]), []).append(row)
        ds.directory = live("directory")
        ds.status_updates = live("status_updates")
        ds.settings = {r["key"]: r["value"] for r in tables.get("settings", [])}
        return ds

    def setting(self, key: str, default: Any = None) -> Any:
        value = self.settings.get(key)
        return default if value is None else value

    def find_keyword(self, name: str) -> dict | None:
        return self.keywords.get(norm(name))

    def canonical(self, name: str) -> dict | None:
        """Follow alias rows to the rule that holds the actual handling."""
        row = self.find_keyword(name)
        for _ in range(MAX_ALIAS_DEPTH):
            if row is None or row["action"] != "alias":
                return row
            row = self.find_keyword(row["alias_of"])
        return None

    def canonical_keywords(self) -> list[dict]:
        return [r for r in self.keywords.values() if r["action"] != "alias"]

    def aliases_of(self, canonical_name: str) -> list[str]:
        key = norm(canonical_name)
        return [
            r["keyword"]
            for r in self.keywords.values()
            if r["action"] == "alias" and norm(r["alias_of"] or "") == key
        ]

    def problems(self) -> tuple[list[str], list[str]]:
        """Return (errors, warnings). Errors make a dataset unsafe to serve."""
        errors: list[str] = []
        warnings: list[str] = []
        extensions = {p["extension"] for p in self.directory if p.get("extension")}

        def check_target(owner: str, row: dict) -> None:
            kind, value = row.get("target_type"), row.get("target")
            if kind == "extension":
                if not EXTENSION_RE.match(value or ""):
                    errors.append(f"{owner}: bad extension {value!r}")
                elif value not in extensions:
                    warnings.append(
                        f"{owner}: extension {value} is not in the directory"
                    )
            elif kind == "phone":
                if not PHONE_RE.match(value or ""):
                    errors.append(
                        f"{owner}: bad phone number {value!r} (use +1XXXXXXXXXX)"
                    )
            elif kind or value:
                errors.append(f"{owner}: target_type/target must both be set")

        for key, row in self.keywords.items():
            owner = f"keyword {row['keyword']!r}"
            action = row["action"]
            if action not in KEYWORD_ACTIONS:
                errors.append(f"{owner}: unknown action {action!r}")
                continue
            if action == "alias":
                if self.canonical(row["keyword"]) is None:
                    errors.append(
                        f"{owner}: alias_of {row['alias_of']!r} is missing or loops"
                    )
                continue
            if action in {
                "say_end",
                "say_transfer",
                "refer",
                "followup",
            } and not row.get("message"):
                errors.append(f"{owner}: {action} needs a message")
            if action in {"transfer", "say_transfer"} and target_of(row) is None:
                errors.append(f"{owner}: {action} needs a target")
            if action == "ask":
                if not row.get("question"):
                    errors.append(f"{owner}: ask needs a question")
                if not self.branches.get(key):
                    errors.append(f"{owner}: ask needs at least one branch")
            check_target(owner, row)

        for key, rows in self.branches.items():
            if key not in self.keywords:
                errors.append(f"branches for unknown keyword {key!r}")
            seen: set[str] = set()
            for row in rows:
                owner = f"branch {key!r}/{row['answer']!r}"
                answer = norm(row["answer"])
                if answer in seen:
                    errors.append(f"{owner}: duplicate answer")
                seen.add(answer)
                action = row["action"]
                if action not in BRANCH_ACTIONS:
                    errors.append(f"{owner}: unknown action {action!r}")
                elif action == "goto":
                    if self.canonical(row.get("goto_keyword") or "") is None:
                        errors.append(
                            f"{owner}: goto {row.get('goto_keyword')!r} not found"
                        )
                else:
                    if action in {
                        "say_end",
                        "say_transfer",
                        "refer",
                        "followup",
                    } and not row.get("message"):
                        errors.append(f"{owner}: {action} needs a message")
                    if (
                        action in {"transfer", "say_transfer"}
                        and target_of(row) is None
                    ):
                        errors.append(f"{owner}: {action} needs a target")
                check_target(owner, row)

        for person in self.directory:
            owner = f"directory {person['last_name']}, {person.get('first_preferred')}"
            if person.get("extension") and not EXTENSION_RE.match(person["extension"]):
                errors.append(f"{owner}: bad extension {person['extension']!r}")
            if person.get("direct_phone") and not PHONE_RE.match(
                person["direct_phone"]
            ):
                errors.append(f"{owner}: bad phone {person['direct_phone']!r}")

        for key in ("greeting",):
            if not self.settings.get(key):
                errors.append(f"settings: {key} is required")
        if not self.canonical_keywords():
            errors.append("no keywords loaded")
        if not self.directory:
            errors.append("directory is empty")
        return errors, warnings
