from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Self

from dataclasses_json import DataClassJsonMixin, config


def _default_config_file() -> Path:
    return Path.home() / ".config" / "timetracker.json"


def data_dir() -> Path:
    return Path.home() / ".local" / "share"


@dataclass(frozen=True)
class Config(DataClassJsonMixin):
    store_dir: str = str(data_dir() / "timetracker")
    host: str = ""
    token: str = ""
    default_group: Optional[str] = None
    epic_link_field: Optional[str] = None
    editor: Optional[str] = None

    file_path: Path = field(
        default=_default_config_file(), metadata=config(exclude=lambda _: True)
    )

    @classmethod
    def from_file(cls: type[Self], file_path: Path) -> Self:
        return cls.from_json(file_path.read_bytes())

    def write_to_file(self):
        self.file_path.parent.mkdir(exist_ok=True)
        self.file_path.write_text(self.to_json(indent=2))

    @property
    def worklog_path(self) -> Path:
        return Path(self.store_dir) / "worklog.json"
