"""Toolkit-independent grouping of resource summary details."""

_INFO_SECTION_RULES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "gpu": (
        ("Hardware", ()),
        ("Status", ("Temperature", "GPU usage", "Memory", "Driver", "Metal")),
    ),
    "network": (
        (
            "Traffic",
            ("Download rate", "Upload rate", "Received this boot", "Sent this boot"),
        ),
        ("Interface", ("Active interface", "VPN")),
    ),
    "battery": (
        (
            "Battery",
            ("Charge", "Power", "Time remaining", "Battery", "CPU", "GPU", "NVMe"),
        ),
    ),
}


def action_label_text(actionable: bool) -> str:
    """Return the card action label for one summary's actionable flag."""

    return "Review and clean  →" if actionable else "View details  →"


def metric_label_pairs(
    details: tuple[str, ...],
    value: str,
) -> tuple[tuple[str, str], ...]:
    """Return labelled detail rows, omitting the headline value."""

    pairs: list[tuple[str, str]] = []
    for line in details:
        if line == value:
            continue
        label, separator, line_value = line.partition(": ")
        pairs.append((label, line_value) if separator else ("", line))
    return tuple(pairs)


def detail_sections(
    key: str,
    details: tuple[str, ...],
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    """Group detail lines into titled sections without importing a UI toolkit.

    Known labels are placed in their category-specific section. Unprefixed
    lines belong to the first section, and unknown prefixed lines go into a
    trailing ``Details`` section. Unknown categories get only that section.
    """

    rules = _INFO_SECTION_RULES.get(key, ())
    buckets: list[list[tuple[str, str]]] = [[] for _ in range(len(rules) + 1)]
    for line in details:
        prefix, separator, value = line.partition(": ")
        if not separator:
            buckets[0 if rules else -1].append(("", line))
            continue
        for index, (_title, prefixes) in enumerate(rules):
            if prefix in prefixes:
                buckets[index].append((prefix, value))
                break
        else:
            buckets[-1].append((prefix, value))

    sections: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for (title, _prefixes), rows in zip(rules, buckets):
        if rows:
            sections.append((title, tuple(rows)))
    if buckets[-1]:
        sections.append(("Details", tuple(buckets[-1])))
    return tuple(sections)
