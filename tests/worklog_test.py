from datetime import datetime

from timetracker.worklog.data import Stint
from timetracker.worklog.error import ActivityAlreadyStopped
from ward import raises, test

BREAKFAST_TIME = datetime.fromisoformat("2024-02-29T08:45:21+0100")
LUNCH_TIME = datetime.fromisoformat("2024-02-29T12:03:47+0100")


@test("A stint with only a start time is unfinished")
def _():
    assert not Stint(start=BREAKFAST_TIME).is_finished()


@test("A stint with both start and end time is finished")
def _():
    assert Stint(start=BREAKFAST_TIME, end=LUNCH_TIME).is_finished()


@test("Finishing an unfinished stint produces a finished one")
def _():
    unfinished_stint = Stint(start=BREAKFAST_TIME)
    finished_stint = unfinished_stint.finished()
    assert finished_stint.is_finished()
    assert finished_stint is not unfinished_stint
    assert not unfinished_stint.is_finished()


@test("Finishing a finished stint raises an exception and leaves the stint unchanged")
def _():
    finished_stint = Stint(start=BREAKFAST_TIME, end=LUNCH_TIME)
    with raises(ActivityAlreadyStopped) as ex:
        finished_stint.finished()
    assert ex.raised.time_last_stopped == LUNCH_TIME
    assert finished_stint.end == LUNCH_TIME


for stint in [Stint(start=BREAKFAST_TIME), Stint(start=BREAKFAST_TIME, end=LUNCH_TIME)]:

    @test("Stints can be serialized to and deserialized from JSON losslessly ({stint})")
    def _(stint: Stint = stint):
        json_str = stint.to_json()
        deserialized_stint = Stint.from_json(json_str)
        assert deserialized_stint == stint
