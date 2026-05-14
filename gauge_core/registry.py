"""Typed component and convert-function registries.

Component types (`ImagePanel`, `Text`, eventually `Line`/`Polygon`/...) are
each registered with a factory that builds an instance from a YAML dict.
Convert functions (data-shaping callables referenced by name from YAML)
live in a parallel registry. Both registries are populated by the modules
that own the implementations — there is no central import list.
"""

from __future__ import annotations

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
    if name is None or name == "":
        return None
    try:
        return _converts[name]
    except KeyError:
        known = ", ".join(sorted(_converts)) or "<none registered>"
        raise ValueError(
            f"Unknown convert function {name!r}. Known: {known}"
        ) from None


def known_components() -> list[str]:
    return sorted(_components)


def known_converts() -> list[str]:
    return sorted(_converts)
