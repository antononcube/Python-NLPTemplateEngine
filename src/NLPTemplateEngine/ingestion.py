"""Ingestion utilities for NLPTemplateEngine."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

import pandas as pd


EXPECTED_COLUMNS = ["DataType", "WorkflowType", "Group", "Key", "Value"]


# ===========================================================
# Utilities
# ===========================================================


def _to_number_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text == "":
        return value
    try:
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            return int(text)
        return float(text)
    except Exception:
        return value


def _normalize_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def _from_wl_spec_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if len(text) < 2 or not (text.startswith("{") and text.endswith("}")):
        return value

    inner = text[1:-1].strip()
    if inner == "":
        return []

    parts = [p.strip() for p in inner.split(",") if p.strip()]
    return [_normalize_quotes(p) for p in parts]


def _hashable_key(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(value)
    return value


def _classify_list(records: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    for rec in records:
        cur: MutableMapping[str, Any] = root
        for key in keys[:-1]:
            val = _hashable_key(rec[key])
            cur = cur.setdefault(val, {})  # type: ignore[assignment]
        last_key = _hashable_key(rec[keys[-1]])
        cur.setdefault(last_key, []).append(rec)
    return root


# ===========================================================
# ConvertCSVDataForType
# ===========================================================


def convert_csv_data_for_type(records: Sequence[Mapping[str, Any]], data_type: str) -> Dict[str, Any]:
    if data_type == "ParameterQuestions":
        ds_query = [r for r in records if r.get("Key") == "Parameter"]
        return _classify_list(ds_query, ["DataType", "WorkflowType", "Value", "Group"])

    if data_type == "ParameterTypePatterns":
        ds_query = [r for r in records if r.get("Key") in ("Parameter", "TypePattern")]
        classified = _classify_list(ds_query, ["DataType", "WorkflowType", "Group", "Key"])

        result: Dict[str, Any] = {}
        for dt, dt_map in classified.items():
            wf_map: Dict[str, Any] = {}
            for wf, groups in dt_map.items():
                param_to_pattern: Dict[str, Any] = {}
                for _, group_map in groups.items():
                    params = group_map.get("Parameter", [])
                    patterns = group_map.get("TypePattern", [])
                    if not params or not patterns:
                        continue
                    param = params[0]["Value"]
                    pattern = patterns[0]["Value"]        
                    if isinstance(param, str) and isinstance(pattern, str):
                        param_to_pattern[param] = pattern
                    if isinstance(param, list) and isinstance(pattern, list):
                        for r in param:
                            for t in pattern:
                                param_to_pattern[r] = t
                    else:
                        ValueError(f"Cannot process param: {param}, and pattern {pattern}.")
                wf_map[wf] = param_to_pattern
            result[dt] = wf_map
        return result

    if data_type == "Questions":
        ds_query = [r for r in records if r.get("DataType") == data_type]
        return _classify_list(ds_query, ["DataType", "WorkflowType", "Group", "Key", "Value"])

    if data_type == "Templates":
        ds_query = [r for r in records if r.get("DataType") == data_type]
        return _classify_list(ds_query, ["DataType", "WorkflowType", "Group", "Value"])

    if data_type == "Defaults":
        ds_query = [r for r in records if r.get("DataType") == data_type]
        classified = _classify_list(ds_query, ["DataType", "WorkflowType", "Key"])

        result: Dict[str, Any] = {}
        for dt, dt_map in classified.items():
            wf_map: Dict[str, Any] = {}
            for wf, params in dt_map.items():
                param_values: Dict[str, Any] = {}
                for key, recs in params.items():
                    if not recs:
                        continue
                    val = recs[0]["Value"]
                    if isinstance(val, list):
                        val = ", ".join(str(v) for v in val)
                    else:
                        val = str(val)
                    param_values[key] = val
                wf_map[wf] = param_values
            result[dt] = wf_map
        return result

    if data_type == "Shortcuts":
        ds_query = [r for r in records if r.get("DataType") == data_type]
        return _classify_list(ds_query, ["DataType", "WorkflowType", "Group"])

    raise ValueError(f"Unknown data type: {data_type}")


# ===========================================================
# ConvertCSVData
# ===========================================================


def _records_from_source(source: Any) -> List[Dict[str, Any]]:
    if isinstance(source, (str, Path)):
        path = Path(source)
        with path.open(newline="", encoding="utf-8") as f:
            import csv

            reader = csv.DictReader(f)
            return [dict(row) for row in reader]

    if hasattr(source, "read"):
        import csv

        reader = csv.DictReader(source)
        return [dict(row) for row in reader]

    if isinstance(source, pd.DataFrame):
        return source.to_dict("records")

    if isinstance(source, Iterable):
        records = list(source)
        if records and isinstance(records[0], Mapping):
            return [dict(r) for r in records]

    raise TypeError("Input must be a CSV path, a pandas DataFrame, or a list of dictionaries.")


def convert_csv_data(source: Any) -> Dict[str, Any]:
    records = _records_from_source(source)

    if not records:
        raise ValueError("No records to ingest.")

    missing = [c for c in EXPECTED_COLUMNS if c not in records[0]]
    if missing:
        raise ValueError(f"Dataset is expected to have the columns {EXPECTED_COLUMNS}.")

    # Convert numbers and WL-like list specs
    normalized: List[Dict[str, Any]] = []
    for rec in records:
        rec2 = dict(rec)
        rec2["Value"] = _to_number_maybe(rec2.get("Value"))
        rec2["Value"] = _from_wl_spec_maybe(rec2.get("Value"))
        normalized.append(rec2)

    result: Dict[str, Any] = {}
    for data_type in [
        "ParameterQuestions",
        "ParameterTypePatterns",
        "Questions",
        "Templates",
        "Defaults",
        "Shortcuts",
    ]:
        converted = convert_csv_data_for_type(normalized, data_type)
        result[data_type] = next(iter(converted.values()), {})

    return result


def merge_hash(a: Mapping[str, Any], b: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(a)
    for key, b_val in b.items():
        a_val = merged.get(key)
        if isinstance(a_val, Mapping) and isinstance(b_val, Mapping):
            merged[key] = merge_hash(a_val, b_val)
        else:
            merged[key] = b_val
    return merged
