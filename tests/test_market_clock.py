from datetime import datetime, timezone

import pytest

from openmarket.config import TAIPEI
from openmarket.market_clock import is_market_open, next_fetch_time


def tpe(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=TAIPEI)


# 2026-10-12 is a Monday; 2026-10-17 Saturday.
MON = (2026, 10, 12)
FRI = (2026, 10, 16)
SAT = (2026, 10, 17)


@pytest.mark.parametrize(
    "now,expected",
    [
        (tpe(*MON, 8, 59), False),
        (tpe(*MON, 9, 0), True),
        (tpe(*MON, 13, 29, 59), True),
        (tpe(*MON, 13, 30), False),
        (tpe(*MON, 13, 31), False),
        (tpe(*SAT, 10, 0), False),
    ],
)
def test_is_market_open(now, expected):
    assert is_market_open(now) is expected


def test_requires_aware_datetime():
    with pytest.raises(ValueError):
        is_market_open(datetime(2026, 10, 12, 10, 0))


def test_utc_input_is_converted():
    # 02:00 UTC == 10:00 Taipei
    assert is_market_open(datetime(2026, 10, 12, 2, 0, tzinfo=timezone.utc))


def test_never_fetched_is_due_now_any_time():
    now = tpe(*SAT, 22, 0)
    assert next_fetch_time(now, None, 60) == now


def test_before_open_waits_for_open():
    now = tpe(*MON, 8, 0)
    assert next_fetch_time(now, tpe(*MON, 7, 59), 60) == tpe(*MON, 9, 0)


def test_in_session_polls_every_interval():
    now = tpe(*MON, 10, 0, 30)
    assert next_fetch_time(now, tpe(*MON, 10, 0), 60) == tpe(*MON, 10, 1)


def test_in_session_overdue_is_due():
    now = tpe(*MON, 10, 5)
    assert next_fetch_time(now, tpe(*MON, 10, 0), 60) <= now


def test_poll_landing_after_close_moves_to_final_fetch():
    now = tpe(*MON, 13, 29, 30)
    assert next_fetch_time(now, tpe(*MON, 13, 29), 60) == tpe(*MON, 13, 35)


def test_between_close_and_final_waits_for_final():
    now = tpe(*MON, 13, 32)
    assert next_fetch_time(now, tpe(*MON, 13, 32), 60) == tpe(*MON, 13, 35)


def test_final_fetch_caught_up_if_missed():
    now = tpe(*MON, 15, 0)
    assert next_fetch_time(now, tpe(*MON, 13, 20), 60) <= now


def test_after_final_fetch_waits_for_next_day():
    now = tpe(*MON, 13, 36)
    assert next_fetch_time(now, tpe(*MON, 13, 35), 60) == tpe(2026, 10, 13, 9, 0)


def test_friday_after_close_waits_for_monday():
    now = tpe(*FRI, 14, 0)
    assert next_fetch_time(now, tpe(*FRI, 13, 35), 60) == tpe(2026, 10, 19, 9, 0)


def test_weekend_waits_for_monday():
    now = tpe(*SAT, 10, 0)
    assert next_fetch_time(now, tpe(*SAT, 9, 0), 60) == tpe(2026, 10, 19, 9, 0)


# --- review regressions -------------------------------------------------------


def test_missed_final_fetch_caught_up_on_a_later_day():
    # slept Fri 13:20 → woke Sat 10:00: Friday's close must be fetched now
    now = tpe(*SAT, 10, 0)
    assert next_fetch_time(now, tpe(*FRI, 13, 20), 60) <= now


def test_missed_final_fetch_caught_up_next_morning_before_open():
    now = tpe(2026, 10, 13, 8, 0)  # Tue
    assert next_fetch_time(now, tpe(*MON, 13, 20), 60) <= now


def test_after_friday_close_fetched_weekend_waits_for_monday():
    now = tpe(*SAT, 10, 0)
    assert next_fetch_time(now, tpe(*FRI, 13, 35), 60) == tpe(2026, 10, 19, 9, 0)


def test_failed_attempt_retried_out_of_session():
    now = tpe(*SAT, 10, 0, 30)
    assert next_fetch_time(now, tpe(*SAT, 10, 0), 60, last_failed=True) == tpe(*SAT, 10, 1)
    assert next_fetch_time(now, tpe(*SAT, 10, 0), 60, last_failed=False) == tpe(2026, 10, 19, 9, 0)


def test_failed_attempt_in_session_keeps_normal_interval():
    now = tpe(*MON, 10, 0, 30)
    assert next_fetch_time(now, tpe(*MON, 10, 0), 60, last_failed=True) == tpe(*MON, 10, 1)
