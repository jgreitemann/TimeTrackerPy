from typing import Generator

from pyfakefs.fake_filesystem import FakeFilesystem
from pyfakefs.fake_filesystem_unittest import Patcher
from ward import fixture


@fixture
def fake_fs() -> Generator[FakeFilesystem, None, None]:
    with Patcher() as patcher:
        if patcher.fs is None:
            raise Exception("failed to patch filesystem")
        yield patcher.fs
