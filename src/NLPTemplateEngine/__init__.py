"""NLPTemplateEngine package."""

from __future__ import annotations

from typing import Any, Iterable

from .core import concretize, get_specs
from .ingestion import convert_csv_data, merge_hash

__all__ = ["concretize", "add_template_data", "get_specs"]
__version__ = "0.1.0"


def add_template_data(ds_qas: Any):
    try:
        new_specs = convert_csv_data(ds_qas)
    except Exception:
        return "Cannot ingest data."

    specs = get_specs()
    data_types = list(specs.keys())

    if len(set(data_types).intersection(new_specs.keys())) != len(data_types):
        raise ValueError(f"The data types of the given data should contain {data_types}.")

    for dt in data_types:
        specs[dt] = merge_hash(specs.get(dt, {}), new_specs.get(dt, {}))

    return list(new_specs.keys())
