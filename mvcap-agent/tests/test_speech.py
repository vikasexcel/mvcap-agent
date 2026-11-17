from speech import speakable


def test_phone_number_is_read_digit_by_digit_in_groups():
    assert (
        speakable("Please dial 937-316-8025.") == "Please dial 9 3 7, 3 1 6, 8 0 2 5."
    )


def test_toll_free_number_with_leading_one():
    assert speakable("call 1-800-433-8500 now") == "call 8 0 0, 4 3 3, 8 5 0 0 now"


def test_text_without_a_phone_number_is_unchanged():
    text = "Our hours are 8 to 4:30, and the year is 2026."
    assert speakable(text) == text


def test_several_numbers_in_one_message():
    out = speakable("Call 937-293-1945 or 937-222-5555.")
    assert out == "Call 9 3 7, 2 9 3, 1 9 4 5 or 9 3 7, 2 2 2, 5 5 5 5."
