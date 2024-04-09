from datetime import datetime

from timetracker.worklog.data import Activity, Stint, Worklog


BREAKFAST_TIME = datetime.fromisoformat("2024-02-29T08:45:21+0100")
LUNCH_TIME = datetime.fromisoformat("2024-02-29T12:03:47+0100")
COFFEE_TIME = datetime.fromisoformat("2024-02-29T13:21:26+0100")
DINNER_TIME = datetime.fromisoformat("2024-02-29T18:44:34+0100")

UNFINISHED_STINT = Stint(begin=BREAKFAST_TIME)
FINISHED_STINT = Stint(begin=BREAKFAST_TIME, end=LUNCH_TIME)

RUNNING_ACTIVITY = Activity(
    stints=[
        Stint(begin=BREAKFAST_TIME, end=LUNCH_TIME),
        Stint(begin=COFFEE_TIME),
    ]
)

COMPLETED_ACTIVITY = Activity(
    stints=[
        Stint(begin=BREAKFAST_TIME, end=LUNCH_TIME),
        Stint(begin=COFFEE_TIME, end=DINNER_TIME),
    ]
)

ALL_NIGHTER_ACTIVITY = Activity(
    stints=[
        Stint(begin=DINNER_TIME),
    ]
)

MIXED_WORKLOG = Worklog(
    activities={
        "completed": COMPLETED_ACTIVITY,
        "running": RUNNING_ACTIVITY,
    }
)
