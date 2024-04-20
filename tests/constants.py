from datetime import datetime

from timetracker.worklog.data import Activity, Stint, Worklog


BREAKFAST_TIME_FORMAT = "2024-02-29T08:45:21.000+0100"
BREAKFAST_TIME = datetime.fromisoformat(BREAKFAST_TIME_FORMAT)
LUNCH_TIME_FORMAT = "2024-02-29T12:03:47.000+0100"
LUNCH_TIME = datetime.fromisoformat(LUNCH_TIME_FORMAT)
COFFEE_TIME_FORMAT = "2024-02-29T13:21:26.000+0100"
COFFEE_TIME = datetime.fromisoformat(COFFEE_TIME_FORMAT)
DINNER_TIME_FORMAT = "2024-02-29T18:44:34.000+0100"
DINNER_TIME = datetime.fromisoformat(DINNER_TIME_FORMAT)

MORNING_SECS = int((LUNCH_TIME - BREAKFAST_TIME).total_seconds())
AFTERNOON_SECS = int((DINNER_TIME - COFFEE_TIME).total_seconds())

UNFINISHED_STINT = Stint(begin=BREAKFAST_TIME)
FINISHED_STINT = Stint(begin=BREAKFAST_TIME, end=LUNCH_TIME)
PUBLISHED_STINT = Stint(begin=BREAKFAST_TIME, end=LUNCH_TIME, is_published=True)

NEW_ACTIVITY = Activity(
    description="Onboarding",
    issue="TIME-42",
)

RUNNING_ACTIVITY = Activity(
    description="Backlog refinement",
    issue="TIME-8",
    stints=[
        Stint(begin=BREAKFAST_TIME, end=LUNCH_TIME),
        Stint(begin=COFFEE_TIME),
    ],
)

COMPLETED_ACTIVITY = Activity(
    description="Support case",
    issue="TIME-13",
    stints=[
        Stint(begin=BREAKFAST_TIME, end=LUNCH_TIME),
        Stint(begin=COFFEE_TIME, end=DINNER_TIME),
    ],
)

PUBLISHED_ACTIVITY = Activity(
    description="Support case",
    issue="TIME-13",
    stints=[
        Stint(begin=BREAKFAST_TIME, end=LUNCH_TIME, is_published=True),
        Stint(begin=COFFEE_TIME, end=DINNER_TIME, is_published=True),
    ],
)

ALL_NIGHTER_ACTIVITY = Activity(
    description="Debugging",
    issue="ME-1",
    stints=[
        Stint(begin=DINNER_TIME),
    ],
)

MIXED_WORKLOG = Worklog(
    activities={
        "completed": COMPLETED_ACTIVITY,
        "running": RUNNING_ACTIVITY,
    }
)
