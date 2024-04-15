from datetime import datetime


class ActivityUpdateError(Exception):
    activity_name: str

    def __init__(self, activity_name: str):
        super().__init__(f"failed to update activity '{activity_name}'")
        self.activity_name = activity_name


class ActivityStateError(Exception):
    pass


class ActivityAlreadyStarted(ActivityStateError):
    time_last_started: datetime

    def __init__(self, time_last_started: datetime):
        self.time_last_started = time_last_started
        super().__init__(
            f"cannot start the activity because it has already been started at {time_last_started.isoformat()}"
        )


class ActivityAlreadyStopped(ActivityStateError):
    time_last_stopped: datetime

    def __init__(self, time_last_stopped: datetime):
        self.time_last_stopped = time_last_stopped
        super().__init__(
            f"cannot stop the activity because it has already been stopped at {time_last_stopped.isoformat()}"
        )


class ActivityNeverStarted(ActivityStateError):
    def __init__(self):
        super().__init__("cannot stop an activity that has never been started")


class StintNotFinishedError(Exception):
    def __init__(self):
        super().__init__("cannot operate on an unfinished stint")
