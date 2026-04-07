"""
Meridian -- Mechanical ventilation outdoor air calculator.
Standard: AS 1668.2 (current edition).

Key references:
  - Table 2:  Outdoor air supply rates by space type (L/s/person and L/s/m2)
  - Cl. 4.3:  Outdoor air quantity -- design OA = max(person-based, area-based)
  - Section 6: Carpark ventilation -- 6 ACH minimum or CO-controlled to <30 ppm
  - Cl. 6.3:  Carpark CO control setpoint

Critical constants:
  Office OA rate:  10 L/s/person + 0.5 L/s/m2  (AS 1668.2 Table 2)
  Carpark minimum: 6 ACH                          (AS 1668.2 Cl. 6.3)
  Carpark CO limit: 30 ppm time-weighted average  (AS 1668.2 Cl. 6.3)
"""

from __future__ import annotations

import math
from typing import NamedTuple

# ── Table 2 -- Occupancy density (persons/m2) ─────────────────────────────────
# Used when occupant_count is not supplied by the caller.
# Carpark and corridor carry no person-density (ventilation via other methods).

OCCUPANCY_RATES: dict[str, float] = {
    "office_open_plan":   1 / 10,
    "office_enclosed":    1 / 10,
    "meeting_room":       1 / 3,
    "reception":          1 / 10,
    "retail_general":     1 / 4,
    "retail_supermarket": 1 / 5,
    "restaurant_dining":  1 / 2,
    "kitchen_commercial": 1 / 10,
    "gym":                1 / 5,
    "cinema":             1 / 1.5,
    "classroom":          1 / 2,
    "library":            1 / 5,
    "hospital_ward":      1 / 10,
    "hospital_waiting":   1 / 3,
    "carpark":            0.0,
    "lobby_hotel":        1 / 10,
    "guestroom":          1 / 25,
    "corridor":           0.0,
}

# ── Table 2 -- Outdoor air rates (L/s/person, L/s/m2) ────────────────────────
# "special" space types (carpark, commercial kitchen) use dedicated functions.

class _VentRate(NamedTuple):
    per_person_ls: float   # L/s per person
    per_m2_ls: float       # L/s per m2 of floor area
    special: bool = False  # True => use dedicated calculation function


VENTILATION_RATES: dict[str, _VentRate] = {
    "office_open_plan":   _VentRate(10.0, 0.5),
    "office_enclosed":    _VentRate(10.0, 0.5),
    "meeting_room":       _VentRate(10.0, 0.5),
    "reception":          _VentRate(10.0, 0.5),
    "retail_general":     _VentRate(8.0,  0.5),
    "retail_supermarket": _VentRate(8.0,  0.5),
    "restaurant_dining":  _VentRate(12.5, 0.5),
    "kitchen_commercial": _VentRate(0.0,  0.0, special=True),
    "gym":                _VentRate(10.0, 1.0),
    "cinema":             _VentRate(8.0,  0.5),
    "classroom":          _VentRate(8.0,  0.5),
    "library":            _VentRate(8.0,  0.5),
    "hospital_ward":      _VentRate(8.0,  0.5),
    "hospital_waiting":   _VentRate(10.0, 0.5),
    "carpark":            _VentRate(0.0,  0.0, special=True),
    "lobby_hotel":        _VentRate(10.0, 0.5),
    "guestroom":          _VentRate(10.0, 0.5),
    "corridor":           _VentRate(0.0,  0.5),
}

# ── Carpark constants ─────────────────────────────────────────────────────────

CARPARK_MIN_ACH: float = 6.0            # AS 1668.2 Cl. 6.3 -- minimum 6 ACH
CARPARK_CO_LIMIT_PPM: float = 30.0      # AS 1668.2 Cl. 6.3 -- CO < 30 ppm TWA
CARPARK_ASSUMED_HEIGHT_M: float = 2.7   # Typical slab-to-slab for ACH if no height given

# ── Validation helpers ────────────────────────────────────────────────────────

def _valid_space_type(space_type: str) -> None:
    if space_type not in VENTILATION_RATES:
        valid = ", ".join(sorted(VENTILATION_RATES))
        raise ValueError(
            f"Unknown space type '{space_type}'. Valid types: {valid}"
        )


# ── Core calculation functions ─────────────────────────────────────────────────

def calculate_outdoor_air(
    space_type: str,
    floor_area_m2: float,
    occupant_count: int | None = None,
) -> dict:
    """Calculate minimum outdoor air supply rate per AS 1668.2 Cl. 4.3.

    The design outdoor air quantity is the greater of:
      (a) occupant-based rate  = L/s/person x occupant_count
      (b) area-based rate      = L/s/m2    x floor_area_m2

    If ``occupant_count`` is not provided it is estimated from ``OCCUPANCY_RATES``
    using the default density for the space type.

    Special space types (``"carpark"``, ``"kitchen_commercial"``) are not
    supported here -- use :func:`calculate_carpark_ventilation` for carparkss.
    Commercial kitchens require an exhaust-first design approach per AS 1668.2
    Section 5; a ``ValueError`` is raised to direct the caller accordingly.

    Args:
        space_type: AS 1668.2 space classification -- must be a key of
                    ``VENTILATION_RATES``.
        floor_area_m2: Net floor area of the space in m2.
        occupant_count: Number of occupants. If ``None``, calculated from the
                        default occupancy density for the space type.

    Returns:
        Dict with keys:
          ``space_type``, ``floor_area_m2``, ``occupants``,
          ``rate_per_person_ls``, ``rate_per_m2_ls``,
          ``occupant_oa_ls``, ``area_oa_ls``, ``design_oa_ls``,
          ``governing_criterion``, ``method_note``, ``clause_ref``.

    Raises:
        ValueError: For unknown space types, special-case types, negative areas,
                    or negative occupant counts.
    """
    _valid_space_type(space_type)

    rate = VENTILATION_RATES[space_type]
    if rate.special:
        if space_type == "carpark":
            raise ValueError(
                "Use calculate_carpark_ventilation() for carpark spaces."
            )
        if space_type == "kitchen_commercial":
            raise ValueError(
                "Commercial kitchens require an exhaust-first design per "
                "AS 1668.2 Section 5. Size exhaust based on cooking appliance "
                "loads, then supply air to maintain negative pressure relative "
                "to adjacent spaces. This function does not cover that method."
            )

    if floor_area_m2 <= 0:
        raise ValueError(f"floor_area_m2 must be positive, got {floor_area_m2}")

    # Determine occupant count
    if occupant_count is None:
        density = OCCUPANCY_RATES[space_type]
        occupants = math.ceil(density * floor_area_m2)
        occupant_source = f"estimated from AS 1668.2 Table 2 density ({density:.3f} p/m2)"
    else:
        if occupant_count < 0:
            raise ValueError(f"occupant_count must be non-negative, got {occupant_count}")
        occupants = occupant_count
        occupant_source = "provided by designer"

    # Flag high-density spaces (>50% above Table 2 default)
    high_density_warning: str | None = None
    default_density = OCCUPANCY_RATES[space_type]
    if default_density > 0 and floor_area_m2 > 0:
        actual_density = occupants / floor_area_m2
        if actual_density > default_density * 1.5:
            high_density_warning = (
                f"WARNING: Actual density {actual_density:.3f} p/m2 exceeds "
                f"AS 1668.2 Table 2 default ({default_density:.3f} p/m2) by more than 50%. "
                "Verify with AHJ whether a higher design OA is required."
            )

    # AS 1668.2 Cl. 4.3 calculation
    occupant_oa_ls = rate.per_person_ls * occupants
    area_oa_ls = rate.per_m2_ls * floor_area_m2
    design_oa_ls = max(occupant_oa_ls, area_oa_ls)

    if occupant_oa_ls >= area_oa_ls:
        governing = "occupant-based"
    else:
        governing = "area-based"

    result = {
        "space_type": space_type,
        "floor_area_m2": floor_area_m2,
        "occupants": occupants,
        "occupant_source": occupant_source,
        "rate_per_person_ls": rate.per_person_ls,
        "rate_per_m2_ls": rate.per_m2_ls,
        "occupant_oa_ls": round(occupant_oa_ls, 2),
        "area_oa_ls": round(area_oa_ls, 2),
        "design_oa_ls": round(design_oa_ls, 2),
        "governing_criterion": governing,
        "high_density_warning": high_density_warning,
        "method_note": (
            f"Design OA = max({rate.per_person_ls} L/s/person x {occupants} persons, "
            f"{rate.per_m2_ls} L/s/m2 x {floor_area_m2} m2) = {design_oa_ls:.1f} L/s "
            f"[{governing} criterion governs]."
        ),
        "clause_ref": "AS 1668.2 Table 2, Cl. 4.3",
    }

    if high_density_warning:
        result["high_density_warning"] = high_density_warning

    return result


def calculate_carpark_ventilation(
    floor_area_m2: float,
    num_spaces: int,
    ceiling_height_m: float = CARPARK_ASSUMED_HEIGHT_M,
    use_co_control: bool = False,
) -> dict:
    """Calculate minimum mechanical ventilation for a carpark per AS 1668.2 Section 6.

    Two compliant methods are available:

    **ACH method (default):**
      Q = Volume x 6 ACH / 3600 seconds
      Volume = floor_area_m2 x ceiling_height_m

    **CO-controlled method:**
      The system must maintain CO below 30 ppm time-weighted average per
      AS 1668.2 Cl. 6.3. Minimum airflow is still governed by the 6 ACH floor
      when CO sensors are not registering elevated levels. The return value
      notes the sensor setpoints that must be included in the BMS.

    Args:
        floor_area_m2: Gross floor area of the carpark level in m2.
        num_spaces: Number of car spaces on the level.
        ceiling_height_m: Clear height from floor to soffit (m). Defaults to
                          2.7 m if not measured.
        use_co_control: If ``True``, the result notes CO-controlled requirements
                        in addition to the minimum ACH floor.

    Returns:
        Dict with keys:
          ``method``, ``floor_area_m2``, ``volume_m3``, ``num_spaces``,
          ``min_ach``, ``min_oa_ls``, ``ach_equivalent``, ``note``, ``clause_ref``.

    Raises:
        ValueError: If floor_area_m2 or ceiling_height_m are non-positive.
    """
    if floor_area_m2 <= 0:
        raise ValueError(f"floor_area_m2 must be positive, got {floor_area_m2}")
    if ceiling_height_m <= 0:
        raise ValueError(f"ceiling_height_m must be positive, got {ceiling_height_m}")
    if num_spaces < 0:
        raise ValueError(f"num_spaces must be non-negative, got {num_spaces}")

    volume_m3 = floor_area_m2 * ceiling_height_m
    # Q (L/s) = Volume (m3) x ACH / 3600 s/hr x 1000 L/m3
    min_oa_ls = (volume_m3 * CARPARK_MIN_ACH / 3600.0) * 1000.0
    ach_equivalent = CARPARK_MIN_ACH

    if use_co_control:
        method = "CO-controlled (with minimum ACH floor)"
        note = (
            f"Minimum supply: {min_oa_ls:.0f} L/s ({CARPARK_MIN_ACH:.0f} ACH) at all times. "
            f"CO sensors must be installed to maintain CO < {CARPARK_CO_LIMIT_PPM:.0f} ppm "
            f"time-weighted average [AS 1668.2 Cl. 6.3]. "
            "BMS to modulate fans based on CO reading; minimum speed must achieve 6 ACH. "
            "Sensor quantity and placement per AS 1668.2 Appendix guidance."
        )
    else:
        method = "Minimum ACH (constant volume)"
        note = (
            f"Continuous supply of {min_oa_ls:.0f} L/s required to achieve "
            f"{CARPARK_MIN_ACH:.0f} ACH minimum [AS 1668.2 Cl. 6.3]. "
            "CO control is an alternative compliant method that may allow reduced "
            "operating hours outside peak use periods."
        )

    return {
        "method": method,
        "floor_area_m2": floor_area_m2,
        "volume_m3": round(volume_m3, 1),
        "ceiling_height_m": ceiling_height_m,
        "num_spaces": num_spaces,
        "min_ach": CARPARK_MIN_ACH,
        "min_oa_ls": round(min_oa_ls, 0),
        "ach_equivalent": ach_equivalent,
        "note": note,
        "clause_ref": "AS 1668.2 Section 6, Cl. 6.3",
    }


def calculate_multi_zone(zones: list[dict]) -> dict:
    """Calculate outdoor air for a multi-zone ventilation system.

    Each zone dict must contain:
      - ``name`` (str): Zone label for reporting
      - ``space_type`` (str): AS 1668.2 space classification
      - ``floor_area_m2`` (float): Net floor area
      - ``occupants`` (int, optional): If omitted, estimated from Table 2

    Calls :func:`calculate_outdoor_air` for each zone. Zones that use special
    methods (carpark, commercial kitchen) must be handled separately and are
    skipped with a warning in the results.

    Args:
        zones: List of zone specification dicts.

    Returns:
        Dict with keys:
          ``zone_results`` (list of per-zone dicts),
          ``total_oa_ls`` (float),
          ``total_floor_area_m2`` (float),
          ``weighted_oa_per_m2`` (float),
          ``zone_count`` (int),
          ``skipped_zones`` (list of zone names skipped due to special types),
          ``clause_ref`` (str).

    Raises:
        ValueError: If ``zones`` is empty.
    """
    if not zones:
        raise ValueError("zones list must not be empty")

    zone_results: list[dict] = []
    skipped_zones: list[str] = []
    total_oa_ls = 0.0
    total_floor_area_m2 = 0.0

    for zone in zones:
        name = zone.get("name", "Unnamed zone")
        space_type = zone["space_type"]
        floor_area_m2 = float(zone["floor_area_m2"])
        occupants = zone.get("occupants", None)

        # Skip special-method zones gracefully
        rate_info = VENTILATION_RATES.get(space_type)
        if rate_info and rate_info.special:
            skipped_zones.append(
                f"{name} ({space_type}) -- requires dedicated calculation method"
            )
            continue

        try:
            result = calculate_outdoor_air(space_type, floor_area_m2, occupants)
        except ValueError as exc:
            skipped_zones.append(f"{name} -- {exc}")
            continue

        result["zone_name"] = name
        zone_results.append(result)

        total_oa_ls += result["design_oa_ls"]
        total_floor_area_m2 += floor_area_m2

    weighted_oa_per_m2 = (
        total_oa_ls / total_floor_area_m2 if total_floor_area_m2 > 0 else 0.0
    )

    return {
        "zone_results": zone_results,
        "total_oa_ls": round(total_oa_ls, 1),
        "total_floor_area_m2": round(total_floor_area_m2, 1),
        "weighted_oa_per_m2": round(weighted_oa_per_m2, 3),
        "zone_count": len(zone_results),
        "skipped_zones": skipped_zones,
        "clause_ref": "AS 1668.2 Table 2, Cl. 4.3",
    }


def supply_air_quantity(
    outdoor_air_ls: float,
    recirculation_fraction: float = 0.0,
) -> dict:
    """Calculate total supply air given outdoor air and recirculation fraction.

    Supply air = OA / (1 - recirculation_fraction)

    A recirculation fraction of 0.0 means 100% OA (no recirculation).
    A fraction of 0.5 means 50% of supply air is recirculated return air.
    Maximum allowed recirculation is 0.9 (90%) per good engineering practice;
    values >= 1.0 are physically impossible.

    Note: Recirculation is not permitted in spaces with high contaminant loads
    (commercial kitchens, laboratories, hospital isolation rooms) per AS 1668.2.

    Args:
        outdoor_air_ls: Required outdoor air flow rate in L/s.
        recirculation_fraction: Fraction of supply air that is recirculated
                                (0.0 = 100% OA; must be in range [0.0, 0.9]).

    Returns:
        Dict with keys: ``oa_ls``, ``recirculation_fraction``,
        ``supply_air_ls``, ``recirculated_ls``, ``note``.

    Raises:
        ValueError: If outdoor_air_ls <= 0 or recirculation_fraction is
                    outside [0.0, 0.9].
    """
    if outdoor_air_ls <= 0:
        raise ValueError(f"outdoor_air_ls must be positive, got {outdoor_air_ls}")
    if not (0.0 <= recirculation_fraction <= 0.9):
        raise ValueError(
            f"recirculation_fraction must be in range [0.0, 0.9], "
            f"got {recirculation_fraction}"
        )

    supply_air_ls = outdoor_air_ls / (1.0 - recirculation_fraction)
    recirculated_ls = supply_air_ls - outdoor_air_ls
    oa_pct = (1.0 - recirculation_fraction) * 100.0

    note = (
        f"Supply air = {supply_air_ls:.1f} L/s "
        f"({oa_pct:.0f}% OA = {outdoor_air_ls:.1f} L/s, "
        f"{recirculation_fraction * 100:.0f}% recirculated = {recirculated_ls:.1f} L/s). "
        "Recirculation is not permitted in kitchens, labs, or isolation rooms."
    )

    return {
        "oa_ls": round(outdoor_air_ls, 1),
        "recirculation_fraction": recirculation_fraction,
        "supply_air_ls": round(supply_air_ls, 1),
        "recirculated_ls": round(recirculated_ls, 1),
        "oa_percentage": round(oa_pct, 1),
        "note": note,
    }


# ── Formatted output ──────────────────────────────────────────────────────────

def format_ventilation_result(result: dict) -> str:
    """Format any ventilation result dict as a professional calculation note.

    Detects result type from its keys and delegates to the appropriate
    sub-formatter. Supported result types: single-zone OA, carpark, multi-zone.

    Args:
        result: Output of ``calculate_outdoor_air``, ``calculate_carpark_ventilation``,
                or ``calculate_multi_zone``.

    Returns:
        A multi-line string structured as a professional calculation note.
    """
    if "zone_results" in result:
        return _format_multi_zone(result)
    if "min_oa_ls" in result:
        return _format_carpark(result)
    return _format_single_zone(result)


def _format_single_zone(r: dict) -> str:
    label = r["space_type"].replace("_", " ").title()
    lines: list[str] = [
        "## Mechanical Ventilation -- Outdoor Air Calculation",
        f"### Space: {label}  [{r['clause_ref']}]",
        "",
        f"  Floor area:          {r['floor_area_m2']:.0f} m2",
        f"  Occupants:           {r['occupants']} persons  ({r['occupant_source']})",
        f"  Rate (person-based): {r['rate_per_person_ls']} L/s/person",
        f"  Rate (area-based):   {r['rate_per_m2_ls']} L/s/m2",
        "",
        "### Working  [AS 1668.2 Cl. 4.3]",
        f"  Occupant-based OA = {r['rate_per_person_ls']} x {r['occupants']} "
        f"= {r['occupant_oa_ls']:.1f} L/s",
        f"  Area-based OA     = {r['rate_per_m2_ls']} x {r['floor_area_m2']:.0f} "
        f"= {r['area_oa_ls']:.1f} L/s",
        f"  Design OA         = max({r['occupant_oa_ls']:.1f}, {r['area_oa_ls']:.1f}) "
        f"= **{r['design_oa_ls']:.1f} L/s**  ({r['governing_criterion']} governs)",
        "",
    ]

    if r.get("high_density_warning"):
        lines += [f"  {r['high_density_warning']}", ""]

    lines += [
        "### Compliance Statement",
        f"  Design OA of {r['design_oa_ls']:.1f} L/s satisfies AS 1668.2 Table 2 "
        f"minimum requirements for {label} [Cl. 4.3].",
    ]
    return "\n".join(lines)


def _format_carpark(r: dict) -> str:
    lines: list[str] = [
        "## Mechanical Ventilation -- Carpark",
        f"### Method: {r['method']}  [{r['clause_ref']}]",
        "",
        f"  Floor area:      {r['floor_area_m2']:.0f} m2",
        f"  Ceiling height:  {r['ceiling_height_m']:.1f} m",
        f"  Volume:          {r['volume_m3']:.0f} m3",
        f"  Car spaces:      {r['num_spaces']}",
        "",
        "### Working  [AS 1668.2 Cl. 6.3]",
        f"  Min ACH          = {r['min_ach']:.0f} ACH",
        f"  Volume           = {r['volume_m3']:.0f} m3",
        f"  Min flow         = {r['volume_m3']:.0f} x {r['min_ach']:.0f} / 3600 x 1000",
        f"                   = **{r['min_oa_ls']:.0f} L/s**",
        "",
        f"  {r['note']}",
        "",
        "### Compliance Statement",
        f"  Supply/exhaust of {r['min_oa_ls']:.0f} L/s required. "
        f"System must achieve {r['min_ach']:.0f} ACH minimum [AS 1668.2 Cl. 6.3].",
    ]
    return "\n".join(lines)


def _format_multi_zone(r: dict) -> str:
    lines: list[str] = [
        "## Mechanical Ventilation -- Multi-Zone Outdoor Air Schedule",
        f"### AS 1668.2 Table 2 / Cl. 4.3 | {r['zone_count']} zones",
        "",
        f"{'Zone':<28} {'Type':<22} {'Area m2':>8}  {'Persons':>8}  {'OA L/s':>8}  {'Criterion':<16}",
        "-" * 96,
    ]

    for z in r["zone_results"]:
        label = z["space_type"].replace("_", " ").title()
        lines.append(
            f"{z.get('zone_name', ''):<28} {label:<22} "
            f"{z['floor_area_m2']:>8.0f}  {z['occupants']:>8}  "
            f"{z['design_oa_ls']:>8.1f}  {z['governing_criterion']:<16}"
        )

    lines += [
        "-" * 96,
        f"{'TOTAL':<28} {'':<22} "
        f"{r['total_floor_area_m2']:>8.0f}  {'':>8}  {r['total_oa_ls']:>8.1f}",
        "",
        f"  Weighted average OA intensity: {r['weighted_oa_per_m2']:.3f} L/s/m2",
        "",
    ]

    if r["skipped_zones"]:
        lines.append("  Zones excluded from totals (require separate calculation):")
        for skip in r["skipped_zones"]:
            lines.append(f"    - {skip}")
        lines.append("")

    lines += [
        "### Compliance Statement",
        f"  Total design outdoor air = {r['total_oa_ls']:.1f} L/s across "
        f"{r['zone_count']} zones. Each zone satisfies AS 1668.2 Table 2 "
        "minimum rates [Cl. 4.3].",
    ]
    return "\n".join(lines)


# ── Worked example ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print("Meridian -- Mechanical Ventilation Worked Example")
    print("AS 1668.2 Outdoor Air Calculation")
    print("=" * 60)

    zones = [
        {"name": "Open Plan Office",  "space_type": "office_open_plan", "floor_area_m2": 800},
        {"name": "Meeting Room",      "space_type": "meeting_room",      "floor_area_m2":  60},
        {"name": "Reception",         "space_type": "reception",         "floor_area_m2":  40},
    ]

    print("\n--- Multi-Zone OA Schedule ---\n")
    multi = calculate_multi_zone(zones)
    print(format_ventilation_result(multi))

    print("\n--- Individual Zone Detail ---")
    for z in multi["zone_results"]:
        print()
        print(format_ventilation_result(z))

    print("\n--- Supply Air with 30% Recirculation ---\n")
    supply = supply_air_quantity(multi["total_oa_ls"], recirculation_fraction=0.3)
    print(f"  OA required:     {supply['oa_ls']:.1f} L/s")
    print(f"  Supply air:      {supply['supply_air_ls']:.1f} L/s")
    print(f"  Recirculated:    {supply['recirculated_ls']:.1f} L/s")
    print(f"  Note: {supply['note']}")

    print("\n--- Carpark (1000 m2, 2.7m ceiling, CO-controlled) ---\n")
    cp = calculate_carpark_ventilation(
        floor_area_m2=1000, num_spaces=40, ceiling_height_m=2.7, use_co_control=True
    )
    print(format_ventilation_result(cp))
