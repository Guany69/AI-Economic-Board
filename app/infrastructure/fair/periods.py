"""Quarter-period helpers. Canonical period format: '2026Q3'."""


def quarter_seq_ending(end: str, count: int) -> list[str]:
    """Return `count` consecutive quarters ending at `end` (inclusive)."""
    year, q = int(end[:4]), int(end[5])
    seq: list[str] = []
    for _ in range(count):
        seq.append(f"{year}Q{q}")
        q -= 1
        if q == 0:
            year, q = year - 1, 4
    return list(reversed(seq))


def quarter_range(start: str, end: str) -> list[str]:
    year, q = int(start[:4]), int(start[5])
    ey, eq = int(end[:4]), int(end[5])
    seq: list[str] = []
    while (year, q) <= (ey, eq):
        seq.append(f"{year}Q{q}")
        q += 1
        if q == 5:
            year, q = year + 1, 1
    return seq


def to_fair_period(period: str) -> str:
    """'2026Q3' -> '2026.3' (Fair's SMPL notation)."""
    return f"{period[:4]}.{period[5]}"
