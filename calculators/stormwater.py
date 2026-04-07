"""
Meridian -- Stormwater drainage sizing calculator.
Standard: AS 3500.3 (current edition), Rational Method.

Formula: Q = C x I x A / 360
  Q -- peak design flow (L/s)
  C -- dimensionless runoff coefficient
  I -- rainfall intensity (mm/hr) for the design AEP and time of concentration
  A -- catchment area (m2)

Note on AEP vs ARI: AS 3500.3 (2018 edition) uses Annual Exceedance Probability (AEP)
  1% AEP = 1-in-100 year event (previously called 100-year ARI)
  10% AEP = 1-in-10 year event (previously called 10-year ARI)

Key references:
  - Cl. 3.2:   Rational method application
  - Table 3.1: Runoff coefficients by surface type
  - Section 4: Pipe sizing and hydraulic gradient
"""

from __future__ import annotations

import math

# ── Rainfall intensities (mm/hr) ─────────────────────────────────────────────
# Nested dict: {aep_percent: {duration_min: intensity_mm_per_hr}}
# Representative values for a temperate coastal Australian city (Sydney basis).
# For project work, obtain site-specific IFD data from the BoM IFD portal.

RAINFALL_INTENSITIES: dict[float, dict[int, float]] = {
    1.0: {   # 1% AEP (1-in-100 year)
        5:   220,
        10:  168,
        15:  142,
        20:  126,
        30:  103,
        45:   82,
        60:   69,
    },
    10.0: {  # 10% AEP (1-in-10 year)
        5:   137,
        10:  104,
        15:   88,
        20:   77,
        30:   63,
        45:   50,
        60:   42,
    },
}

# ── Runoff coefficients by surface type (AS 3500.3 Table 3.1) ─────────────────

RUNOFF_COEFFICIENTS: dict[str, float] = {
    "roof_metal":       0.95,
    "roof_tile":        0.90,
    "concrete_paving":  0.85,
    "asphalt":          0.85,
    "gravel":           0.40,
    "lawn_flat":        0.25,
    "lawn_steep":       0.35,
    "garden_bed":       0.15,
    "bushland":         0.10,
}

# ── Manning's roughness coefficients by pipe material ─────────────────────────

MANNING_N: dict[str, float] = {
    "upvc":       0.011,
    "concrete":   0.013,
    "cast_iron":  0.014,
}

# ── Standard pipe sizes to trial for auto-sizing ──────────────────────────────

STANDARD_SIZES_MM: list[int] = [100, 150, 200, 225, 300, 375, 450]


# ── Validation helpers ────────────────────────────────────────────────────────

def _nearest_duration(aep: float, tc_min: float) -> tuple[int, float]:
    """Return the nearest tabulated duration and its intensity for the given AEP.

    Uses the tabulated duration closest to ``tc_min``. If ``tc_min`` falls
    between two tabulated values the closer one is selected (conservative --
    shorter durations give higher intensity).

    Args:
        aep: Annual exceedance probability in percent (1.0 or 10.0).
        tc_min: Time of concentration in minutes.

    Returns:
        Tuple of (selected_duration_min, intensity_mm_per_hr).

    Raises:
        ValueError: If AEP is not in ``RAINFALL_INTENSITIES``.
    """
    if aep not in RAINFALL_INTENSITIES:
        valid = ", ".join(f"{k}%" for k in sorted(RAINFALL_INTENSITIES))
        raise ValueError(
            f"AEP {aep}% is not tabulated. Available: {valid}. "
            "For other AEPs obtain IFD data from the BoM IFD portal."
        )

    durations = RAINFALL_INTENSITIES[aep]
    sorted_durations = sorted(durations)

    # Clamp to table range
    if tc_min <= sorted_durations[0]:
        d = sorted_durations[0]
        return d, durations[d]
    if tc_min >= sorted_durations[-1]:
        d = sorted_durations[-1]
        return d, durations[d]

    # Find nearest (shorter duration preferred when equidistant -- conservative)
    nearest = min(sorted_durations, key=lambda d: abs(d - tc_min))
    return nearest, durations[nearest]


# ── Core calculation functions ─────────────────────────────────────────────────

def calculate_rational_method(
    catchment_area_m2: float,
    surface_type: str,
    aep_percent: float,
    time_of_concentration_min: float,
) -> dict:
    """Calculate peak stormwater flow using the Rational Method per AS 3500.3.

    Formula::

        Q (L/s) = C x I (mm/hr) x A (m2) / 360

    Rainfall intensity ``I`` is selected from ``RAINFALL_INTENSITIES`` using
    the tabulated duration nearest to the time of concentration. For project
    work, obtain site-specific IFD data from the BoM IFD portal (not the
    representative Sydney values tabulated here).

    Args:
        catchment_area_m2: Total catchment area draining to the point of
                           interest, in m2.
        surface_type: Surface classification -- must be a key of
                      ``RUNOFF_COEFFICIENTS``.
        aep_percent: Design storm annual exceedance probability in percent
                     (1.0 = 1% AEP / 1-in-100yr; 10.0 = 10% AEP / 1-in-10yr).
        time_of_concentration_min: Time of concentration in minutes (tc).
                                   Typically inlet time (5--10 min for small
                                   roof catchments) plus pipe travel time.

    Returns:
        Dict with keys: ``catchment_area_m2``, ``surface_type``, ``C``,
        ``aep_percent``, ``tc_min``, ``selected_duration_min``,
        ``I_mm_per_hr``, ``Q_ls``, ``method_note``, ``clause_ref``.

    Raises:
        ValueError: For unknown surface type, unsupported AEP, non-positive area,
                    or non-positive tc.
    """
    if catchment_area_m2 <= 0:
        raise ValueError(f"catchment_area_m2 must be positive, got {catchment_area_m2}")
    if time_of_concentration_min <= 0:
        raise ValueError(
            f"time_of_concentration_min must be positive, got {time_of_concentration_min}"
        )
    if surface_type not in RUNOFF_COEFFICIENTS:
        valid = ", ".join(sorted(RUNOFF_COEFFICIENTS))
        raise ValueError(
            f"Unknown surface type '{surface_type}'. Valid types: {valid}"
        )

    C = RUNOFF_COEFFICIENTS[surface_type]
    selected_duration, I = _nearest_duration(aep_percent, time_of_concentration_min)

    Q_ls = C * I * catchment_area_m2 / 360.0

    return {
        "catchment_area_m2": catchment_area_m2,
        "surface_type": surface_type,
        "C": C,
        "aep_percent": aep_percent,
        "tc_min": time_of_concentration_min,
        "selected_duration_min": selected_duration,
        "I_mm_per_hr": I,
        "Q_ls": round(Q_ls, 2),
        "method_note": (
            f"Q = C x I x A / 360 = {C} x {I} x {catchment_area_m2:.0f} / 360 "
            f"= {Q_ls:.2f} L/s. "
            f"Intensity from {aep_percent}% AEP table at {selected_duration} min duration "
            f"(nearest to tc={time_of_concentration_min} min). "
            "NOTE: Tabulated intensities are representative Sydney values. "
            "Obtain site-specific IFD data from BoM for project submissions."
        ),
        "clause_ref": "AS 3500.3 Cl. 3.2, Table 3.1",
    }


def calculate_pipe_capacity(
    diameter_mm: float,
    grade_percent: float,
    material: str = "upvc",
) -> dict:
    """Calculate full-bore pipe flow capacity using Manning's equation.

    Manning's equation::

        Q = (1/n) x A x R^(2/3) x S^(1/2)

    For a circular pipe flowing full:
      A = pi x (D/2)^2        (cross-sectional area, m2)
      R = D/4                  (hydraulic radius for full circular pipe, m)
      S = grade_percent / 100  (hydraulic gradient, m/m)

    Args:
        diameter_mm: Internal pipe diameter in mm.
        grade_percent: Hydraulic gradient as a percentage (e.g., 1.0 = 1%).
        material: Pipe material -- one of ``"upvc"``, ``"concrete"``,
                  ``"cast_iron"``.

    Returns:
        Dict with keys: ``diameter_mm``, ``grade_percent``, ``material``,
        ``manning_n``, ``area_m2``, ``hydraulic_radius_m``, ``velocity_ms``,
        ``capacity_ls``.

    Raises:
        ValueError: For unknown material, non-positive diameter, or
                    non-positive grade.
    """
    if material not in MANNING_N:
        valid = ", ".join(MANNING_N)
        raise ValueError(f"Unknown material '{material}'. Valid: {valid}")
    if diameter_mm <= 0:
        raise ValueError(f"diameter_mm must be positive, got {diameter_mm}")
    if grade_percent <= 0:
        raise ValueError(f"grade_percent must be positive, got {grade_percent}")

    n = MANNING_N[material]
    d_m = diameter_mm / 1000.0
    area_m2 = math.pi * (d_m / 2.0) ** 2
    r_hydraulic = d_m / 4.0
    s_gradient = grade_percent / 100.0

    velocity_ms = (1.0 / n) * (r_hydraulic ** (2.0 / 3.0)) * (s_gradient ** 0.5)
    capacity_m3s = area_m2 * velocity_ms
    capacity_ls = capacity_m3s * 1000.0

    return {
        "diameter_mm": diameter_mm,
        "grade_percent": grade_percent,
        "material": material,
        "manning_n": n,
        "area_m2": round(area_m2, 6),
        "hydraulic_radius_m": round(r_hydraulic, 4),
        "velocity_ms": round(velocity_ms, 3),
        "capacity_ls": round(capacity_ls, 2),
    }


def size_stormwater_pipe(
    design_flow_ls: float,
    grade_percent: float,
    material: str = "upvc",
) -> dict:
    """Select the minimum standard pipe size to carry a design stormwater flow.

    Tests ``STANDARD_SIZES_MM`` from smallest to largest (uPVC default) and
    returns the first size whose full-bore capacity exceeds ``design_flow_ls``.
    If no standard size is adequate, the largest size is returned with
    ``compliant=False``.

    Args:
        design_flow_ls: Design peak flow rate in L/s (output of
                        :func:`calculate_rational_method`).
        grade_percent: Available hydraulic gradient as a percentage.
        material: Pipe material (default ``"upvc"``).

    Returns:
        Dict with keys: ``design_flow_ls``, ``selected_diameter_mm``,
        ``capacity_ls``, ``velocity_ms``, ``grade_percent``, ``material``,
        ``compliant`` (bool), ``clause_ref``.

    Raises:
        ValueError: If design_flow_ls <= 0 or grade_percent <= 0.
    """
    if design_flow_ls <= 0:
        raise ValueError(f"design_flow_ls must be positive, got {design_flow_ls}")
    if grade_percent <= 0:
        raise ValueError(f"grade_percent must be positive, got {grade_percent}")

    last: dict | None = None

    for dn in STANDARD_SIZES_MM:
        cap = calculate_pipe_capacity(dn, grade_percent, material)
        last = cap
        if cap["capacity_ls"] >= design_flow_ls:
            return {
                "design_flow_ls": design_flow_ls,
                "selected_diameter_mm": dn,
                "capacity_ls": cap["capacity_ls"],
                "velocity_ms": cap["velocity_ms"],
                "grade_percent": grade_percent,
                "material": material,
                "compliant": True,
                "clause_ref": "AS 3500.3 Section 4",
            }

    assert last is not None
    return {
        "design_flow_ls": design_flow_ls,
        "selected_diameter_mm": last["diameter_mm"],
        "capacity_ls": last["capacity_ls"],
        "velocity_ms": last["velocity_ms"],
        "grade_percent": grade_percent,
        "material": material,
        "compliant": False,
        "clause_ref": "AS 3500.3 Section 4",
    }


# ── Formatted output ──────────────────────────────────────────────────────────

def format_stormwater_result(result: dict) -> str:
    """Format any stormwater result dict as a professional calculation note.

    Detects result type from keys and delegates to the appropriate formatter.

    Args:
        result: Output of ``calculate_rational_method`` or ``size_stormwater_pipe``.

    Returns:
        Multi-line formatted string.
    """
    if "selected_diameter_mm" in result:
        return _format_pipe_size(result)
    return _format_rational(result)


def _format_rational(r: dict) -> str:
    label = r["surface_type"].replace("_", " ").title()
    lines: list[str] = [
        "## Stormwater Flow -- Rational Method  [AS 3500.3 Cl. 3.2]",
        "",
        "### Inputs",
        f"  Catchment area:          {r['catchment_area_m2']:.0f} m2",
        f"  Surface type:            {label}",
        f"  Runoff coefficient C:    {r['C']}  [AS 3500.3 Table 3.1]",
        f"  Design AEP:              {r['aep_percent']}% AEP",
        f"  Time of concentration:   {r['tc_min']} min",
        f"  Selected duration:       {r['selected_duration_min']} min "
        f"(nearest tabulated to tc)",
        f"  Rainfall intensity I:    {r['I_mm_per_hr']} mm/hr",
        "",
        "### Working  [Q = C x I x A / 360]",
        f"  Q = {r['C']} x {r['I_mm_per_hr']} x {r['catchment_area_m2']:.0f} / 360",
        f"    = **{r['Q_ls']:.2f} L/s**",
        "",
        "### Notes",
        f"  {r['method_note']}",
        "",
        f"  [{r['clause_ref']}]",
    ]
    return "\n".join(lines)


def _format_pipe_size(r: dict) -> str:
    status = "COMPLIANT" if r["compliant"] else (
        "NON-COMPLIANT -- no standard size adequate at this grade. "
        "Increase grade or use custom diameter."
    )
    lines: list[str] = [
        "## Stormwater Pipe Sizing  [AS 3500.3 Section 4]",
        "",
        "### Inputs",
        f"  Design flow:    {r['design_flow_ls']:.2f} L/s",
        f"  Grade:          {r['grade_percent']:.2f}%",
        f"  Material:       {r['material'].upper()} (n = {MANNING_N[r['material']]})",
        "",
        "### Result",
        f"  Selected size:  DN{r['selected_diameter_mm']}",
        f"  Pipe capacity:  {r['capacity_ls']:.2f} L/s (full bore, Manning's equation)",
        f"  Flow velocity:  {r['velocity_ms']:.3f} m/s",
        f"  Utilisation:    {r['design_flow_ls'] / r['capacity_ls'] * 100:.1f}% "
        "of full-bore capacity",
        "",
        f"### Compliance: {status}",
        "",
        f"  [{r['clause_ref']}]",
    ]
    return "\n".join(lines)


# ── Worked example ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print("Meridian -- Stormwater Worked Examples")
    print("AS 3500.3 Rational Method + Pipe Sizing")
    print("=" * 60)

    # Example 1: 500 m2 metal roof, 1% AEP, tc = 5 min
    print("\n--- Example 1: Metal Roof Catchment (1% AEP) ---\n")
    roof = calculate_rational_method(
        catchment_area_m2=500,
        surface_type="roof_metal",
        aep_percent=1.0,
        time_of_concentration_min=5,
    )
    print(format_stormwater_result(roof))

    # Example 2: Size the drain pipe for that flow at 1% grade
    print("\n--- Example 2: Pipe Sizing for Roof Drain (1% grade, uPVC) ---\n")
    pipe = size_stormwater_pipe(
        design_flow_ls=roof["Q_ls"],
        grade_percent=1.0,
        material="upvc",
    )
    print(format_stormwater_result(pipe))

    # Example 3: Mixed catchment -- roof + car park, 10% AEP
    print("\n--- Example 3: Car Park Catchment (10% AEP, tc = 15 min) ---\n")
    carpark = calculate_rational_method(
        catchment_area_m2=2000,
        surface_type="asphalt",
        aep_percent=10.0,
        time_of_concentration_min=15,
    )
    print(format_stormwater_result(carpark))

    # Example 4: Pipe capacity at specific size/grade
    print("\n--- Example 4: Pipe Capacity -- DN150 uPVC at 1.5% grade ---\n")
    cap = calculate_pipe_capacity(diameter_mm=150, grade_percent=1.5, material="upvc")
    print(f"  DN150 uPVC @ 1.5%: capacity = {cap['capacity_ls']:.2f} L/s, "
          f"velocity = {cap['velocity_ms']:.3f} m/s, n = {cap['manning_n']}")
