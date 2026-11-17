import asyncio

import pytest

import people
from agent import Receptionist
from store import load_snapshot


@pytest.fixture
def receptionist(monkeypatch):
    ds = load_snapshot()
    bot = Receptionist.__new__(Receptionist)
    bot.ds = ds
    bot._confirming = None
    bot._replied = False
    bot.log = None
    said, moved = [], []

    async def say(parts):
        said.append(" ".join(p for p in parts if p))

    async def transfer(target):
        moved.append(target)

    monkeypatch.setattr(bot, "_say", say)
    monkeypatch.setattr(bot, "_transfer", transfer)
    bot.said, bot.moved = said, moved
    return bot


class Ctx:
    def disallow_interruptions(self):
        pass


def transfer_tool(bot, pid):
    return asyncio.run(Receptionist.transfer_to_person.__wrapped__(bot, Ctx(), pid))


def reachable_person(ds):
    for i, row in enumerate(ds.directory):
        person = people.get(ds, row.get("id", i))
        if person and person.target:
            return person
    raise AssertionError("no reachable person in the snapshot")


def test_first_call_asks_for_confirmation_and_does_not_transfer(receptionist):
    person = reachable_person(receptionist.ds)
    transfer_tool(receptionist, person.id)
    assert receptionist.moved == []
    assert receptionist.said[0].startswith(
        "Do you want to connect with " + person.display
    )


def test_second_call_without_a_caller_reply_does_not_transfer(receptionist):
    person = reachable_person(receptionist.ds)
    transfer_tool(receptionist, person.id)
    transfer_tool(receptionist, person.id)
    assert receptionist.moved == []


def test_transfers_after_the_caller_replies(receptionist):
    person = reachable_person(receptionist.ds)
    transfer_tool(receptionist, person.id)
    receptionist._replied = True
    transfer_tool(receptionist, person.id)
    assert receptionist.moved == [person.target]


def test_a_reply_about_a_different_person_does_not_carry_over(receptionist):
    ds = receptionist.ds
    first = reachable_person(ds)
    other = next(
        p
        for i, row in enumerate(ds.directory)
        if (p := people.get(ds, row.get("id", i))) and p.target and p.id != first.id
    )
    transfer_tool(receptionist, first.id)
    receptionist._replied = True
    transfer_tool(receptionist, other.id)
    assert receptionist.moved == []
    assert receptionist.said[-1].startswith(
        "Do you want to connect with " + other.display
    )
