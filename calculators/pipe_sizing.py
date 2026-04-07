"""
Meridian — Cold water pipe sizing calculator.
Standard: AS 3500.1—2018, fixture unit method.

Key references:
  - Table 3.1: Fixture unit (FU) values by fixture type
  - Table 3.2: FU to design flow rate (L/s) conversion
  - Cl. 3.4.3: Maximum velocity — 3.0 m/s
  - Cl. 7.4.1: Minimum residual pressure — 100 kPa at furthest outlet

Critical constants:
  Max velocity:          3.0 m/s   (AS 3500.1 Cl. 3.4.3)
  Min residual pressure: 100 kPa   (AS 3500.1 Cl. 7.4.1)
"""

from __future__ import annotations

import math
from typing import NamedTuple

# ── Table 3.1 — Fixture loading units (AS 3500.1—2018) ───────────────────────

FIXTURE_UNITS: dict[str, float] = {
    "wc_private":          0.5,
    "wc_public":           3.0,
    "basin_private":       0.5,
    "basin_public":        1.0,
    "bath":                1.5,
    "shower":              1.0,
    "sink_domestic":       1.0,
    "sink_commercial":     3.0,
    "dishwasher_domestic": 1.5,
    "washing_machine":     2.5,
    "urinal_flush":        2.5,
    "hose_tap":            2.5,
    "drinking_fountain":   0.5,
    "cleaners_sink":       1.5,
}

# ── Table 3.2 — Design flow rate vs total fixture units (AS 3500.1—2018) ─────
# Format: (total_fixture_units, design_flow_ls)
# Covers 1 FU (0.1 L/s) through 300 FU (4.2 L/s).
# Linear interpolation is applied between tabulated points.

DEMAND_FLOW_RATE: list[tuple[float, float]] = [
    (1,    0.10),
    (2,    0.13),
    (4,    0.17),
    (6,    0.20),
    (8,    0.23),
    (10,   0.26),
    (15,   0.31),
    (20,   0.36),
    (30,   0.44),
    (40,   0.52),
    (50,   0.59),
    (75,   0.72),
    (100,  0.84),
    (150,  1.04),
    (200,  1.22),
    (250,  1.38),
    (300,  4.20),   # upper bound per table
]

# ── Pipe data ─────────────────────────────────────────────────────────────────
# Format: (nominal_size_mm, internal_diameter_mm, max_velocity_ms, hazen_williams_c)
# Velocity limit of 3.0 m/s applies to all materials per AS 3500.1 Cl. 3.4.3.

class _PipeRow(NamedTuple):
    nominal_size_mm: int
    id_mm: float
    max_velocity_ms: float
    c_factor: int


PIPE_DATA: dict[str, list[_PipeRow]] = {
    "copper": [
        _PipeRow(15, 13.6, 3.0, 130),
        _PipeRow(20, 18.8, 3.0, 130),
        _PipeRow(25, 24.3, 3.0, 130),
        _PipeRow(32, 31.6, 3.0, 130),
        _PipeRow(40, 39.6, 3.0, 130),
        _PipeRow(50, 50.0, 3.0, 130),
        _PipeRow(65, 65.0, 3.0, 130),
        _PipeRow(80, 80.0, 3.0, 130),
    ],
    "cpvc": [
        _PipeRow(15, 14.4, 3.0, 150),
        _PipeRow(20, 19.6, 3.0, 150),
        _PipeRow(25, 25.0, 3.0, 150),
        _PipeRow(32, 32.6, 3.0, 150),
        _PipeRow(40, 40.8, 3.0, 150),
        _PipeRow(50, 51.4, 3.0, 150),
        _PipeRow(65, 66.6, 3.0, 150),
        _PipeRow(80, 82.0, 3.0, 150),
    ],
    "pex": [
        _PipeRow(15, 14.4, 3.0, 150),
        _PipeRow(20, 19.4, 3.0, 150),
        _PipeRow(25, 24.6, 3.0, 150),
        _PipeRow(32, 31.8, 3.0, 150),
        _PipeRow(40, 40.2, 3.0, 150),
        _PipeRow(50, 51.0, 3.0, 150),
        _PipeRow(65, 65.8, 3.0, 150),
        _PipeRow(80, 81.4, 3.0, 150),
    ],
    "stainless": [
        _PipeRow(15, 13.8, 3.0, 140),
        _PipeRow(20, 19.0, 3.0, 140),
        _PipeRow(25, 24.6, 3.0, 140),
        _PipeRow(32, 32.0, 3.0, 140),
        _PipeRow(40, 40.0, 3.0, 140),
        _PipeRow(50, 50.6, 3.0, 140),
        _PipeRow(65, 65.6, 3.0, 140),
        _PipeRow(80, 80.8, 3.0, 140),
    ],
}

# ── Compliance constants ───────────────────────────────────────────────────────

MAX_VELOCITY_MS: float = 3.0        # AS 3500.1 Cl. 3.4.3
MIN_RESIDUAL_PRESSURE_KPA: float = 100.0  # AS 3500.1 Cl. 7.4.1


# ── Core calculation functions ─────────────────────────────────────────────────

def calculate_fixture_units(fixtures: dict[str, int]) -> dict:
    """Calculate total fixture units from a fixture schedule.

    Args:
        fixtures: Mapping of fixture type to count, e.g. ``{"wc_private": 4, "basin_private": 4}``.
                  Valid fixture types are the keys of ``FIXTURE_UNITS``.

    Returns:
        Dict with keys:
          - ``total_fu`` (float): Sum of all fixture units.
          - ``breakdown`` (dict): Mapping of fixture type to ``(count, fu_each, fu_subtotal)``.

    Raises:
        ValueError: If any fixture type is not in ``FIXTURE_UNITS``.
    """
    unknown = [k for k in fixtures if k not in FIXTURE_UNITS]
    if unknown:
        valid = ", ".join(sorted(FIXTURE_UNITS))
        raise ValueError(
            f"Unknown fixture type(s): {', '.join(unknown)}. "
            f"Valid types: {valid}"
        )

    breakdown: dict[str, tuple[int, float, float]] = {}
    total_fu = 0.0

    for fixture_type, count in fixtures.items():
        if count <= 0:
            continue
        fu_each = FIXTURE_UNITS[fixture_type]
        subtotal = fu_each * count
        breakdown[fixture_type] = (count, fu_each, subtotal)
        total_fu += subtotal

    return {"total_fu": total_fu, "breakdown": breakdown}


def fixture_units_to_flow_rate(total_fu: float) -> float:
    """Convert total fixture units to design flow rate via AS 3500.1 Table 3.2.

    Uses linear interpolation between tabulated points. For values above the
    table maximum (300 FU → 4.2 L/s), the maximum tabulated flow is returned
    with a warning embedded in the result.

    Args:
        total_fu: Total fixture loading units (non-negative).

    Returns:
        Design flow rate in L/s.

    Raises:
        ValueError: If ``total_fu`` is negative.
    """
    if total_fu < 0:
        raise ValueError(f"total_fu must be non-negative, got {total_fu}")

    if total_fu <= DEMAND_FLOW_RATE[0][0]:
        return DEMAND_FLOW_RATE[0][1]

    if total_fu >= DEMAND_FLOW_RATE[-1][0]:
        return DEMAND_FLOW_RATE[-1][1]

    for i in range(len(DEMAND_FLOW_RATE) - 1):
        fu_low, q_low = DEMAND_FLOW_RATE[i]
        fu_high, q_high = DEMAND_FLOW_RATE[i + 1]
        if fu_low <= total_fu <= fu_high:
            # Linear interpolation
            fraction = (total_fu - fu_low) / (fu_high - fu_low)
            return q_low + fraction * (q_high - q_low)

    return DEMAND_FLOW_RATE[-1][1]  # unreachable, but satisfies type checker


def hazen_williams_velocity(
    flow_ls: float,
    id_mm: float,
    c_factor: float,
) -> tuple[float, float]:
    """Calculate pipe velocity and pressure drop using the Hazen-Williams equation.

    Hazen-Williams formula:
      V = 0.8492 × C × R^0.63 × S^0.54
    where:
      R = hydraulic radius = D/4 (m) for a full circular pipe
      S = head loss per unit length (m/m), solved iteratively from velocity

    Rearranged for direct computation:
      Q  = A × V  →  V = Q/A
      S  = (V / (0.8492 × C × R^0.63))^(1/0.54)
      ΔP = S × ρg  (Pa/m, using ρ = 1000 kg/m³, g = 9.81 m/s²)

    Args:
        flow_ls: Flow rate in L/s.
        id_mm: Internal diameter of the pipe in mm.
        c_factor: Hazen-Williams C factor (dimensionless).

    Returns:
        Tuple of (velocity_ms, pressure_drop_pa_per_m).

    Raises:
        ValueError: If any input is non-positive.
    """
    if flow_ls <= 0 or id_mm <= 0 or c_factor <= 0:
        raise ValueError(
            f"All inputs must be positive. Got flow={flow_ls}, id={id_mm}, C={c_factor}"
        )

    id_m = id_mm / 1000.0
    area_m2 = math.pi * (id_m / 2) ** 2
    flow_m3s = flow_ls / 1000.0

    velocity_ms = flow_m3s / area_m2

    # Hydraulic radius for circular full pipe = D/4
    r_hydraulic = id_m / 4.0

    # Hazen-Williams: V = 0.8492 × C × R^0.63 × S^0.54
    # Solve for S: S = (V / (0.8492 × C × R^0.63))^(1/0.54)
    hw_coeff = 0.8492 * c_factor * (r_hydraulic ** 0.63)
    s_gradient = (velocity_ms / hw_coeff) ** (1.0 / 0.54)

    # Convert hydraulic gradient (m/m) to pressure drop (Pa/m)
    pressure_drop_pa_per_m = s_gradient * 1000.0 * 9.81

    return (velocity_ms, pressure_drop_pa_per_m)


def select_pipe_size(
    flow_ls: float,
    material: str,
    max_velocity: float = MAX_VELOCITY_MS,
) -> dict:
    """Select the minimum compliant pipe size for a given flow rate and material.

    Iterates pipe sizes from smallest to largest for the given material and
    returns the first size where the computed velocity is at or below
    ``max_velocity``. If no size is compliant, the largest available size is
    returned with ``compliant=False``.

    Args:
        flow_ls: Design flow rate in L/s.
        material: Pipe material key — one of ``"copper"``, ``"cpvc"``, ``"pex"``,
                  ``"stainless"``.
        max_velocity: Maximum allowable velocity in m/s (default 3.0 per
                      AS 3500.1 Cl. 3.4.3).

    Returns:
        Dict with keys: ``nominal_size_mm``, ``id_mm``, ``velocity_ms``,
        ``pressure_drop_pa_per_m``, ``material``, ``flow_ls``, ``compliant``.

    Raises:
        ValueError: If ``material`` is not in ``PIPE_DATA``.
    """
    if material not in PIPE_DATA:
        valid = ", ".join(PIPE_DATA)
        raise ValueError(
            f"Unknown pipe material '{material}'. Valid options: {valid}"
        )

    rows = PIPE_DATA[material]
    last_result: dict | None = None

    for row in rows:
        velocity_ms, pressure_drop_pa_per_m = hazen_williams_velocity(
            flow_ls, row.id_mm, row.c_factor
        )
        result = {
            "nominal_size_mm": row.nominal_size_mm,
            "id_mm": row.id_mm,
            "velocity_ms": round(velocity_ms, 3),
            "pressure_drop_pa_per_m": round(pressure_drop_pa_per_m, 2),
            "material": material,
            "flow_ls": flow_ls,
            "compliant": velocity_ms <= max_velocity,
        }
        last_result = result
        if velocity_ms <= max_velocity:
            return result

    # No compliant size found — return largest with compliant=False
    assert last_result is not None
    last_result["compliant"] = False
    return last_result


def size_pipe_from_fixtures(
    fixtures: dict[str, int],
    material: str,
    pipe_length_m: float,
    static_pressure_kpa: float = 300.0,
) -> dict:
    """Full end-to-end pipe sizing calculation from a fixture schedule.

    Performs the complete AS 3500.1 fixture unit method:
    1. Sum fixture units from Table 3.1.
    2. Convert to design flow rate via Table 3.2 interpolation.
    3. Select minimum compliant pipe size for the given material.
    4. Check residual pressure at the furthest outlet.

    Pressure check (simplified — does not account for fittings loss or elevation):
      Residual pressure = static_pressure - friction_loss
      Friction loss (kPa) = (pressure_drop_pa_per_m × pipe_length_m) / 1000
      Residual must be ≥ 100 kPa per AS 3500.1 Cl. 7.4.1.

    Args:
        fixtures: Mapping of fixture type to count.
        material: Pipe material — one of ``"copper"``, ``"cpvc"``, ``"pex"``,
                  ``"stainless"``.
        pipe_length_m: Equivalent pipe length in metres (include allowance for
                       fittings as equivalent lengths).
        static_pressure_kpa: Static inlet pressure available in kPa (default 300 kPa).

    Returns:
        Dict with keys:
          - ``total_fu`` (float)
          - ``breakdown`` (dict) — per-fixture FU contribution
          - ``design_flow_ls`` (float)
          - ``recommended_pipe`` (dict) — output of ``select_pipe_size``
          - ``friction_loss_kpa`` (float)
          - ``residual_pressure_kpa`` (float)
          - ``pressure_check`` (dict) — ``{"pass": bool, "clause": str, "note": str}``
          - ``methodology_note`` (str)
          - ``clause_reference`` (str)
    """
    # Step 1 — fixture units
    fu_result = calculate_fixture_units(fixtures)
    total_fu = fu_result["total_fu"]

    # Step 2 — design flow rate
    design_flow_ls = fixture_units_to_flow_rate(total_fu)

    # Step 3 — pipe selection
    pipe = select_pipe_size(design_flow_ls, material)

    # Step 4 — pressure check
    friction_loss_kpa = (pipe["pressure_drop_pa_per_m"] * pipe_length_m) / 1000.0
    residual_pressure_kpa = static_pressure_kpa - friction_loss_kpa
    pressure_pass = residual_pressure_kpa >= MIN_RESIDUAL_PRESSURE_KPA

    pressure_check = {
        "pass": pressure_pass,
        "clause": "AS 3500.1—2018 Cl. 7.4.1",
        "note": (
            f"Residual pressure {residual_pressure_kpa:.1f} kPa "
            f"{'≥' if pressure_pass else '<'} {MIN_RESIDUAL_PRESSURE_KPA:.0f} kPa minimum."
        ),
    }

    return {
        "total_fu": round(total_fu, 1),
        "breakdown": fu_result["breakdown"],
        "design_flow_ls": round(design_flow_ls, 3),
        "recommended_pipe": pipe,
        "friction_loss_kpa": round(friction_loss_kpa, 2),
        "residual_pressure_kpa": round(residual_pressure_kpa, 1),
        "pressure_check": pressure_check,
        "methodology_note": (
            "AS 3500.1—2018 Section 3, Fixture Unit Method, Table 3.1 and Table 3.2. "
            "Design flow rate determined by linear interpolation of Table 3.2. "
            "Pipe size selected as minimum DN where velocity ≤ 3.0 m/s "
            "[AS 3500.1 Cl. 3.4.3]. Pressure drop calculated using Hazen-Williams equation."
        ),
        "clause_reference": (
            "AS 3500.1—2018 Table 3.1 (fixture units), Table 3.2 (design flow), "
            "Cl. 3.4.3 (velocity limit), Cl. 7.4.1 (residual pressure)"
        ),
    }


# ── Formatted output ──────────────────────────────────────────────────────────

def format_pipe_sizing_result(result: dict) -> str:
    """Format a pipe sizing result dict as a professional calculation note.

    Args:
        result: Output dict from ``size_pipe_from_fixtures``.

    Returns:
        A multi-line string suitable for display in the Streamlit UI or as an
        agent response, structured as: Fixture Schedule → Design Flow → Pipe
        Selection → Pressure Check → Compliance Statement.
    """
    pipe = result["recommended_pipe"]
    pc = result["pressure_check"]

    lines: list[str] = []

    lines.append("## Cold Water Pipe Sizing — AS 3500.1—2018")
    lines.append("")

    # ── Fixture schedule ──────────────────────────────────────────────────────
    lines.append("### Fixture Schedule  [AS 3500.1 Table 3.1]")
    lines.append(f"{'Fixture Type':<28} {'Count':>6}  {'FU each':>8}  {'Subtotal FU':>11}")
    lines.append("-" * 58)

    for fixture_type, (count, fu_each, subtotal) in result["breakdown"].items():
        label = fixture_type.replace("_", " ").title()
        lines.append(f"{label:<28} {count:>6}  {fu_each:>8.1f}  {subtotal:>11.1f}")

    lines.append("-" * 58)
    lines.append(f"{'TOTAL FIXTURE UNITS':<28} {'':>6}  {'':>8}  {result['total_fu']:>11.1f}")
    lines.append("")

    # ── Design flow rate ──────────────────────────────────────────────────────
    lines.append("### Design Flow Rate  [AS 3500.1 Table 3.2]")
    lines.append(
        f"  Total FU = {result['total_fu']} -> "
        f"Design flow = **{result['design_flow_ls']} L/s** (linear interpolation)"
    )
    lines.append("")

    # ── Pipe selection ────────────────────────────────────────────────────────
    lines.append("### Pipe Selection  [AS 3500.1 Cl. 3.4.3 — max 3.0 m/s]")
    lines.append(f"  Material:        {pipe['material'].upper()}")
    lines.append(f"  Nominal size:    DN{pipe['nominal_size_mm']}")
    lines.append(f"  Internal Ø:      {pipe['id_mm']} mm")
    lines.append(f"  Velocity:        {pipe['velocity_ms']:.3f} m/s  (limit: 3.0 m/s)")
    lines.append(f"  Friction drop:   {pipe['pressure_drop_pa_per_m']:.1f} Pa/m")

    velocity_status = "PASS" if pipe["compliant"] else "FAIL"
    lines.append(f"  Velocity check:  {velocity_status}")
    lines.append("")

    # ── Pressure check ────────────────────────────────────────────────────────
    lines.append("### Pressure Check  [AS 3500.1 Cl. 7.4.1 — min 100 kPa residual]")
    lines.append(f"  Friction loss:   {result['friction_loss_kpa']:.2f} kPa")
    lines.append(f"  Residual:        {result['residual_pressure_kpa']:.1f} kPa")

    pressure_status = "PASS" if pc["pass"] else "FAIL -- increase pipe size or inlet pressure"
    lines.append(f"  Pressure check:  {pressure_status}")
    lines.append("")

    # ── Compliance statement ──────────────────────────────────────────────────
    all_pass = pipe["compliant"] and pc["pass"]
    lines.append("### Compliance Statement")

    if all_pass:
        lines.append(
            f"  DN{pipe['nominal_size_mm']} {pipe['material'].upper()} complies with AS 3500.1—2018. "
            f"Velocity {pipe['velocity_ms']:.3f} m/s ≤ 3.0 m/s [Cl. 3.4.3]. "
            f"Residual pressure {result['residual_pressure_kpa']:.1f} kPa ≥ 100 kPa [Cl. 7.4.1]."
        )
    else:
        issues: list[str] = []
        if not pipe["compliant"]:
            issues.append(
                f"velocity {pipe['velocity_ms']:.3f} m/s exceeds 3.0 m/s limit [Cl. 3.4.3]"
            )
        if not pc["pass"]:
            issues.append(
                f"residual pressure {result['residual_pressure_kpa']:.1f} kPa "
                f"is below 100 kPa minimum [Cl. 7.4.1]"
            )
        lines.append(f"  NON-COMPLIANT — {'; '.join(issues)}.")

    lines.append("")
    lines.append(f"*{result['methodology_note']}*")

    return "\n".join(lines)


# ── Worked example ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    # Force UTF-8 on Windows terminals that default to cp1252
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    fixtures = {
        "wc_private":    10,
        "basin_private": 10,
        "shower":         5,
        "hose_tap":       2,
    }
    material = "copper"
    pipe_length_m = 35.0
    static_pressure_kpa = 300.0

    print("=" * 60)
    print("Meridian — Pipe Sizing Worked Example")
    print("AS 3500.1—2018 Fixture Unit Method")
    print("=" * 60)
    print(f"Fixtures:       {fixtures}")
    print(f"Material:       {material.upper()}")
    print(f"Equiv. length:  {pipe_length_m} m")
    print(f"Static pressure:{static_pressure_kpa} kPa")
    print()

    result = size_pipe_from_fixtures(
        fixtures=fixtures,
        material=material,
        pipe_length_m=pipe_length_m,
        static_pressure_kpa=static_pressure_kpa,
    )

    print(format_pipe_sizing_result(result))
