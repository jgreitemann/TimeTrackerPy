from functools import partial
from typing import (
    Callable,
    Dict,
    Mapping,
    TypedDict,
)

from dataclasses_json import DataClassJsonMixin
from dataclasses_json.core import Json


def decode_mapping[
    T: DataClassJsonMixin
](cls: type[T], json_dict: Dict[str, Json]) -> Mapping[str, T]:
    return {k: cls.from_dict(v) for k, v in json_dict.items()}


def encode_mapping[T: DataClassJsonMixin](mapping: Mapping[str, T]) -> Dict[str, Json]:
    return {k: v.to_dict() for k, v in mapping.items()}


class Coder[U, V](TypedDict):
    encoder: Callable[[U], V]
    decoder: Callable[[V], U]


def mapping_coder[
    T: DataClassJsonMixin
](cls: type[T]) -> Coder[Mapping[str, T], Dict[str, Json]]:
    return {
        "encoder": encode_mapping,
        "decoder": partial(decode_mapping, cls),
    }
