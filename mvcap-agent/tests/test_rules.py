import copy
import json
import re

import pytest

import people
from dataset import Dataset, Target
from rules import resolve, rule_index
from store import SNAPSHOT_PATH, load_snapshot


@pytest.fixture(scope="module")
def ds() -> Dataset:
    return load_snapshot()


def spoken(outcome) -> str:
    return " ".join(outcome.speak)


# ---------------------------------------------------------------- the shipped data is sound
def test_snapshot_has_no_validation_errors(ds):
    errors, _ = ds.problems()
    assert errors == []


def test_no_spoken_text_contains_an_extension(ds):
    """Extensions must never be spoken: no message may contain an 'x###' extension."""
    texts = [r.get("message") or "" for r in ds.keywords.values()]
    texts += [r.get("message") or "" for rows in ds.branches.values() for r in rows]
    texts += [u["text"] for u in ds.status_updates]
    pattern = re.compile(r"\bx\d{3}\b|\bext(ension)?\.? ?\d{3}\b", re.IGNORECASE)
    assert not [t for t in texts if pattern.search(t)]


# ---------------------------------------------------------------- simple routing
def test_attorney_transfers_to_157_with_voicemail_note(ds):
    out = resolve(ds, "Attorney")
    assert (out.status, out.then, out.target) == (
        "act",
        "transfer",
        Target("extension", "157"),
    )
    assert "voice message" in spoken(out)


def test_alias_resolves_to_same_handling(ds):
    assert resolve(ds, "lawyer").target == resolve(ds, "Attorney").target
    assert resolve(ds, "Police").target == Target("extension", "157")


def test_say_end_rule_ends_without_transfer(ds):
    out = resolve(ds, "Appeals")
    assert out.then == "end" and out.target is None
    assert "www.miamivalleycap.org" in spoken(out)


def test_followup_rule_continues_the_call(ds):
    out = resolve(ds, "Eligibility")
    assert out.then == "continue" and out.target is None


def test_unknown_keyword_is_reported_not_guessed(ds):
    out = resolve(ds, "Quantum computing")
    assert out.status == "unknown" and out.target is None and out.speak == []


# ---------------------------------------------------------------- county flows
def test_food_asks_the_county_first(ds):
    out = resolve(ds, "Food")
    assert out.status == "need_answer"
    assert "county" in spoken(out).lower()
    assert {"Montgomery", "Greene", "Darke", "Preble"} <= set(out.options)


@pytest.mark.parametrize("county,expected", [("Darke", "601"), ("Preble", "501")])
def test_food_transfers_in_counties_that_offer_it(ds, county, expected):
    out = resolve(ds, "Food Pantry", county)
    assert out.then == "transfer" and out.target == Target("extension", expected)


@pytest.mark.parametrize("county", ["Montgomery", "Greene"])
def test_food_refers_to_211_where_mvcap_has_no_food_program(ds, county):
    out = resolve(ds, "Food", county)
    assert out.then == "end" and out.target is None and "211" in spoken(out)


def test_county_answer_tolerates_the_word_county(ds):
    assert resolve(ds, "Food", "Darke County").target == Target("extension", "601")


def test_near_miss_county_asks_for_a_retry_instead_of_using_the_catch_all(ds):
    out = resolve(ds, "Food", "Montgmery")
    assert out.status == "invalid_answer" and "Montgomery" in out.options


def test_unlisted_county_uses_the_other_branch(ds):
    out = resolve(ds, "Food", "Butler")
    assert out.status == "act" and out.then == "end"


def test_homeless_darke_goes_to_the_domestic_violence_hotline(ds):
    out = resolve(ds, "Homeless", "Darke")
    assert out.target == Target("phone", "+19374566891")


def test_homeless_montgomery_gives_both_referrals(ds):
    text = spoken(resolve(ds, "Homeless", "Montgomery"))
    assert "Homefull" in text and "St. Vincent de Paul" in text


def test_eviction_chains_through_rental_assistance_to_the_county_question(ds):
    out = resolve(ds, "Eviction")
    assert out.status == "need_answer" and out.rule == "Rental Assistance"


# ---------------------------------------------------------------- multi-step flows
def test_utility_assistance_branches_on_disconnection(ds):
    assert resolve(ds, "HEAP", "yes").target == Target("extension", "821")
    assert resolve(ds, "HEAP", "no").target == Target("extension", "102")


def test_yes_no_question_has_no_catch_all(ds):
    assert resolve(ds, "Utility Assistance", "maybe").status == "invalid_answer"


def test_summer_crisis_transfers_to_the_scheduling_line_either_way(ds):
    for answer in ("yes", "no"):
        assert resolve(ds, "Fan", answer).target == Target("phone", "+19375144777")


def test_affordable_housing_follows_the_chosen_department(ds):
    out = resolve(ds, "Affordable Housing", "Fox Run")
    assert out.then == "end" and "937-316-8025" in spoken(out)


# ---------------------------------------------------------------- status updates
def test_status_update_is_spoken_before_the_rule(ds):
    out = resolve(ds, "Winter Crisis")
    assert spoken(out).startswith(
        "The 2026-2027 Winter Crisis program is accepting applications"
    )


def test_status_update_applies_to_aliases_but_not_to_unrelated_rules(ds):
    assert "closed until further notice" in spoken(resolve(ds, "Clothing Assistance"))
    assert "closed until further notice" not in spoken(resolve(ds, "Appeals"))


def test_status_update_is_not_repeated_on_the_answer_turn(ds):
    assert "closed until further notice" not in spoken(
        resolve(ds, "Clothing Assistance", "Darke")
    )


# ---------------------------------------------------------------- directory
def test_find_by_preferred_name(ds):
    [match] = people.search(ds, "Val Bolen")
    assert match.target == Target("extension", "139")


def test_find_by_legal_first_name_and_last_name(ds):
    [match] = people.search(ds, "Valeria Bolen")
    assert match.display == "Val Bolen"


def test_speech_recognition_misspelling_still_matches(ds):
    assert [p.display for p in people.search(ds, "Kevin Reaves")] == ["Kevin Reeves"]


def test_misspelled_match_is_flagged_approximate_so_the_agent_confirms(ds):
    [guess] = people.search(ds, "Kevin Reaves")
    [exact] = people.search(ds, "Kevin Reeves")
    assert guess.score < people.EXACT <= exact.score


def test_ambiguous_first_name_returns_every_candidate(ds):
    assert {p.display for p in people.search(ds, "Ashley")} >= {
        "Ashley King",
        "Ashley Lewis",
    }


def test_adding_a_last_name_resolves_the_ambiguity(ds):
    assert [p.display for p in people.search(ds, "Ashley King")] == ["Ashley King"]


def test_unknown_name_matches_nobody(ds):
    assert people.search(ds, "Zebediah Quillfeather") == []


def test_person_with_no_extension_cannot_be_transferred(ds):
    [match] = people.search(ds, "Candis Adams")
    assert match.target is None and match.blocked == "no_extension"


def test_internal_only_person_is_blocked(ds):
    [match] = people.search(ds, "David Walker")
    assert match.target is None and match.blocked == "internal_only"


def test_person_with_only_a_direct_phone_uses_it(ds):
    [match] = people.search(ds, "Courtney Griffith")
    assert match.target == Target("phone", "+19374225589")


# ---------------------------------------------------------------- prompt
def test_rule_index_lists_aliases_and_answers(ds):
    index = rule_index(ds)
    assert "Attorney (also: Lawyer, Legal Matter)" in index
    assert "[answers: Montgomery, Greene, Darke, Preble, other]" in index


def test_prompt_never_contains_extensions(ds):
    from agent import build_instructions

    prompt = build_instructions(ds)
    assert "x601" not in prompt and "601" not in prompt and "157" not in prompt


# ---------------------------------------------------------------- validation catches bad edits
def tables():
    return json.loads(SNAPSHOT_PATH.read_text())


def problems_after(edit) -> list[str]:
    t = copy.deepcopy(tables())
    edit(t)
    return Dataset.from_tables(t).problems()[0]


def test_validation_rejects_an_alias_to_nowhere():
    def edit(t):
        next(k for k in t["keywords"] if k["keyword"] == "Lawyer")["alias_of"] = (
            "Nothing"
        )

    assert any("alias_of" in e for e in problems_after(edit))


def test_validation_rejects_a_malformed_extension():
    def edit(t):
        next(k for k in t["keywords"] if k["keyword"] == "Attorney")["target"] = "15"

    assert any("bad extension" in e for e in problems_after(edit))


def test_validation_rejects_a_question_without_branches():
    def edit(t):
        t["keyword_branches"] = [
            b for b in t["keyword_branches"] if b["keyword"] != "Food"
        ]

    assert any("Food" in e and "branch" in e for e in problems_after(edit))


def test_validation_rejects_a_transfer_without_a_target():
    def edit(t):
        next(k for k in t["keywords"] if k["keyword"] == "Attorney")["target"] = None
        next(k for k in t["keywords"] if k["keyword"] == "Attorney")["target_type"] = (
            None
        )

    assert any("needs a target" in e for e in problems_after(edit))


def test_inactive_rows_are_ignored_so_a_row_can_be_switched_off():
    def edit(t):
        next(k for k in t["keywords"] if k["keyword"] == "Attorney")["active"] = False
        t["keywords"] = [k for k in t["keywords"] if k["alias_of"] != "Attorney"]

    assert problems_after(edit) == []


def test_prompt_gives_the_real_office_hours_so_the_model_need_not_invent_them(ds):
    from agent import build_instructions

    prompt = build_instructions(ds)
    assert "8:00 a.m. to 4:30 p.m." in prompt and "12:00 p.m. to 1:00 p.m." in prompt
    assert "escalate_to_human" in prompt
