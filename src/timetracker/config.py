from dataclasses import dataclass
from pathlib import Path

from dataclasses_json import DataClassJsonMixin


@dataclass(frozen=True)
class Config(DataClassJsonMixin):
    store_dir: str
    host: str
    token: str
    default_group: str

    @property
    def worklog_path(self) -> Path:
        return Path(self.store_dir) / "worklog.json"
