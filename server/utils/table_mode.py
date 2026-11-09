"""Request-level table policy. Missing modes keep the legacy engine behavior."""

TABLE_MODES = ("preserve", "fixed")


def parse_table_mode(value):
    if value is None or value == "":
        return None
    if value not in TABLE_MODES:
        raise ValueError(
            "Unsupported tableMode. Available modes: preserve, fixed. "
            "Adaptive table layout is not implemented yet."
        )
    return value
