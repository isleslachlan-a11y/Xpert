"""
Meridian -- Calculator tools for the ReActAgent.

Each public calculator function is wrapped in a thin adapter that:
  1. Calls the calculator with validated arguments.
  2. Passes the result dict through the matching formatter.
  3. Returns a human-readable string directly to the agent.
  4. Catches exceptions and returns a structured error string so the agent
     can report the problem without crashing.

Tool description quality is critical -- the ReActAgent reads each description
to decide whether to invoke the tool. Descriptions answer three questions:
  - When should I use this tool? (trigger conditions)
  - What inputs does it need? (parameter contract)
  - What standard does it reference? (compliance context)

ALL_CALC_TOOLS is imported by agent/orchestrator.py and passed to ReActAgent.
"""

from __future__ import annotations

from llama_index.core.tools import FunctionTool

from calculators.hot_water import (
    calculate_storage_volume,
    calculate_tmv_requirement,
    format_hot_water_result,
)
from calculators.pipe_sizing import (
    format_pipe_sizing_result,
    size_pipe_from_fixtures,
)
from calculators.stormwater import (
    calculate_rational_method,
    format_stormwater_result,
    size_stormwater_pipe,
)
from calculators.ventilation_mechanical import (
    calculate_carpark_ventilation,
    calculate_multi_zone,
    format_ventilation_result,
)


# ── Tool adapter functions ────────────────────────────────────────────────────
# Each adapter wraps one calculator function, formats the result, and returns
# a string. Adapters are defined here (not imported from calculators/) so that
# the docstrings seen by FunctionTool describe parameters in agent-friendly
# terms, not engineering-library terms.


def _tool_error(tool_name: str, exc: Exception) -> str:
    """Return a structured error string the agent can relay to the user."""
    return (
        f"[{tool_name}] Calculation failed: {exc}\n"
        "Please check your inputs and try again. "
        "If the problem persists, check that fixture types, material names, "
        "space types, and surface types are spelled correctly."
    )


# ── AS 3500.1 -- Pipe sizing ──────────────────────────────────────────────────

def as3500_pipe_sizing(
    fixtures: dict,
    material: str,
    pipe_length_m: float,
    static_pressure_kpa: float = 300.0,
) -> str:
    """Size a cold water pipe using the AS 3500.1--2018 fixture unit method.

    Use this tool when the user asks to size a cold water supply pipe, find the
    recommended pipe diameter for a given fixture schedule, or check whether a
    proposed pipe size complies with AS 3500.1 velocity and pressure limits.

    ``fixtures`` must be a dict mapping fixture type strings to integer counts,
    e.g. ``{"wc_private": 4, "basin_private": 4, "shower": 2}``. Valid fixture
    types include: wc_private, wc_public, basin_private, basin_public, bath,
    shower, sink_domestic, sink_commercial, dishwasher_domestic,
    washing_machine, urinal_flush, hose_tap, drinking_fountain, cleaners_sink.

    ``material`` must be one of: copper, cpvc, pex, stainless.

    ``pipe_length_m`` is the equivalent pipe length in metres (include a
    fitting allowance -- typically add 15--20% to measured length for elbows
    and tees).

    Returns the recommended pipe DN, velocity, pressure drop (Pa/m), residual
    pressure, and a compliance statement referencing AS 3500.1 Cl. 3.4.3
    (velocity) and Cl. 7.4.1 (minimum residual pressure 100 kPa).
    """
    try:
        result = size_pipe_from_fixtures(
            fixtures=fixtures,
            material=material,
            pipe_length_m=pipe_length_m,
            static_pressure_kpa=static_pressure_kpa,
        )
        return format_pipe_sizing_result(result)
    except Exception as exc:
        return _tool_error("as3500_pipe_sizing", exc)


# ── AS 1668.2 -- Multi-zone outdoor air ───────────────────────────────────────

def as1668_multi_zone_ventilation(zones: list) -> str:
    """Calculate outdoor air requirements for multiple occupied zones per AS 1668.2.

    Use this tool when the user asks to calculate outdoor air supply rates,
    check ventilation compliance for a floor plate with multiple space types,
    or determine total OA for an air handling unit serving several zones.

    ``zones`` must be a list of dicts. Each dict requires:
      - ``name`` (str): Zone label (e.g. "Open Plan Office")
      - ``space_type`` (str): AS 1668.2 space classification
      - ``floor_area_m2`` (float): Net floor area in m2
      - ``occupants`` (int, optional): If omitted, estimated from Table 2 density

    Valid space types include: office_open_plan, office_enclosed, meeting_room,
    reception, retail_general, restaurant_dining, gym, classroom, library,
    hospital_ward, guestroom, corridor, lobby_hotel.

    Returns a zone-by-zone outdoor air schedule with totals, governing criterion
    per zone (occupant-based vs area-based), and a compliance statement
    referencing AS 1668.2 Table 2 and Cl. 4.3.
    """
    try:
        result = calculate_multi_zone(zones=zones)
        return format_ventilation_result(result)
    except Exception as exc:
        return _tool_error("as1668_multi_zone_ventilation", exc)


# ── AS 1668.2 -- Carpark ventilation ─────────────────────────────────────────

def as1668_carpark_ventilation(
    floor_area_m2: float,
    num_spaces: int,
    ceiling_height_m: float = 2.7,
    use_co_control: bool = False,
) -> str:
    """Calculate minimum mechanical ventilation for a carpark per AS 1668.2 Section 6.

    Use this tool when the user asks about carpark ventilation rates, whether
    a carpark needs CO sensors, how much supply/exhaust air is required for a
    basement carpark, or what the minimum air changes per hour are for a
    parking structure.

    ``floor_area_m2`` is the gross floor area of the carpark level.
    ``num_spaces`` is the number of car parking spaces on the level.
    ``ceiling_height_m`` is the clear floor-to-soffit height in metres
    (defaults to 2.7 m if not measured).
    ``use_co_control`` set to True when a CO sensor-controlled system is
    being designed; the result will include BMS setpoint requirements.

    Returns minimum flow in L/s, equivalent ACH, and compliance notes
    referencing AS 1668.2 Cl. 6.3 (6 ACH minimum, CO < 30 ppm).
    """
    try:
        result = calculate_carpark_ventilation(
            floor_area_m2=floor_area_m2,
            num_spaces=num_spaces,
            ceiling_height_m=ceiling_height_m,
            use_co_control=use_co_control,
        )
        return format_ventilation_result(result)
    except Exception as exc:
        return _tool_error("as1668_carpark_ventilation", exc)


# ── AS 3500.4 -- Hot water storage ───────────────────────────────────────────

def as3500_hot_water_storage(
    occupancy_type: str,
    num_persons: int,
) -> str:
    """Size a hot water storage system per AS 3500.4 Cl. 4.2.

    Use this tool when the user asks to determine the required hot water
    storage volume, size a storage heater, or calculate daily hot water demand
    for a building.

    ``occupancy_type`` must be one of: residential_apartment, residential_house,
    office, restaurant_per_meal, hotel_guestroom, hospital_per_bed,
    school_per_student.

    ``num_persons`` is the count appropriate to the occupancy type: persons for
    residential/office, meals for restaurant, rooms for hotel, beds for
    hospital, students for school.

    Returns daily demand (L/day), recommended storage volume (L), the 0.8
    recovery factor per Cl. 4.2, and a note on minimum storage temperature
    (>=60 deg C) for Legionella control.
    """
    try:
        result = calculate_storage_volume(
            occupancy_type=occupancy_type,
            num_persons=num_persons,
        )
        return format_hot_water_result(result)
    except Exception as exc:
        return _tool_error("as3500_hot_water_storage", exc)


# ── AS 3500.4 -- TMV requirement ─────────────────────────────────────────────

def as3500_tmv_requirement(
    supply_temp_c: float,
    outlet_type: str,
) -> str:
    """Check whether a thermostatic mixing valve (TMV) is required per AS 3500.4 Cl. 6.5.

    Use this tool when the user asks whether a TMV is needed for a specific
    outlet, what maximum outlet temperature is permitted for a bathroom or
    healthcare facility, whether storage temperature complies with Legionella
    control requirements, or which AS 4032 TMV standard applies.

    ``supply_temp_c`` is the hot water storage or supply temperature in deg C.
    ``outlet_type`` must be one of: general_residential, general_commercial,
    healthcare_ward, early_childhood, laundry_commercial,
    dishwasher_commercial, kitchen_prep, hand_washing_public.

    Returns whether a TMV is required, the maximum permitted outlet temperature,
    Legionella risk flag if storage is below 60 deg C, and relevant state
    variation notes, referencing AS 3500.4 Cl. 6.5 and SA HB 39.
    """
    try:
        result = calculate_tmv_requirement(
            supply_temp_c=supply_temp_c,
            outlet_type=outlet_type,
        )
        return format_hot_water_result(result)
    except Exception as exc:
        return _tool_error("as3500_tmv_requirement", exc)


# ── AS 3500.3 -- Stormwater flow ─────────────────────────────────────────────

def as3500_stormwater_flow(
    catchment_area_m2: float,
    surface_type: str,
    aep_percent: float,
    time_of_concentration_min: float,
) -> str:
    """Calculate peak stormwater flow using the Rational Method per AS 3500.3.

    Use this tool when the user asks to calculate design stormwater flows,
    determine the peak runoff from a roof or paved area, or establish the
    design flow for sizing a stormwater drain or downpipe.

    ``catchment_area_m2`` is the total area draining to the point of interest.
    ``surface_type`` must be one of: roof_metal, roof_tile, concrete_paving,
    asphalt, gravel, lawn_flat, lawn_steep, garden_bed, bushland.
    ``aep_percent`` is 1.0 (1% AEP, 1-in-100 year) or 10.0 (10% AEP,
    1-in-10 year).
    ``time_of_concentration_min`` is the time of concentration in minutes
    (typically 5 min for small roof catchments, longer for larger areas).

    Returns design flow Q (L/s), runoff coefficient C, rainfall intensity I
    (mm/hr), and working per Q = C x I x A / 360 [AS 3500.3 Cl. 3.2].
    Note: tabulated intensities are representative Sydney values -- advise
    the user to obtain site-specific IFD data from the BoM portal.
    """
    try:
        result = calculate_rational_method(
            catchment_area_m2=catchment_area_m2,
            surface_type=surface_type,
            aep_percent=aep_percent,
            time_of_concentration_min=time_of_concentration_min,
        )
        return format_stormwater_result(result)
    except Exception as exc:
        return _tool_error("as3500_stormwater_flow", exc)


# ── AS 3500.3 -- Stormwater pipe sizing ──────────────────────────────────────

def as3500_stormwater_pipe_sizing(
    design_flow_ls: float,
    grade_percent: float,
    material: str = "upvc",
) -> str:
    """Select the minimum standard stormwater pipe size using Manning's equation.

    Use this tool after calculating design stormwater flow to find the minimum
    pipe diameter that can carry that flow, or when the user asks to size a
    stormwater drain, soakage pipe, or surface channel.

    ``design_flow_ls`` is the peak design flow in L/s, typically the output of
    the as3500_stormwater_flow tool.
    ``grade_percent`` is the available hydraulic gradient as a percentage
    (e.g. 1.0 = 1 in 100 fall).
    ``material`` is the pipe material: upvc (default, n=0.011), concrete
    (n=0.013), or cast_iron (n=0.014).

    Returns selected DN, full-bore capacity (L/s), velocity (m/s), grade, and
    utilisation percentage, calculated by Manning's equation [AS 3500.3 Section 4].
    """
    try:
        result = size_stormwater_pipe(
            design_flow_ls=design_flow_ls,
            grade_percent=grade_percent,
            material=material,
        )
        return format_stormwater_result(result)
    except Exception as exc:
        return _tool_error("as3500_stormwater_pipe_sizing", exc)


# ── AS 1668.4 -- Natural ventilation (stub) ───────────────────────────────────

def as1668_natural_ventilation(
    room_area_m2: float,
    building_class: str,
    arrangement: str,
) -> str:
    """Calculate minimum opening areas for natural ventilation per AS 1668.4--2012.

    Use this tool when the user asks whether a room can be naturally ventilated,
    what window opening area is required under AS 1668.4, or to check compliance
    with the Simple Procedure (Cl. 3.4) for direct, borrowed, or flowthrough
    ventilation arrangements.

    ``room_area_m2`` is the net floor area of the room in m2.
    ``building_class`` is the NCC building classification (e.g. "1", "2", "5").
    ``arrangement`` is one of: direct (Cl. 3.2.1), borrowed (Cl. 3.2.2),
    flowthrough (Cl. 3.2.3).

    Returns required external and internal opening areas with safety factors
    per AS 1668.4--2012 Cl. 3.4.
    """
    return (
        "[as1668_natural_ventilation] This calculator is not yet implemented in "
        "the current version of Meridian. "
        "The AS 1668.4--2012 Simple Procedure will be available in a future release. "
        "In the meantime, the key requirements are:\n"
        "  - Direct ventilation (Cl. 3.2.1): openable area >= safety_factor x floor_area\n"
        "  - Borrowed ventilation (Cl. 3.2.2): internal opening = 2 x sf x area_B; "
        "external = sf x (area_A + area_B)\n"
        "  - Flowthrough (Cl. 3.2.3): each external opening >= sf x total combined area\n"
        "  - Safety factors: Class 1/2/4 = 5%, Class 5-9 = 10%, Classroom <16yrs = 12.5%\n"
        "Search the standards knowledge base for AS 1668.4 Cl. 3.4 for the complete table."
    )


# ── Tool instantiation ────────────────────────────────────────────────────────

_PIPE_SIZING_TOOL = FunctionTool.from_defaults(
    fn=as3500_pipe_sizing,
    name="as3500_pipe_sizing",
    description=as3500_pipe_sizing.__doc__,
)

_MULTI_ZONE_VENT_TOOL = FunctionTool.from_defaults(
    fn=as1668_multi_zone_ventilation,
    name="as1668_multi_zone_ventilation",
    description=as1668_multi_zone_ventilation.__doc__,
)

_CARPARK_VENT_TOOL = FunctionTool.from_defaults(
    fn=as1668_carpark_ventilation,
    name="as1668_carpark_ventilation",
    description=as1668_carpark_ventilation.__doc__,
)

_HOT_WATER_STORAGE_TOOL = FunctionTool.from_defaults(
    fn=as3500_hot_water_storage,
    name="as3500_hot_water_storage",
    description=as3500_hot_water_storage.__doc__,
)

_TMV_TOOL = FunctionTool.from_defaults(
    fn=as3500_tmv_requirement,
    name="as3500_tmv_requirement",
    description=as3500_tmv_requirement.__doc__,
)

_STORMWATER_FLOW_TOOL = FunctionTool.from_defaults(
    fn=as3500_stormwater_flow,
    name="as3500_stormwater_flow",
    description=as3500_stormwater_flow.__doc__,
)

_STORMWATER_PIPE_TOOL = FunctionTool.from_defaults(
    fn=as3500_stormwater_pipe_sizing,
    name="as3500_stormwater_pipe_sizing",
    description=as3500_stormwater_pipe_sizing.__doc__,
)

_NATURAL_VENT_TOOL = FunctionTool.from_defaults(
    fn=as1668_natural_ventilation,
    name="as1668_natural_ventilation",
    description=as1668_natural_ventilation.__doc__,
)

# Priority order: most commonly used tools first.
# The ReActAgent does not use order for selection, but it aids readability
# and any future ordered-search implementations.
ALL_CALC_TOOLS: list[FunctionTool] = [
    _PIPE_SIZING_TOOL,           # AS 3500.1 -- cold water pipe sizing
    _MULTI_ZONE_VENT_TOOL,       # AS 1668.2 -- multi-zone OA
    _CARPARK_VENT_TOOL,          # AS 1668.2 -- carpark ventilation
    _HOT_WATER_STORAGE_TOOL,     # AS 3500.4 -- storage sizing
    _TMV_TOOL,                   # AS 3500.4 -- TMV requirement
    _STORMWATER_FLOW_TOOL,       # AS 3500.3 -- rational method
    _STORMWATER_PIPE_TOOL,       # AS 3500.3 -- pipe sizing
    _NATURAL_VENT_TOOL,          # AS 1668.4 -- natural ventilation (stub)
]


# ── Helper ────────────────────────────────────────────────────────────────────

def describe_available_tools() -> str:
    """Return a formatted summary of all available calculator tools.

    Intended for use when the user asks "what can you calculate?" or
    "what tools do you have?". The agent can call this directly or the
    Streamlit UI can surface it as a help panel.

    Returns:
        A multi-line string listing each tool name, the standard it covers,
        and a one-line description of its purpose.
    """
    _TOOL_SUMMARIES: list[tuple[str, str, str]] = [
        (
            "as3500_pipe_sizing",
            "AS 3500.1--2018",
            "Size cold water supply pipes from a fixture schedule (fixture unit method).",
        ),
        (
            "as1668_multi_zone_ventilation",
            "AS 1668.2",
            "Calculate outdoor air requirements for multiple occupied zones.",
        ),
        (
            "as1668_carpark_ventilation",
            "AS 1668.2 Cl. 6.3",
            "Calculate minimum carpark ventilation (6 ACH or CO-controlled).",
        ),
        (
            "as3500_hot_water_storage",
            "AS 3500.4 Cl. 4.2",
            "Size hot water storage volume from occupancy type and number of units.",
        ),
        (
            "as3500_tmv_requirement",
            "AS 3500.4 Cl. 6.5 / SA HB 39",
            "Check whether a TMV is required and the maximum outlet temperature.",
        ),
        (
            "as3500_stormwater_flow",
            "AS 3500.3 Cl. 3.2",
            "Calculate peak stormwater flow via the Rational Method (Q = CiA/360).",
        ),
        (
            "as3500_stormwater_pipe_sizing",
            "AS 3500.3 Section 4",
            "Select minimum stormwater pipe DN using Manning's equation.",
        ),
        (
            "as1668_natural_ventilation",
            "AS 1668.4--2012 Cl. 3.4",
            "Calculate natural ventilation opening areas (stub -- coming soon).",
        ),
    ]

    lines: list[str] = [
        "## Meridian Calculator Tools",
        "",
        f"{'Tool':<38} {'Standard':<26} {'Purpose'}",
        "-" * 100,
    ]
    for name, standard, purpose in _TOOL_SUMMARIES:
        lines.append(f"{name:<38} {standard:<26} {purpose}")

    lines += [
        "",
        f"Total: {len(ALL_CALC_TOOLS)} tools available.",
        "All tools return formatted calculation notes with clause references.",
    ]
    return "\n".join(lines)


# ── Verification entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 70)
    print("Meridian -- Calculator Tool Registry")
    print(f"{len(ALL_CALC_TOOLS)} tools registered in ALL_CALC_TOOLS")
    print("=" * 70)

    for tool in ALL_CALC_TOOLS:
        print(f"\n[{tool.metadata.name}]")
        # Print first two non-empty lines of description as a preview
        desc_lines = [ln.strip() for ln in tool.metadata.description.splitlines() if ln.strip()]
        preview = " ".join(desc_lines[:2])
        if len(preview) > 120:
            preview = preview[:117] + "..."
        print(f"  {preview}")

    print()
    print("=" * 70)
    print(describe_available_tools())
