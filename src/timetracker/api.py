import asyncio
from dataclasses import replace
from itertools import chain
from typing import Mapping

import httpx

from timetracker.config import Config
from timetracker.worklog.data import Activity, Stint, Worklog


class ApiError(Exception):
    def __init__(self, message: str):
        super().__init__(f"JIRA API request failed: {message}")


class StintPostError(ApiError):
    stint: Stint

    def __init__(self, stint: Stint):
        super().__init__(f"failed to publish stint: {stint}")
        self.stint = stint


class Api:
    config: Config

    def __init__(self, config: Config):
        self.config = config

    def _headers(self) -> Mapping[str, str]:
        return {"Authorization": f"Bearer {self.config.token}"}

    async def _publish_stint(
        self, client: httpx.AsyncClient, issue: str, comment: str, stint: Stint
    ) -> Stint:
        try:
            response = await client.post(
                f"https://{self.config.host}/rest/api/2/issue/{issue}/worklog",
                headers=self._headers(),
                json={
                    "comment": comment,
                    "visibility": {"type": "group", "value": self.config.default_group},
                    "started": stint.begin_jira_format(),
                    "timeSpentSeconds": stint.seconds(),
                },
            )
            response.raise_for_status()
            return stint.published()
        except httpx.HTTPStatusError as e:
            try:
                for msg in e.response.json()["errorMessages"]:
                    e.add_note(msg)
            except Exception:
                pass
            raise StintPostError(stint) from e

    async def _publish_activity(
        self, client: httpx.AsyncClient, name: str, activity: Activity
    ) -> tuple[Activity, list[ApiError]]:
        errors: list[ApiError] = []

        async def publish_and_aggregate_errors(stint: Stint) -> Stint:
            try:
                return await self._publish_stint(
                    client, activity.issue, f"[{name}] {activity.description}", stint
                )
            except ApiError as e:
                errors.append(e)
                return stint

        stints = await asyncio.gather(
            *(
                (
                    publish_and_aggregate_errors(stint)
                    if not stint.is_published and stint.is_finished()
                    else ((f := asyncio.Future()).set_result(stint) or f)
                )
                for stint in activity.stints
            ),
        )
        return (replace(activity, stints=stints), errors)

    async def publish_activity(
        self, name: str, activity: Activity
    ) -> tuple[Activity, list[ApiError]]:
        async with httpx.AsyncClient() as client:
            return await self._publish_activity(client, name, activity)

    async def publish_worklog(self, worklog: Worklog) -> list[ApiError]:
        async with httpx.AsyncClient() as client:
            activities, errors = zip(
                *await asyncio.gather(
                    *(
                        self._publish_activity(client, name, activity)
                        for name, activity in worklog.activities.items()
                    )
                )
            )

            worklog.activities = {
                name: activity for name, activity in zip(worklog.activities, activities)
            }
            return list(chain.from_iterable(errors))
