"""
Meridian -- Hot water storage sizing and TMV requirement calculator.
Standard: AS 3500.4 (current edition), SA HB 39.

Key references:
  - Cl. 4.2:  Storage system sizing -- daily demand x recovery factor
  - Cl. 6.5:  Thermostatic mixing valve (TMV) requirements
  - SA HB 39: Hot water system design guide

Critical constants:
  Minimum storage temp: >=60 deg C  (AS 3500.4 -- legionella control)
  General TMV outlet:   <=50 deg C  (AS 3500.4 Cl. 6.5)
  Healthcare TMV:       <=41 deg C  (AS 3500.4 Cl. 6.5 / SA HB 39)
  Early childhood TMV:  <=43.5 deg C (SA HB 39)
"""

from __future__ import annotations

# ── Table: Daily hot water demand per occupancy type (AS 3500.4) ──────────────
# Format: (litres_per_unit, unit_label)

class _DemandRate:
    __slots__ = ("litres_per_unit", "unit_label", "clause")

    def __init__(self, litres_per_unit: float, unit_label: str, clause: str = "AS 3500.4 Cl. 4.2"):
        self.litres_per_unit = litres_per_unit
        self.unit_label = unit_label
        self.clause = clause


DEMAND_RATES: dict[str, _DemandRate] = {
    "residential_apartment": _DemandRate(50,  "person"),
    "residential_house":     _DemandRate(50,  "person"),
    "office":                _DemandRate(5,   "person"),
    "restaurant_per_meal":   _DemandRate(12,  "meal"),
    "hotel_guestroom":       _DemandRate(100, "room"),
    "hospital_per_bed":      _DemandRate(200, "bed"),
    "school_per_student":    _DemandRate(6,   "student"),
}

# ── TMV outlet temperature limits (AS 3500.4 Cl. 6.5 / SA HB 39) ─────────────
# Format: (max_outlet_temp_c, tmv_required, description, state_note)

class _TMVRule:
    __slots__ = ("max_outlet_temp_c", "tmv_required", "description", "state_note")

    def __init__(
        self,
        max_outlet_temp_c: float,
        tmv_required: bool,
        description: str,
        state_note: str = "",
    ):
        self.max_outlet_temp_c = max_outlet_temp_c
        self.tmv_required = tmv_required
        self.description = description
        self.state_note = state_note


TMV_RULES: dict[str, _TMVRule] = {
    "healthcare_ward": _TMVRule(
        41.0, True,
        "Healthcare/aged care patient bathing outlets",
        "41 deg C limit applies in all states per AS 3500.4 Cl. 6.5 and SA HB 39.",
    ),
    "early_childhood": _TMVRule(
        43.5, True,
        "Early childhood centres (children under school age)",
        "43.5 deg C limit per SA HB 39. Some states require 38 deg C -- confirm with AHJ.",
    ),
    "general_residential": _TMVRule(
        50.0, True,
        "General residential outlets (baths, showers, basins) -- Class 1 and 2 buildings",
        "50 deg C required in most states. Victoria and SA require 45 deg C -- confirm NCC state amendment.",
    ),
    "general_commercial": _TMVRule(
        50.0, True,
        "General commercial/public outlet (shower, basin, bath)",
        "50 deg C required. Confirm state NCC amendment -- some states specify 45 deg C.",
    ),
    "laundry_commercial": _TMVRule(
        60.0, False,
        "Commercial laundry outlet -- high-temp process",
        "No TMV required. Supply at storage temperature is acceptable for laundry process.",
    ),
    "dishwasher_commercial": _TMVRule(
        65.0, False,
        "Commercial dishwasher -- high-temp sanitising cycle",
        "No TMV required. Dishwashers require 60-82 deg C depending on sanitising method.",
    ),
    "kitchen_prep": _TMVRule(
        50.0, False,
        "Kitchen preparation sink (not a hand-washing outlet)",
        "TMV not mandatory but recommended. Confirm with AHJ for building class.",
    ),
    "hand_washing_public": _TMVRule(
        50.0, True,
        "Public hand-washing basin",
        "50 deg C maximum. Consider 45 deg C for public/accessible facilities.",
    ),
}

# ── Constants ─────────────────────────────────────────────────────────────────

MIN_STORAGE_TEMP_C: float = 60.0   # AS 3500.4 -- minimum to control legionella
RECOVERY_FACTOR: float = 0.8       # AS 3500.4 Cl. 4.2 -- storage = daily demand x 0.8


# ── Core calculation functions ─────────────────────────────────────────────────

def calculate_storage_volume(
    occupancy_type: str,
    num_persons: int,
) -> dict:
    """Calculate hot water storage volume per AS 3500.4 Cl. 4.2.

    Storage volume is calculated as::

        daily_demand = demand_rate (L/unit) x num_persons
        storage_volume = daily_demand x recovery_factor (0.8)

    The recovery factor of 0.8 reflects that continuous-draw storage systems
    need not store 100% of daily demand because the heater contributes during
    the draw period.

    Args:
        occupancy_type: Building/space classification. Must be a key of
                        ``DEMAND_RATES``.
        num_persons: Number of persons, rooms, beds, meals, or students
                     (unit depends on occupancy_type -- see ``DEMAND_RATES``).

    Returns:
        Dict with keys: ``occupancy_type``, ``unit_label``, ``num_units``,
        ``demand_rate_l_per_unit``, ``daily_demand_l``, ``recovery_factor``,
        ``storage_volume_l``, ``min_storage_temp_c``, ``clause_ref``.

    Raises:
        ValueError: If ``occupancy_type`` is unknown or ``num_persons`` <= 0.
    """
    if occupancy_type not in DEMAND_RATES:
        valid = ", ".join(sorted(DEMAND_RATES))
        raise ValueError(
            f"Unknown occupancy type '{occupancy_type}'. Valid types: {valid}"
        )
    if num_persons <= 0:
        raise ValueError(f"num_persons must be positive, got {num_persons}")

    rate = DEMAND_RATES[occupancy_type]
    daily_demand_l = rate.litres_per_unit * num_persons
    storage_volume_l = daily_demand_l * RECOVERY_FACTOR

    return {
        "occupancy_type": occupancy_type,
        "unit_label": rate.unit_label,
        "num_units": num_persons,
        "demand_rate_l_per_unit": rate.litres_per_unit,
        "daily_demand_l": round(daily_demand_l, 0),
        "recovery_factor": RECOVERY_FACTOR,
        "storage_volume_l": round(storage_volume_l, 0),
        "min_storage_temp_c": MIN_STORAGE_TEMP_C,
        "clause_ref": rate.clause,
    }


def calculate_tmv_requirement(
    supply_temp_c: float,
    outlet_type: str,
) -> dict:
    """Determine whether a TMV is required and the maximum allowable outlet temperature.

    Compares the system supply temperature against the maximum outlet temperature
    for the given outlet type per AS 3500.4 Cl. 6.5 and SA HB 39.

    A TMV is always required when supply temperature exceeds the allowable outlet
    temperature for the outlet type. When storage is at >=60 deg C (as required for
    legionella control), a TMV is required for all general residential and
    healthcare outlets.

    Args:
        supply_temp_c: Hot water supply (storage) temperature in deg C.
        outlet_type: Outlet classification. Must be a key of ``TMV_RULES``.

    Returns:
        Dict with keys: ``supply_temp_c``, ``outlet_type``, ``tmv_required``,
        ``max_outlet_temp_c``, ``legionella_risk`` (bool -- True if supply
        temp is below 60 deg C), ``state_note``, ``clause_ref``.

    Raises:
        ValueError: If ``outlet_type`` is unknown or ``supply_temp_c`` <= 0.
    """
    if outlet_type not in TMV_RULES:
        valid = ", ".join(sorted(TMV_RULES))
        raise ValueError(
            f"Unknown outlet type '{outlet_type}'. Valid types: {valid}"
        )
    if supply_temp_c <= 0:
        raise ValueError(f"supply_temp_c must be positive, got {supply_temp_c}")

    rule = TMV_RULES[outlet_type]
    legionella_risk = supply_temp_c < MIN_STORAGE_TEMP_C

    # TMV required if supply temp exceeds the allowable outlet temp,
    # OR if the rule mandates a TMV regardless of supply temp.
    tmv_required = rule.tmv_required or (supply_temp_c > rule.max_outlet_temp_c)

    temp_delta_c = supply_temp_c - rule.max_outlet_temp_c

    return {
        "supply_temp_c": supply_temp_c,
        "outlet_type": outlet_type,
        "outlet_description": rule.description,
        "tmv_required": tmv_required,
        "max_outlet_temp_c": rule.max_outlet_temp_c,
        "temp_delta_c": round(temp_delta_c, 1),
        "legionella_risk": legionella_risk,
        "legionella_note": (
            f"Storage at {supply_temp_c} deg C is BELOW the 60 deg C minimum required "
            "to control Legionella [AS 3500.4]. Increase storage temperature."
            if legionella_risk else
            f"Storage at {supply_temp_c} deg C meets >=60 deg C Legionella control "
            "requirement [AS 3500.4]."
        ),
        "state_note": rule.state_note,
        "clause_ref": "AS 3500.4 Cl. 6.5; SA HB 39",
    }


# ── Formatted output ──────────────────────────────────────────────────────────

def format_hot_water_result(result: dict) -> str:
    """Format a hot water calculation result as a professional calculation note.

    Detects result type from keys and delegates to the appropriate formatter.

    Args:
        result: Output of ``calculate_storage_volume`` or
                ``calculate_tmv_requirement``.

    Returns:
        Multi-line formatted string.
    """
    if "storage_volume_l" in result:
        return _format_storage(result)
    if "tmv_required" in result:
        return _format_tmv(result)
    return str(result)


def _format_storage(r: dict) -> str:
    label = r["occupancy_type"].replace("_", " ").title()
    lines: list[str] = [
        "## Hot Water Storage Sizing -- AS 3500.4",
        f"### Occupancy: {label}  [{r['clause_ref']}]",
        "",
        f"  Occupancy type:     {label}",
        f"  Number of {r['unit_label']}s:    {r['num_units']}",
        f"  Demand rate:        {r['demand_rate_l_per_unit']} L/{r['unit_label']}/day",
        "",
        "### Working  [AS 3500.4 Cl. 4.2]",
        f"  Daily demand   = {r['demand_rate_l_per_unit']} L/{r['unit_label']} "
        f"x {r['num_units']} {r['unit_label']}s",
        f"                 = {r['daily_demand_l']:.0f} L/day",
        f"  Recovery factor: {r['recovery_factor']} (AS 3500.4 Cl. 4.2)",
        f"  Storage volume = {r['daily_demand_l']:.0f} x {r['recovery_factor']}",
        f"                 = **{r['storage_volume_l']:.0f} L**",
        "",
        "### Compliance Notes",
        f"  - Storage system must maintain >={r['min_storage_temp_c']:.0f} deg C "
        "to control Legionella risk [AS 3500.4].",
        "  - Cold water entry to storage vessel must prevent thermal stratification "
        "below 60 deg C [AS/NZS 3666.1].",
        "  - This is a preliminary sizing. Verify against peak-hour demand and "
        "available recovery rate before specifying equipment.",
    ]
    return "\n".join(lines)


def _format_tmv(r: dict) -> str:
    tmv_status = "REQUIRED" if r["tmv_required"] else "NOT REQUIRED"
    legionella_flag = " [LEGIONELLA RISK]" if r["legionella_risk"] else ""

    lines: list[str] = [
        "## TMV Requirement Check -- AS 3500.4 Cl. 6.5",
        f"### Outlet: {r['outlet_type'].replace('_', ' ').title()}",
        "",
        f"  Supply temperature:  {r['supply_temp_c']} deg C{legionella_flag}",
        f"  Outlet description:  {r['outlet_description']}",
        f"  Max outlet temp:     {r['max_outlet_temp_c']} deg C",
        f"  Temperature delta:   {r['temp_delta_c']:+.1f} deg C "
        f"(supply vs max outlet)",
        "",
        f"### Result: TMV {tmv_status}  [{r['clause_ref']}]",
        "",
        f"  {r['legionella_note']}",
        "",
    ]

    if r["state_note"]:
        lines += [f"  State note: {r['state_note']}", ""]

    if r["tmv_required"]:
        lines += [
            "### TMV Specification Notes",
            f"  - Install AS 4032.1 / AS 4032.2 compliant TMV set to "
            f"{r['max_outlet_temp_c']:.1f} deg C maximum.",
            "  - TMV must be accessible for periodic testing and maintenance.",
            "  - Test and commission per AS 4032.3 after installation.",
            "  - Include in essential services maintenance schedule.",
        ]
    return "\n".join(lines)


# ── Worked example ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print("Meridian -- Hot Water Worked Examples")
    print("AS 3500.4 Storage Sizing and TMV Requirements")
    print("=" * 60)

    # Example 1: 10-unit apartment block, 3 persons per unit
    print("\n--- Example 1: Residential Apartment Block ---\n")
    storage = calculate_storage_volume("residential_apartment", num_persons=30)
    print(format_hot_water_result(storage))

    # Example 2: 50-bed hospital ward
    print("\n--- Example 2: Hospital Ward ---\n")
    hospital = calculate_storage_volume("hospital_per_bed", num_persons=50)
    print(format_hot_water_result(hospital))

    # Example 3: TMV check -- general residential shower, storage at 65 deg C
    print("\n--- Example 3: TMV Requirement -- General Residential ---\n")
    tmv_res = calculate_tmv_requirement(supply_temp_c=65.0, outlet_type="general_residential")
    print(format_hot_water_result(tmv_res))

    # Example 4: TMV check -- healthcare ward outlet
    print("\n--- Example 4: TMV Requirement -- Healthcare Ward ---\n")
    tmv_hc = calculate_tmv_requirement(supply_temp_c=65.0, outlet_type="healthcare_ward")
    print(format_hot_water_result(tmv_hc))

    # Example 5: Legionella risk -- storage below 60 deg C
    print("\n--- Example 5: Legionella Risk -- Storage Below 60 deg C ---\n")
    tmv_risk = calculate_tmv_requirement(supply_temp_c=55.0, outlet_type="general_residential")
    print(format_hot_water_result(tmv_risk))
