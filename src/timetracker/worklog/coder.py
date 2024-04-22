from functools import partial
from typing import (
    Callable,
    Dict,
    Generic,
    List,
    Mapping,
    Sequence,
    TypedDict,
    TypeVar,
)

from dataclasses_json import DataClassJsonMixin
from dataclasses_json.core import Json

T = TypeVar("T", bound=DataClassJsonMixin)


def decode_seq(cls: type[T], json_list: List[Json]) -> Sequence[T]:
    return [cls.from_dict(e) for e in json_list]


def encode_seq(seq: Sequence[T]) -> List[Json]:
    return [e.to_dict() for e in seq]


def decode_mapping(cls: type[T], json_dict: Dict[str, Json]) -> Mapping[str, T]:
    return {k: cls.from_dict(v) for k, v in json_dict.items()}


def encode_mapping(mapping: Mapping[str, T]) -> Dict[str, Json]:
    return {k: v.to_dict() for k, v in mapping.items()}


U = TypeVar("U")
V = TypeVar("V")


class Coder(TypedDict, Generic[U, V]):
    encoder: Callable[[U], V]
    decoder: Callable[[V], U]


def seq_coder(cls: type[T]) -> Coder[Sequence[T], List[Json]]:
    return {
        "encoder": encode_seq,
        "decoder": partial(decode_seq, cls),
    }


def mapping_coder(cls: type[T]) -> Coder[Mapping[str, T], Dict[str, Json]]:
    return {
        "encoder": encode_mapping,
        "decoder": partial(decode_mapping, cls),
    }
