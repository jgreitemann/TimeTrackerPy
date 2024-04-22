from copy import deepcopy
from typing import Optional, Sequence

import httpx
import respx
from timetracker.api import Api, StintPostError
from timetracker.config import Config
from ward import fixture, test, using

from tests import constants

UNAUTHORIZED_RESPONSE = httpx.Response(
    status_code=401,
    json={
        "errorMessages": [
            "You do not have the permission to see the specified issue.",
            "Login Required",
        ],
        "errors": {},
    },
)


class FakeJira:
    api: Api

    def __init__(self):
        self.api = Api(
            Config(
                store_dir="",
                host="jira.example.com",
                token="deadbeef",
                default_group="minions",
            )
        )

    def mock_post_worklog(
        self,
        issue: str,
        comment: str,
        started: str,
        seconds_spent: int,
        *,
        group: Optional[str] = None,
        token: Optional[str] = None,
    ) -> respx.Route:
        if group is None:
            group = self.api.config.default_group
        if token is None:
            token = self.api.config.token

        return respx.post(
            f"https://{self.api.config.host}/rest/api/2/issue/{issue}/worklog",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "comment": comment,
                "visibility": {"type": "group", "value": group},
                "started": started,
                "timeSpentSeconds": seconds_spent,
            },
        )


@fixture
def fake_jira():
    with respx.mock:
        yield FakeJira()


def raise_any(errors: Sequence[Exception]):
    if errors:
        raise errors[0]


@test(
    "Given an empty activity, "
    "when publishing, "
    "then no HTTP requests are made and no errors are aggregated"
)
@using(jira=fake_jira)
async def _(jira: FakeJira):
    activity, errors = await jira.api.publish_activity(
        "ME-12345", constants.NEW_ACTIVITY
    )
    raise_any(errors)
    assert activity == constants.NEW_ACTIVITY


@test(
    "Given an activity with unpublished finished stints, "
    "when publishing with the correct access token, "
    "then a HTTP POST request is made for each unpublished stint and no errors are aggregated"
)
@using(jira=fake_jira)
async def _(jira: FakeJira):
    jira.mock_post_worklog(
        "TIME-13",
        "[ME-12345] Support case",
        started=constants.BREAKFAST_TIME_FORMAT,
        seconds_spent=constants.MORNING_SECS,
    ).mock(httpx.Response(201))
    jira.mock_post_worklog(
        "TIME-13",
        "[ME-12345] Support case",
        started=constants.COFFEE_TIME_FORMAT,
        seconds_spent=constants.AFTERNOON_SECS,
    ).mock(httpx.Response(201))

    activity, errors = await jira.api.publish_activity(
        "ME-12345", constants.COMPLETED_ACTIVITY
    )

    raise_any(errors)
    assert (
        activity == constants.PUBLISHED_ACTIVITY
    ), "stints should now be marked as published"


@test(
    "Given an activity with unpublished finished and running stints, "
    "when publishing with the correct access token, "
    "then a HTTP POST request is made only for the unpublished finished stints and no errors are aggregated"
)
@using(jira=fake_jira)
async def _(jira: FakeJira):
    jira.mock_post_worklog(
        "TIME-8",
        "[BLR] Backlog refinement",
        started=constants.BREAKFAST_TIME_FORMAT,
        seconds_spent=constants.MORNING_SECS,
    ).mock(httpx.Response(201))

    activity, errors = await jira.api.publish_activity(
        "BLR", constants.RUNNING_ACTIVITY
    )

    raise_any(errors)
    assert activity.is_running()
    for stint in activity.stints:
        assert stint.is_published or not stint.is_finished()


@test(
    "Given an activity with unpublished finished stints, "
    "when publishing with an invalid access token, "
    "then each HTTP POST results in an error and the stints are NOT marked as published"
)
@using(jira=fake_jira)
async def _(jira: FakeJira):
    jira.mock_post_worklog(
        "TIME-13",
        "[ME-12345] Support case",
        started=constants.BREAKFAST_TIME_FORMAT,
        seconds_spent=constants.MORNING_SECS,
    ).mock(UNAUTHORIZED_RESPONSE)
    jira.mock_post_worklog(
        "TIME-13",
        "[ME-12345] Support case",
        started=constants.COFFEE_TIME_FORMAT,
        seconds_spent=constants.AFTERNOON_SECS,
    ).mock(UNAUTHORIZED_RESPONSE)

    activity, errors = await jira.api.publish_activity(
        "ME-12345", constants.COMPLETED_ACTIVITY
    )

    assert len(errors) == 2
    for err in errors:
        assert isinstance(err, StintPostError)
        assert isinstance(err.__cause__, httpx.HTTPStatusError)
        assert err.__cause__.response.status_code == 401
        assert err.__cause__.__notes__ == [
            "You do not have the permission to see the specified issue.",
            "Login Required",
        ]
    assert (
        activity == constants.COMPLETED_ACTIVITY
    ), "stints should NOT be marked as published"


@test(
    "Given an activity with published stints, "
    "when publishing with the correct access token, "
    "then no HTTP requests are made for stints that have already been published"
)
@using(jira=fake_jira)
async def _(jira: FakeJira):
    activity, errors = await jira.api.publish_activity(
        "ME-12345", constants.PUBLISHED_ACTIVITY
    )

    raise_any(errors)
    assert activity == constants.PUBLISHED_ACTIVITY


@test(
    "Given a worklog with some unpublished activities, "
    "when publishing with the correct access token, "
    "then only the completed unpublished stints are published"
)
@using(jira=fake_jira)
async def _(jira: FakeJira):
    for name, activity in constants.MIXED_WORKLOG.activities.items():
        for stint in activity.stints:
            if stint.is_finished() and not stint.is_published:
                jira.mock_post_worklog(
                    activity.issue,
                    f"[{name}] {activity.description}",
                    started=stint.begin_jira_format(),
                    seconds_spent=stint.seconds(),
                )

    worklog = deepcopy(constants.MIXED_WORKLOG)
    raise_any(await jira.api.publish_worklog(worklog))

    for name, activity in worklog.activities.items():
        for i, stint in enumerate(activity.stints):
            assert (
                stint.is_published == stint.is_finished()
            ), f"discrepancy for stint #{i} of activity '{name}'"
