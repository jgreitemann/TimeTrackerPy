from dataclasses import dataclass

from dataclasses_json import DataClassJsonMixin


@dataclass(frozen=True)
class Config(DataClassJsonMixin):
    host: str
    token: str
    default_group: str
