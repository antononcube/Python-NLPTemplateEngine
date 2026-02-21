"""Core functionality for NLPTemplateEngine."""

from __future__ import annotations

from importlib import resources
from typing import Any, Dict, Iterable, Mapping, Sequence

from LLMTextualAnswer import llm_classify, llm_textual_answer

from .ingestion import convert_csv_data, merge_hash


_QAS_SPECS: Dict[str, Any] = {}


_WORKFLOW_SPEC_TO_FULL_NAME = {
    "Classification": "Classification",
    "ClCon": "Classification",
    "LatentSemanticAnalysis": "Latent Semantic Analysis",
    "QuantileRegression": "Quantile Regression",
    "Recommendations": "Recommendations",
    "QRMon": "Quantile Regression",
    "RandomTabularDataset": "Random Tabular Dataset",
    "ProgrammingEnvironment": "Programming Environment",
}


def _workflow_full_name_to_spec() -> Dict[str, Sequence[str]]:
    result: Dict[str, list[str]] = {}
    for spec, full in _WORKFLOW_SPEC_TO_FULL_NAME.items():
        result.setdefault(full, []).append(spec)
    return result


_WORKFLOW_FULL_NAME_TO_SPEC = _workflow_full_name_to_spec()


def get_specs(spec_type: str = "standard") -> Dict[str, Any]:
    global _QAS_SPECS
    if _QAS_SPECS:
        return _QAS_SPECS

    with resources.files("NLPTemplateEngine.resources").joinpath("dfQASParameters.csv").open(
        "r", encoding="utf-8"
    ) as f:
        _QAS_SPECS = convert_csv_data(f)

    return _QAS_SPECS


def _normalize_lang(lang: str) -> str:
    return (lang or "").strip().lower() or "raku"


def _syntax_for_lang(lang: str) -> Dict[str, str]:
    syntax = {
        "python": {
            "Automatic": "None",
            "True": "True",
            "False": "False",
            "left-list-bracket": "[",
            "right-list-bracket": "]",
            "double-quote": '"',
        },
        "r": {
            "Automatic": "NULL",
            "True": "TRUE",
            "False": "FALSE",
            "left-list-bracket": "c(",
            "right-list-bracket": ")",
            "double-quote": '"',
        },
        "raku": {
            "Automatic": "Whatever",
            "True": "True",
            "False": "False",
            "left-list-bracket": "[",
            "right-list-bracket": "]",
            "double-quote": '"',
        },
        "wl": {
            "Automatic": "Automatic",
            "True": "True",
            "False": "False",
            "left-list-bracket": "{",
            "right-list-bracket": "}",
            "double-quote": '"',
        },
    }

    return syntax.get(_normalize_lang(lang), syntax["raku"])


def _coerce_answer(param: str, ans: str, param_type_patterns: Mapping[str, Any], syntax: Mapping[str, str]) -> str:
    pattern = param_type_patterns.get(param)
    if not isinstance(ans, str):
        return str(ans)

    lowered = ans.lower()
    if pattern in {"_?BooleanQ", "Bool"}:
        if lowered in {"false", "n/a", "no", "none", "null"}:
            return syntax["False"]
        if lowered in {"automatic", "auto", "whatever"}:
            return ans
        return syntax["True"]

    if pattern in {"{_?StringQ..}", "{_String..}"}:
        parts = [p.strip() for p in ans.split(",") if p.strip()]
        quoted = ", ".join(f"{syntax['double-quote']}{p}{syntax['double-quote']}" for p in parts)
        return f"{syntax['left-list-bracket']}{quoted}{syntax['right-list-bracket']}"

    if pattern in {"{_?NumericQ..}", "{_?NumberQ..}", "{_Integer..}", "{_?IntegerQ..}"}:
        return f"{syntax['left-list-bracket']}{ans}{syntax['right-list-bracket']}"

    return ans


def _replace_template_slots(template: str, param: str, value: str) -> str:
    template = template.replace(f"`{param}`", value)
    template = template.replace(f"$*{param}", value)

    slot = f'TemplateSlot["{param}"]'
    if slot in template:
        import re

        template = re.sub(r",\s*TemplateSlot\[\"%s\"\]\s*,\s*" % re.escape(param), value, template)
        template = template.replace(slot, value)

    return template


def _final_template_adjustments(template: str) -> str:
    if template.startswith('TemplateObject[{"'):
        template = template[len('TemplateObject[{"') :]
    if template.endswith('"}, CombinerFunction -> StringJoin, InsertionFunction -> TextString]'):
        template = template[: -len('"}, CombinerFunction -> StringJoin, InsertionFunction -> TextString]')]
    return template


# ===========================================================
# Concretize
# ===========================================================


def concretize(
    command: str,
    template: str | None = None,
    lang: str = "WL",
    avoid_monads: bool = False,
    format: str = "dict",
    user_id: str = "",
    **kwargs: Any,
) -> str:
    if template in (None, "", "Whatever"):
        labels = [
            name
            for name in dict.fromkeys(_WORKFLOW_SPEC_TO_FULL_NAME.values())
            if name != "Programming Environment"
        ]

        args2 = dict(kwargs)
        args2.setdefault("request", "which of these workflows characterizes it")
        if "llm" not in args2:
            if "llm_evaluator" in args2:
                args2["llm"] = args2["llm_evaluator"]
            elif "finder" in args2:
                args2["llm"] = args2["finder"]
            elif "e" in args2:
                args2["llm"] = args2["e"]

        template = llm_classify(command, labels, form=dict, **args2)

        if kwargs.get("echo"):
            print(f"Workflow classification result: {template}")

        if template in _WORKFLOW_FULL_NAME_TO_SPEC:
            template2: Any = _WORKFLOW_FULL_NAME_TO_SPEC[template]
            if isinstance(template2, Iterable) and not isinstance(template2, str):
                preferred = [t for t in template2 if t in {"LSAMon", "ClCon", "SMRMon", "QRMon"}]
                template2 = preferred[0] if preferred else list(template2)[0]
            return concretize(command, template=template2, lang=lang, avoid_monads=avoid_monads, format=format, user_id=user_id, **kwargs)

        raise ValueError("Cannot determine the workflow type of the given command.")

    if format not in ("dict", "code"):
        raise ValueError("The argument format is expected to be one of 'dict', 'code', or None")

    specs = get_specs()
    if template not in specs.get("Templates", {}):
        raise ValueError(f"There is no template {template} for the language {lang}.")

    # Get questions
    qas2 = specs.get("ParameterQuestions", {}).get(template, {})
    param_to_question = {param: list(questions.keys())[0] for param, questions in qas2.items() if questions}
    question_to_param = {v: k for k, v in param_to_question.items()}

    param_type_patterns = specs.get("ParameterTypePatterns", {}).get(template, {})

    questions = [q + "?" for q in question_to_param.keys()]

    # Find answers
    args2 = dict(kwargs)
    if "llm" not in args2:
        if "llm_evaluator" in args2:
            args2["llm"] = args2["llm_evaluator"]
        elif "e" in args2:
            args2["llm"] = args2["e"]
        elif "finder" in args2:
            args2["llm"] = args2["finder"]

    answers_raw = llm_textual_answer(command, questions, form=dict, **args2)

    if isinstance(answers_raw, Mapping):
        answers = dict(answers_raw)
    elif isinstance(answers_raw, Sequence):
        answers = dict(answers_raw)
    else:
        raise ValueError("Unexpected answers format returned by llm_textual_answer.")

    tmpl = specs.get("Templates", {}).get(template, {}).get(lang, {})
    tmpl_value = ""
    if tmpl:
        first_bucket = next(iter(tmpl.values()))
        if first_bucket:
            tmpl_value = first_bucket[0].get("Value", "")

    if kwargs.get("echo"):
        print({"template": tmpl_value})

    syntax = _syntax_for_lang(lang)

    if answers:
        param_to_answer: Dict[str, str] = {}
        for question, param in question_to_param.items():
            ans = answers.get(question + "?")
            if ans is None:
                ans = answers.get(question)
            if ans is None:
                ans = ""
            if isinstance(ans, str) and ans.lower() in {"n/a", "none", "null"}:
                ans = specs.get("Defaults", {}).get(template, {}).get(param, f"$*{param}")
            param_to_answer[param] = ans

        defaults = specs.get("Defaults", {}).get(template, {})
        param_to_answer = merge_hash(defaults, param_to_answer)

        tmpl_filled = tmpl_value
        for param, ans in param_to_answer.items():
            ans2 = _coerce_answer(param, str(ans), param_type_patterns, syntax)
            tmpl_filled = _replace_template_slots(tmpl_filled, param, ans2)

        return _final_template_adjustments(tmpl_filled)

    return tmpl_value
