"""Typed component and convert-function registries.

Component types (`ImagePanel`, `Text`, eventually `Line`/`Polygon`/...) are
each registered with a factory that builds an instance from a YAML dict.
Convert functions (data-shaping callables referenced by name from YAML)
live in a parallel registry. Both registries are populated by the modules
that own the implementations — there is no central import list.
"""

from __future__ import annotations

import operator as _operator
from typing import Any, Callable

# A component factory takes (yaml_dict, base_dir, container_size) and returns
# the component instance. base_dir is the directory containing the instrument
# YAML (used for resolving relative texture paths); container_size is the
# instrument's declared [w, h] in pixels (passed so factories can implement
# resize_to_container without needing a second pass).
ComponentFactory = Callable[[dict[str, Any], "Path", "tuple[int,int] | None"], Any]  # noqa: F821

# A convert function takes (raw_value, get_data) where get_data is a callable
# that fetches another dataref's value (used for cross-dataref maths).
ConvertFunction = Callable[[float, Callable[[object], float]], Any]


_components: dict[str, ComponentFactory] = {}
_converts: dict[str, ConvertFunction] = {}


def register_component(type_name: str, factory: ComponentFactory) -> None:
    if type_name in _components:
        raise ValueError(f"Component type already registered: {type_name!r}")
    _components[type_name] = factory


def get_component_factory(type_name: str) -> ComponentFactory:
    try:
        return _components[type_name]
    except KeyError:
        known = ", ".join(sorted(_components)) or "<none registered>"
        raise ValueError(
            f"Unknown component type {type_name!r}. Known: {known}"
        ) from None


def register_convert(name: str, func: ConvertFunction) -> None:
    if name in _converts:
        raise ValueError(f"Convert function already registered: {name!r}")
    _converts[name] = func


def get_convert(name: str | None) -> ConvertFunction | None:
    if name is None or name in ("", "(none)"):
        return None
    try:
        return _converts[name]
    except KeyError:
        known = ", ".join(sorted(_converts)) or "<none registered>"
        raise ValueError(
            f"Unknown convert function {name!r}. Known: {known}"
        ) from None


_COMPARISON_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "<": _operator.lt, "lt": _operator.lt,
    "<=": _operator.le, "le": _operator.le,
    "==": _operator.eq, "eq": _operator.eq,
    "!=": _operator.ne, "ne": _operator.ne,
    ">": _operator.gt, "gt": _operator.gt,
    ">=": _operator.ge, "ge": _operator.ge,
}


def resolve_predicate_name(block: dict[str, Any]) -> str:
    """Return a convert-function name for a visibility/predicate YAML block.

    Accepts either a named predicate (``predicate: some_registered_name`` —
    the original mechanism, looked up as-is) or an inline threshold
    comparison (``operator: "<" | "<=" | "==" | "!=" | ">" | ">="`` plus
    ``value: <number>``). For the inline form, a comparison convert
    function is synthesized and registered on first use (memoized by
    operator+value so repeated identical blocks don't re-register), so
    every component's existing ``set_visibility(dataref, predicate_name)``
    keeps working unmodified — this only changes what name gets resolved.
    """
    if "predicate" in block:
        return block["predicate"]

    op_key = block["operator"]
    try:
        op_func = _COMPARISON_OPERATORS[op_key]
    except KeyError:
        raise ValueError(
            f"Unknown visibility operator {op_key!r}. "
            f"Known: {', '.join(sorted(_COMPARISON_OPERATORS))}"
        ) from None
    threshold = float(block["value"])

    name = f"__cmp_{op_key}_{threshold!r}__"
    if name not in _converts:
        register_convert(name, lambda value, _get, _op=op_func, _t=threshold: _op(value, _t))
    return name


def known_components() -> list[str]:
    return sorted(_components)


def known_converts() -> list[str]:
    return sorted(_converts)
