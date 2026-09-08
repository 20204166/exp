"""Immutable metadata catalog for dashboard resource features."""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResourceFeature:
    """Immutable metadata for one dashboard resource category.

    The catalog describes metadata only; it never imports or calls scanners,
    handlers, widgets, or destructive actions.
    """

    key: str
    title: str
    order: int
    action_kind: str
    platforms: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not self.key or not self.title or not self.action_kind:
            raise ValueError("Resource feature metadata fields cannot be empty")
        if self.order < 0:
            raise ValueError("Resource feature order cannot be negative")

        if self.platforms is not None:
            platforms = tuple(self.platforms)
            if not platforms or any(not platform for platform in platforms):
                raise ValueError("Resource feature platforms cannot be empty")
            object.__setattr__(self, "platforms", platforms)

    def is_available_on(self, platform_name: str) -> bool:
        """Return whether this feature is declared for a platform."""

        if self.platforms is None:
            return True
        normalized_platform = platform_name.casefold()
        return any(
            platform.casefold() == normalized_platform for platform in self.platforms
        )


class ResourceFeatureCatalog:
    """Own isolated, deterministic metadata for dashboard resource features.

    The default entries mirror the current dashboard. Registering a feature
    extends one catalog instance only, so future feature experiments cannot
    mutate another window or a process-wide registry by accident.
    """

    DEFAULT_FEATURES: tuple[ResourceFeature, ...] = (
        ResourceFeature("cpu", "CPU", 0, "process"),
        ResourceFeature("memory", "Memory", 1, "process"),
        ResourceFeature("storage", "Storage", 2, "storage"),
        ResourceFeature("gpu", "GPU", 3, "informational"),
        ResourceFeature("network", "Network", 4, "informational"),
        ResourceFeature("battery", "Battery", 5, "informational"),
    )

    def __init__(
        self,
        features: Iterable[ResourceFeature] | None = None,
    ) -> None:
        self._features: dict[str, ResourceFeature] = {}
        for feature in self.DEFAULT_FEATURES if features is None else features:
            self.register(feature)

    def all(self) -> tuple[ResourceFeature, ...]:
        """Return features in deterministic display order."""

        return tuple(
            sorted(
                self._features.values(),
                key=lambda feature: (feature.order, feature.key),
            )
        )

    def get(self, key: str) -> ResourceFeature:
        """Return one feature or raise a clear error for an unknown key."""

        try:
            return self._features[key]
        except KeyError as error:
            raise KeyError(f"Unknown resource feature: {key}") from error

    def title_for(self, key: str) -> str | None:
        """Return one feature's display title, or None for an unknown key.

        The fallback-friendly lookup used by the dashboard and scanner when
        the caller must keep working for keys outside the catalog.
        """

        feature = self._features.get(key)
        return feature.title if feature is not None else None

    def register(self, feature: ResourceFeature) -> None:
        """Register one immutable feature, rejecting duplicate keys."""

        if not isinstance(feature, ResourceFeature):
            raise TypeError("feature must be a ResourceFeature")
        if feature.key in self._features:
            raise ValueError(f"Resource feature already registered: {feature.key}")
        self._features[feature.key] = feature

    def available_on(self, platform_name: str) -> tuple[ResourceFeature, ...]:
        """Return the ordered features declared for one platform."""

        return tuple(
            feature for feature in self.all() if feature.is_available_on(platform_name)
        )
