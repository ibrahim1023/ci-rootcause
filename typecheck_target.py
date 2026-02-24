def sentinel_value() -> int:
    value: int = "7"  # type: ignore[assignment]
    return value
