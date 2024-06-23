from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dataclasses_json import DataClassJsonMixin


@dataclass(frozen=True)
class Config(DataClassJsonMixin):
    store_dir: str
    host: str
    token: str
    default_group: str
    epic_link_field: Optional[str] = None
    editor: Optional[str] = None

    @property
    def worklog_path(self) -> Path:
        return Path(self.store_dir) / "worklog.json"
