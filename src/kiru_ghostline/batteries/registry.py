"""Battery registry: the set of disorders Ghostline can probe for."""

from .base import Battery

_REGISTRY: dict[str, Battery] = {}


def register(cls: type[Battery]) -> type[Battery]:
    """Class decorator: instantiate the battery and add it to the registry."""
    instance = cls()
    if instance.slug in _REGISTRY:
        raise ValueError(f"battery already registered: {instance.slug}")
    _REGISTRY[instance.slug] = instance
    return cls


def get(slug: str) -> Battery:
    try:
        return _REGISTRY[slug]
    except KeyError:
        raise KeyError(f"unknown battery: {slug!r} (registered: {sorted(_REGISTRY)})")


def all_batteries() -> list[Battery]:
    return [_REGISTRY[slug] for slug in sorted(_REGISTRY)]


def disorders() -> list[str]:
    return sorted({b.disorder for b in _REGISTRY.values()})
