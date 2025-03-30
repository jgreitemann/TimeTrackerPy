import asyncio
from dataclasses import dataclass, replace
from itertools import chain
from typing import Mapping, Optional

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


class IssueGetError(ApiError):
    key: str

    def __init__(self, key: str):
        super().__init__(f"failed to get issue info for {key}")
        self.key = key


class IssueNotFoundError(ApiError):
    key: str

    def __init__(self, key: str):
        super().__init__(f"no issue exists for key {key}")
        self.key = key


@dataclass(frozen=True)
class IssueInfo:
    key: str
    summary: str
    epic_key: Optional[str]


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
                    "started": stint.begin_jira_format(),
                    "timeSpentSeconds": stint.seconds(),
                    **(
                        {
                            "visibility": {
                                "type": "group",
                                "value": self.config.default_group,
                            }
                        }
                        if self.config.default_group is not None
                        else {}
                    ),
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

        stints = [
            (
                await publish_and_aggregate_errors(stint)
                if not stint.is_published and stint.is_finished()
                else stint
            )
            for stint in activity.stints
        ]
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

    async def get_issue(self, key: str) -> IssueInfo:
        try:
            async with httpx.AsyncClient() as client:
                fields = filter(None, ["summary", self.config.epic_link_field])

                response = await client.get(
                    f"https://{self.config.host}/rest/api/2/issue/{key}",
                    headers=self._headers(),
                    params={"fields": ",".join(fields)},
                )
                response.raise_for_status()
                data = response.json()

                return IssueInfo(
                    key=key,
                    summary=data["fields"]["summary"],
                    epic_key=data["fields"].get(self.config.epic_link_field),
                )
        except httpx.HTTPStatusError as e:
            try:
                for msg in e.response.json()["errorMessages"]:
                    e.add_note(msg)
            except Exception:
                pass
            if e.response.status_code == 404:
                raise IssueNotFoundError(key) from e
            else:
                raise IssueGetError(key) from e

    async def get_fields(self) -> Mapping[str, str]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://{self.config.host}/rest/api/2/field",
                    headers=self._headers(),
                )
                response.raise_for_status()
                return {field["name"]: field["id"] for field in response.json()}
        except httpx.HTTPStatusError as e:
            raise ApiError("failed to get field info") from e
