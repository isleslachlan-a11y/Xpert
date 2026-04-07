"""
Meridian -- Sanitary drainage pipe sizing calculator.
Standard: AS 3500.2 (current edition), Discharge Drainage Unit (DDU) method.

Key references:
  - Table 3.1: DDU values by fixture type
  - Table 3.2: DDU total to design flow rate conversion
  - Cl. 3.3:   Minimum grades by pipe diameter
  - DDU method: fixtures converted to DDU load -> design flow (L/s) -> pipe size

Minimum grades per AS 3500.2 Cl. 3.3:
  DN65:  1 in 40  (2.50%)
  DN80:  1 in 60  (1.67%)
  DN100: 1 in 60  (1.67%)
  DN150: 1 in 100 (1.00%)
  DN225: 1 in 150 (0.67%)
"""

from __future__ import annotations

import math

# ── Table 3.1 -- Fixture DDU values (AS 3500.2) ──────────────────────────────

FIXTURE_DDU: dict[str, float] = {
    "wc_private":          6,
    "wc_public":           8,
    "basin_private":       1,
    "basin_public":        2,
    "bath":                3,
    "shower":              2,
    "sink_domestic":       3,
    "sink_commercial":     4,
    "dishwasher_domestic": 3,
    "washing_machine":     3,
    "urinal_flush":        2,
    "floor_waste":         1,
    "cleaners_sink":       3,
}

# ── Table 3.2 -- DDU to design flow (AS 3500.2) ──────────────────────────────
# Format: (total_ddu, design_flow_ls)

DRAIN_FLOW_TABLE: list[tuple[float, float]] = [
    (1,    0.4),
    (3,    0.6),
    (6,    0.8),
    (10,   1.0),
    (15,   1.2),
    (20,   1.4),
    (25,   1.6),
    (30,   1.8),
    (40,   2.1),
    (50,   2.4),
    (75,   2.9),
    (100,  3.3),
    (150,  4.0),
    (200,  4.6),
    (300,  5.6),
    (400,  6.4),
    (500,  7.1),
]

# ── Standard drain pipe sizes and minimum grades (AS 3500.2 Cl. 3.3) ─────────
# Format: (nominal_size_mm, internal_diameter_mm, min_grade_percent, manning_n)

class _DrainPipe:
    __slots__ = ("dn", "id_mm", "min_grade_pct", "n")

    def __init__(self, dn: int, id_mm: float, min_grade_pct: float, n: float = 0.011):
        self.dn = dn
        self.id_mm = id_mm
        self.min_grade_pct = min_grade_pct
        self.n = n  # Manning's n for uPVC


DRAIN_SIZES: list[_DrainPipe] = [
    # min_grade_pct stored as exact fractions to avoid floating-point comparison errors
    # e.g. 1/60 = 0.016666... -> 1.6666...% stored as 100/60 = 1.6666...
    _DrainPipe(65,  63.0,  100/40),   # 1 in 40  = 2.500%
    _DrainPipe(80,  78.0,  100/60),   # 1 in 60  = 1.6666...%
    _DrainPipe(100, 97.0,  100/60),   # 1 in 60  = 1.6666...%
    _DrainPipe(150, 147.0, 100/100),  # 1 in 100 = 1.000%
    _DrainPipe(225, 220.0, 100/150),  # 1 in 150 = 0.6666...%
    _DrainPipe(300, 294.0, 100/200),  # 1 in 200 = 0.500%
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ddu_to_flow(total_ddu: float) -> float:
    """Interpolate AS 3500.2 Table 3.2 to get design flow in L/s."""
    if total_ddu <= DRAIN_FLOW_TABLE[0][0]:
        return DRAIN_FLOW_TABLE[0][1]
    if total_ddu >= DRAIN_FLOW_TABLE[-1][0]:
        return DRAIN_FLOW_TABLE[-1][1]
    for i in range(len(DRAIN_FLOW_TABLE) - 1):
        d_lo, q_lo = DRAIN_FLOW_TABLE[i]
        d_hi, q_hi = DRAIN_FLOW_TABLE[i + 1]
        if d_lo <= total_ddu <= d_hi:
            frac = (total_ddu - d_lo) / (d_hi - d_lo)
            return q_lo + frac * (q_hi - q_lo)
    return DRAIN_FLOW_TABLE[-1][1]


def _manning_capacity_ls(pipe: _DrainPipe, grade_pct: float) -> tuple[float, float]:
    """Return (capacity_ls, velocity_ms) at full bore via Manning's equation."""
    d_m = pipe.id_mm / 1000.0
    area = math.pi * (d_m / 2) ** 2
    r = d_m / 4.0  # hydraulic radius
    s = grade_pct / 100.0
    v = (1.0 / pipe.n) * (r ** (2.0 / 3.0)) * (s ** 0.5)
    q_ls = area * v * 1000.0
    return q_ls, v


# ── Core calculation functions ─────────────────────────────────────────────────

def calculate_fixture_ddu(fixtures: dict[str, int]) -> dict:
    """Sum Discharge Drainage Units from a fixture schedule per AS 3500.2 Table 3.1.

    Args:
        fixtures: Mapping of fixture type to count.

    Returns:
        Dict with keys: ``total_ddu``, ``breakdown``.

    Raises:
        ValueError: For unknown fixture types.
    """
    unknown = [k for k in fixtures if k not in FIXTURE_DDU]
    if unknown:
        valid = ", ".join(sorted(FIXTURE_DDU))
        raise ValueError(f"Unknown fixture type(s): {', '.join(unknown)}. Valid: {valid}")

    total = 0.0
    breakdown: dict[str, tuple[int, float, float]] = {}
    for ftype, count in fixtures.items():
        if count <= 0:
            continue
        ddu_each = FIXTURE_DDU[ftype]
        subtotal = ddu_each * count
        breakdown[ftype] = (count, ddu_each, subtotal)
        total += subtotal

    return {"total_ddu": round(total, 1), "breakdown": breakdown}


def calculate_drain_size(
    total_ddu: float,
    grade_fraction: float,
    pipe_length_m: float,
) -> dict:
    """Size a sanitary drain using the AS 3500.2 DDU method.

    Selects the smallest pipe that:
    (a) has sufficient capacity (Manning's equation, full bore), and
    (b) meets or exceeds the minimum grade for that diameter [Cl. 3.3].

    ``grade_fraction`` is the hydraulic gradient as a decimal
    (e.g. 1 in 60 = 0.01667). Internally converted to a percentage.

    Args:
        total_ddu: Total Discharge Drainage Units (sum of Table 3.1 values).
        grade_fraction: Hydraulic gradient as a fraction (e.g. 0.01667 for 1:60).
        pipe_length_m: Pipe length in metres (used for context in result only;
                       drainage sizing is flow-limited, not pressure-limited).

    Returns:
        Dict with keys: ``total_ddu``, ``design_flow_ls``, ``grade_fraction``,
        ``grade_ratio``, ``selected_dn``, ``capacity_ls``, ``velocity_ms``,
        ``min_grade_pct``, ``grade_compliant``, ``capacity_compliant``,
        ``compliant``, ``clause_ref``.

    Raises:
        ValueError: If inputs are out of range.
    """
    if total_ddu <= 0:
        raise ValueError(f"total_ddu must be positive, got {total_ddu}")
    if grade_fraction <= 0:
        raise ValueError(f"grade_fraction must be positive, got {grade_fraction}")
    if pipe_length_m <= 0:
        raise ValueError(f"pipe_length_m must be positive, got {pipe_length_m}")

    grade_pct = grade_fraction * 100.0
    grade_ratio = round(1.0 / grade_fraction)
    design_flow_ls = _ddu_to_flow(total_ddu)

    last: dict | None = None

    for pipe in DRAIN_SIZES:
        capacity_ls, velocity_ms = _manning_capacity_ls(pipe, grade_pct)
        grade_ok = grade_pct >= pipe.min_grade_pct
        cap_ok = capacity_ls >= design_flow_ls

        result = {
            "total_ddu": total_ddu,
            "design_flow_ls": round(design_flow_ls, 2),
            "grade_fraction": grade_fraction,
            "grade_pct": round(grade_pct, 3),
            "grade_ratio": f"1 in {grade_ratio}",
            "pipe_length_m": pipe_length_m,
            "selected_dn": pipe.dn,
            "id_mm": pipe.id_mm,
            "capacity_ls": round(capacity_ls, 2),
            "velocity_ms": round(velocity_ms, 3),
            "min_grade_pct": pipe.min_grade_pct,
            "min_grade_ratio": f"1 in {round(100.0 / pipe.min_grade_pct)}",
            "grade_compliant": grade_ok,
            "capacity_compliant": cap_ok,
            "compliant": grade_ok and cap_ok,
            "clause_ref": "AS 3500.2 Table 3.1, Table 3.2, Cl. 3.3",
        }
        last = result

        if grade_ok and cap_ok:
            return result

    # Return largest size with compliant=False
    assert last is not None
    last["compliant"] = False
    return last


def format_drainage_result(result: dict) -> str:
    """Format a drainage sizing result as a professional calculation note.

    Args:
        result: Output of ``calculate_drain_size``.

    Returns:
        Multi-line formatted string.
    """
    status = "COMPLIANT" if result["compliant"] else "NON-COMPLIANT"
    issues: list[str] = []
    if not result["grade_compliant"]:
        issues.append(
            f"grade {result['grade_ratio']} is less than minimum "
            f"{result['min_grade_ratio']} for DN{result['selected_dn']} [Cl. 3.3]"
        )
    if not result["capacity_compliant"]:
        issues.append(
            f"capacity {result['capacity_ls']:.2f} L/s < "
            f"design flow {result['design_flow_ls']:.2f} L/s"
        )

    lines: list[str] = [
        "## Sanitary Drainage Sizing -- AS 3500.2",
        "",
        "### Inputs  [AS 3500.2 DDU Method]",
        f"  Total DDU:       {result['total_ddu']:.1f}  [AS 3500.2 Table 3.1]",
        f"  Design flow:     {result['design_flow_ls']:.2f} L/s  [Table 3.2 interpolation]",
        f"  Grade:           {result['grade_ratio']} ({result['grade_pct']:.3f}%)",
        f"  Pipe length:     {result['pipe_length_m']:.1f} m",
        "",
        "### Selected Pipe",
        f"  Nominal size:    DN{result['selected_dn']}",
        f"  Internal dia:    {result['id_mm']:.0f} mm",
        f"  Full-bore cap:   {result['capacity_ls']:.2f} L/s  (Manning's equation, n=0.011)",
        f"  Velocity:        {result['velocity_ms']:.3f} m/s",
        f"  Min grade:       {result['min_grade_ratio']} ({result['min_grade_pct']:.2f}%)  "
        f"[AS 3500.2 Cl. 3.3]",
        "",
        f"### {status}",
    ]

    if result["compliant"]:
        lines.append(
            f"  DN{result['selected_dn']} at {result['grade_ratio']} grade carries "
            f"{result['design_flow_ls']:.2f} L/s with {result['capacity_ls']:.2f} L/s capacity."
        )
    else:
        for issue in issues:
            lines.append(f"  - {issue}")

    lines.append(f"\n  [{result['clause_ref']}]")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print("Meridian -- Drainage Sizing Worked Example")
    print("AS 3500.2 DDU Method")
    print("=" * 60)

    # Example: 4-bathroom floor (4 WC + 4 basin + 4 shower), 1:60 grade
    fixtures = {"wc_private": 4, "basin_private": 4, "shower": 4}
    ddu_result = calculate_fixture_ddu(fixtures)
    print(f"\nFixtures: {fixtures}")
    print(f"Total DDU: {ddu_result['total_ddu']}")

    result = calculate_drain_size(
        total_ddu=ddu_result["total_ddu"],
        grade_fraction=1/60,
        pipe_length_m=15.0,
    )
    print()
    print(format_drainage_result(result))
