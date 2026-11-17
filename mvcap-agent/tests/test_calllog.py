from datetime import UTC, datetime, timedelta

from calllog import CallLog

START = datetime(2026, 11, 17, 9, 0, 0, tzinfo=UTC)


def make() -> CallLog:
    return CallLog(caller_id="+19375551234", room_name="call-abc", started_at=START)


def test_a_call_with_no_request_is_type_none():
    row = make().row(START + timedelta(seconds=12))
    assert row["request_type"] == "none"
    assert row["outcome"] == "caller_hung_up"
    assert row["duration_seconds"] == 12


def test_keyword_call_records_the_keyword_once():
    log = make()
    log.keyword("Attorney")
    log.keyword("Attorney")
    log.finish("transferred", "extension:157")
    row = log.row(START + timedelta(seconds=75))
    assert row["request_type"] == "keyword"
    assert row["keywords"] == ["Attorney"]
    assert row["transfer_target"] == "extension:157"
    assert row["duration_seconds"] == 75
    assert row["caller_id"] == "+19375551234"


def test_directory_call_records_the_person():
    log = make()
    log.person("Daniel Franks")
    assert log.row()["request_type"] == "directory"
    assert log.row()["people"] == ["Daniel Franks"]


def test_the_first_request_decides_the_type():
    log = make()
    log.keyword("Fox Run")
    log.person("Daniel Franks")
    assert log.row()["request_type"] == "keyword"


def test_row_has_only_columns_that_exist_in_the_table():
    columns = {
        "started_at", "ended_at", "duration_seconds", "caller_id", "request_type",
        "keywords", "people", "outcome", "transfer_target", "room_name",
    }  # fmt: skip
    assert set(make().row()) == columns
