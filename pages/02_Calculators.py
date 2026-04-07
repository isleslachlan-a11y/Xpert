"""
Meridian -- Calculator Library page.
Structured form-based interface for all engineering calculators.
Each calculator occupies its own tab with input form, metric results,
calculation working expander, and download button.
"""

from __future__ import annotations

import os

import streamlit as st

st.set_page_config(
    page_title="Calculator Library -- Meridian",
    page_icon="⚙",
    layout="wide",
)

# ── Lazy imports from calculator modules ──────────────────────────────────────
# Deferred so the page loads even if a calculator has an issue.

from calculators.pipe_sizing import (
    FIXTURE_UNITS,
    PIPE_DATA,
    format_pipe_sizing_result,
    size_pipe_from_fixtures,
)
from calculators.ventilation_mechanical import (
    OCCUPANCY_RATES,
    VENTILATION_RATES,
    calculate_multi_zone,
    format_ventilation_result,
)
from calculators.hot_water import (
    DEMAND_RATES,
    TMV_RULES,
    calculate_storage_volume,
    calculate_tmv_requirement,
    format_hot_water_result,
)
from calculators.stormwater import (
    RUNOFF_COEFFICIENTS,
    calculate_rational_method,
    format_stormwater_result,
    size_stormwater_pipe,
)

# ── Human-readable labels ─────────────────────────────────────────────────────

_FIXTURE_LABELS: dict[str, str] = {
    "wc_private":          "WC (private)",
    "wc_public":           "WC (public)",
    "basin_private":       "Basin (private)",
    "basin_public":        "Basin (public)",
    "bath":                "Bath",
    "shower":              "Shower",
    "sink_domestic":       "Sink (domestic)",
    "sink_commercial":     "Sink (commercial)",
    "dishwasher_domestic": "Dishwasher (domestic)",
    "washing_machine":     "Washing Machine",
    "urinal_flush":        "Urinal (flush valve)",
    "hose_tap":            "Hose Tap",
    "drinking_fountain":   "Drinking Fountain",
    "cleaners_sink":       "Cleaner's Sink",
}

_SPACE_LABELS: dict[str, str] = {
    k: k.replace("_", " ").title()
    for k in OCCUPANCY_RATES
    if not VENTILATION_RATES[k].special  # exclude carpark / kitchen_commercial
}

_DEMAND_LABELS: dict[str, str] = {
    "residential_apartment": "Residential Apartment",
    "residential_house":     "Residential House",
    "office":                "Office",
    "restaurant_per_meal":   "Restaurant (per meal)",
    "hotel_guestroom":       "Hotel (per guestroom)",
    "hospital_per_bed":      "Hospital (per bed)",
    "school_per_student":    "School (per student)",
}

_DEMAND_UNIT: dict[str, str] = {
    "residential_apartment": "persons",
    "residential_house":     "persons",
    "office":                "persons",
    "restaurant_per_meal":   "meals/day",
    "hotel_guestroom":       "rooms",
    "hospital_per_bed":      "beds",
    "school_per_student":    "students",
}

_OUTLET_LABELS: dict[str, str] = {
    k: k.replace("_", " ").title() for k in TMV_RULES
}

_SURFACE_LABELS: dict[str, str] = {
    k: k.replace("_", " ").title() for k in RUNOFF_COEFFICIENTS
}

_AEP_OPTIONS: list[str] = ["1% AEP (1 in 100)", "10% AEP (1 in 10)"]
_AEP_VALUES: dict[str, float] = {"1% AEP (1 in 100)": 1.0, "10% AEP (1 in 10)": 10.0}


# ── Session state ─────────────────────────────────────────────────────────────

def _init_session_state() -> None:
    defaults: dict = {
        # Tab 1 -- pipe sizing results
        "pipe_result": None,
        # Tab 2 -- ventilation zones
        "vent_zones": [{"name": "Zone 1", "space_type": "office_open_plan",
                        "floor_area_m2": 100.0, "occupants": None}],
        "vent_result": None,
        # Tab 3 -- hot water results
        "hw_storage_result": None,
        "hw_tmv_result": None,
        # Tab 4 -- stormwater results
        "sw_flow_result": None,
        "sw_pipe_result": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _download_btn(label: str, text: str, filename: str, key: str) -> None:
    st.download_button(
        label=label,
        data=text.encode("utf-8"),
        file_name=filename,
        mime="text/plain",
        key=key,
    )


# ── Tab 1: AS 3500.1 Pipe Sizing ─────────────────────────────────────────────

def _tab_pipe_sizing() -> None:
    st.subheader("AS 3500.1\u20142018 \u2014 Cold Water Pipe Sizing")
    st.caption("Fixture unit method | Velocity limit 3.0 m/s [Cl. 3.4.3] | "
               "Min residual pressure 100 kPa [Cl. 7.4.1]")

    col_in, col_out = st.columns([1, 1], gap="large")

    with col_in:
        st.markdown("**Fixture Schedule**  [AS 3500.1 Table 3.1]")
        fixtures: dict[str, int] = {}
        # Render inputs in 2 mini-columns for compactness
        fc1, fc2 = st.columns(2)
        keys = list(FIXTURE_UNITS.keys())
        half = (len(keys) + 1) // 2
        for i, fk in enumerate(keys):
            col = fc1 if i < half else fc2
            with col:
                val = st.number_input(
                    _FIXTURE_LABELS[fk],
                    min_value=0,
                    max_value=500,
                    value=0,
                    step=1,
                    key=f"pipe_fx_{fk}",
                )
            if val > 0:
                fixtures[fk] = val

        st.markdown("**Pipe Parameters**")
        material = st.selectbox(
            "Pipe Material",
            list(PIPE_DATA.keys()),
            format_func=str.upper,
            key="pipe_material",
        )
        pipe_length = st.number_input(
            "Equivalent Pipe Length (m)",
            min_value=1.0,
            max_value=500.0,
            value=20.0,
            step=0.5,
            key="pipe_length",
        )
        static_pressure = st.number_input(
            "Available Static Pressure (kPa)",
            min_value=0.0,
            max_value=1000.0,
            value=300.0,
            step=10.0,
            key="pipe_pressure",
        )

        if st.button("Calculate Pipe Size", type="primary", key="pipe_calc_btn"):
            if not fixtures:
                st.warning("Enter at least one fixture count above zero.")
            else:
                try:
                    st.session_state.pipe_result = size_pipe_from_fixtures(
                        fixtures=fixtures,
                        material=material,
                        pipe_length_m=pipe_length,
                        static_pressure_kpa=static_pressure,
                    )
                except ValueError as exc:
                    st.error(str(exc))
                    st.session_state.pipe_result = None

    with col_out:
        result = st.session_state.pipe_result
        if result is None:
            st.info("Enter your fixture schedule and click **Calculate Pipe Size**.")
            return

        pipe = result["recommended_pipe"]
        pc = result["pressure_check"]
        all_pass = pipe["compliant"] and pc["pass"]

        # Metric cards
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total FU", f"{result['total_fu']}")
        m2.metric("Design Flow", f"{result['design_flow_ls']} L/s")
        m3.metric("Pipe Size", f"DN{pipe['nominal_size_mm']}")
        m4.metric("Velocity", f"{pipe['velocity_ms']:.3f} m/s",
                  delta=f"{pipe['velocity_ms'] - 3.0:+.3f} m/s vs limit",
                  delta_color="inverse")

        st.divider()

        if all_pass:
            st.success(
                f"DN{pipe['nominal_size_mm']} {material.upper()} **COMPLIES** with AS 3500.1\u20142018.\n\n"
                f"Velocity {pipe['velocity_ms']:.3f} m/s \u2264 3.0 m/s [Cl. 3.4.3]. "
                f"Residual pressure {result['residual_pressure_kpa']:.1f} kPa "
                f"\u2265 100 kPa [Cl. 7.4.1].",
                icon="✅",
            )
        else:
            issues: list[str] = []
            if not pipe["compliant"]:
                issues.append(
                    f"velocity {pipe['velocity_ms']:.3f} m/s exceeds 3.0 m/s [Cl. 3.4.3]"
                )
            if not pc["pass"]:
                issues.append(
                    f"residual pressure {result['residual_pressure_kpa']:.1f} kPa "
                    "below 100 kPa [Cl. 7.4.1]"
                )
            st.warning(
                "**Non-compliant** \u2014 " + "; ".join(issues) + ". Increase pipe size or inlet pressure.",
                icon="⚠️",
            )

        st.caption(f"Friction loss: {result['friction_loss_kpa']:.2f} kPa over {pipe_length} m")

        formatted = format_pipe_sizing_result(result)
        with st.expander("Calculation Working"):
            st.text(formatted)

        _download_btn(
            "Download Calculation Note (.txt)",
            formatted,
            "meridian_pipe_sizing.txt",
            key="pipe_dl",
        )


# ── Tab 2: AS 1668.2 Ventilation ─────────────────────────────────────────────

def _tab_ventilation() -> None:
    st.subheader("AS 1668.2 \u2014 Mechanical Ventilation Outdoor Air")
    st.caption("Design OA = max(person-based, area-based) per Cl. 4.3 | "
               "Office: 10 L/s/person + 0.5 L/s/m\u00b2 [Table 2]")

    # Zone management
    col_hdr, col_btn = st.columns([4, 1])
    with col_hdr:
        st.markdown("**Zone Schedule**  [AS 1668.2 Table 2 / Cl. 4.3]")
    with col_btn:
        if st.button("+ Add Zone", key="vent_add_zone"):
            n = len(st.session_state.vent_zones) + 1
            st.session_state.vent_zones.append(
                {"name": f"Zone {n}", "space_type": "office_open_plan",
                 "floor_area_m2": 100.0, "occupants": None}
            )
            st.rerun()

    space_type_options = list(_SPACE_LABELS.keys())

    zones_to_remove: list[int] = []
    for i, zone in enumerate(st.session_state.vent_zones):
        with st.container(border=True):
            zc1, zc2, zc3, zc4, zc5 = st.columns([2, 2, 1.5, 1.5, 0.5])
            with zc1:
                zone["name"] = st.text_input(
                    "Zone Name", value=zone["name"], key=f"vent_name_{i}"
                )
            with zc2:
                zone["space_type"] = st.selectbox(
                    "Space Type",
                    options=space_type_options,
                    index=space_type_options.index(zone["space_type"])
                    if zone["space_type"] in space_type_options else 0,
                    format_func=lambda k: _SPACE_LABELS[k],
                    key=f"vent_stype_{i}",
                )
            with zc3:
                zone["floor_area_m2"] = st.number_input(
                    "Floor Area (m\u00b2)",
                    min_value=1.0,
                    max_value=50000.0,
                    value=float(zone["floor_area_m2"]),
                    step=10.0,
                    key=f"vent_area_{i}",
                )
            with zc4:
                override = st.number_input(
                    "Override Occupants",
                    min_value=0,
                    max_value=10000,
                    value=0,
                    step=1,
                    key=f"vent_occ_{i}",
                    help="Leave 0 to use AS 1668.2 Table 2 default density",
                )
                zone["occupants"] = int(override) if override > 0 else None
            with zc5:
                st.markdown("<br>", unsafe_allow_html=True)
                if len(st.session_state.vent_zones) > 1:
                    if st.button("✕", key=f"vent_del_{i}", help="Remove zone"):
                        zones_to_remove.append(i)

    if zones_to_remove:
        for idx in sorted(zones_to_remove, reverse=True):
            st.session_state.vent_zones.pop(idx)
        st.rerun()

    st.divider()

    if st.button("Calculate All Zones", type="primary", key="vent_calc_btn"):
        try:
            zones_input = [
                {
                    "name": z["name"],
                    "space_type": z["space_type"],
                    "floor_area_m2": z["floor_area_m2"],
                    "occupants": z["occupants"],
                }
                for z in st.session_state.vent_zones
            ]
            st.session_state.vent_result = calculate_multi_zone(zones_input)
        except Exception as exc:
            st.error(str(exc))
            st.session_state.vent_result = None

    result = st.session_state.vent_result
    if result is None:
        return

    # Summary metrics
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Total OA", f"{result['total_oa_ls']:.1f} L/s")
    mc2.metric("Total Floor Area", f"{result['total_floor_area_m2']:.0f} m\u00b2")
    mc3.metric("Weighted OA Intensity", f"{result['weighted_oa_per_m2']:.3f} L/s/m\u00b2")

    # Zone table
    if result["zone_results"]:
        import pandas as pd
        rows = [
            {
                "Zone": z.get("zone_name", ""),
                "Space Type": z["space_type"].replace("_", " ").title(),
                "Area (m\u00b2)": z["floor_area_m2"],
                "Persons": z["occupants"],
                "Occupant OA (L/s)": z["occupant_oa_ls"],
                "Area OA (L/s)": z["area_oa_ls"],
                "Design OA (L/s)": z["design_oa_ls"],
                "Governs": z["governing_criterion"],
            }
            for z in result["zone_results"]
        ]
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

    if result["skipped_zones"]:
        with st.expander(f"{len(result['skipped_zones'])} zone(s) excluded (special method required)"):
            for s in result["skipped_zones"]:
                st.caption(s)

    # Warnings from individual zones
    for z in result["zone_results"]:
        if z.get("high_density_warning"):
            st.warning(f"{z.get('zone_name', z['space_type'])}: {z['high_density_warning']}")

    formatted = format_ventilation_result(result)
    with st.expander("Calculation Working"):
        st.text(formatted)

    _download_btn(
        "Download Calculation Note (.txt)",
        formatted,
        "meridian_ventilation.txt",
        key="vent_dl",
    )


# ── Tab 3: AS 3500.4 Hot Water ────────────────────────────────────────────────

def _tab_hot_water() -> None:
    st.subheader("AS 3500.4 \u2014 Hot Water Storage Sizing & TMV Requirements")
    st.caption("Storage \u2265 60\u00b0C for Legionella control | TMV per Cl. 6.5 / SA HB 39")

    col_a, col_b = st.columns([1, 1], gap="large")

    with col_a:
        st.markdown("**Storage Sizing**  [AS 3500.4 Cl. 4.2]")
        occ_keys = list(_DEMAND_LABELS.keys())
        occ_type = st.selectbox(
            "Occupancy Type",
            options=occ_keys,
            format_func=lambda k: _DEMAND_LABELS[k],
            key="hw_occ_type",
        )
        unit_label = _DEMAND_UNIT[occ_type]
        num_units = st.number_input(
            f"Number of {unit_label}",
            min_value=1,
            max_value=10000,
            value=10,
            step=1,
            key="hw_num_units",
        )

        st.divider()
        st.markdown("**TMV Requirement**  [AS 3500.4 Cl. 6.5 / SA HB 39]")
        supply_temp = st.number_input(
            "Hot Water Supply Temperature (\u00b0C)",
            min_value=20.0,
            max_value=95.0,
            value=65.0,
            step=1.0,
            key="hw_supply_temp",
        )
        outlet_keys = list(_OUTLET_LABELS.keys())
        outlet_type = st.selectbox(
            "Outlet Type",
            options=outlet_keys,
            format_func=lambda k: _OUTLET_LABELS[k],
            key="hw_outlet_type",
        )

        if st.button("Calculate", type="primary", key="hw_calc_btn"):
            try:
                st.session_state.hw_storage_result = calculate_storage_volume(occ_type, num_units)
                st.session_state.hw_tmv_result = calculate_tmv_requirement(supply_temp, outlet_type)
            except Exception as exc:
                st.error(str(exc))
                st.session_state.hw_storage_result = None
                st.session_state.hw_tmv_result = None

    with col_b:
        sr = st.session_state.hw_storage_result
        tr = st.session_state.hw_tmv_result

        if sr is None and tr is None:
            st.info("Configure inputs and click **Calculate**.")
            return

        if sr:
            st.markdown("**Storage Result**")
            sm1, sm2 = st.columns(2)
            sm1.metric("Daily Demand", f"{sr['daily_demand_l']:.0f} L/day")
            sm2.metric("Storage Volume", f"{sr['storage_volume_l']:.0f} L")
            st.caption(
                f"Recovery factor: {sr['recovery_factor']} \u00d7 daily demand "
                f"[AS 3500.4 Cl. 4.2]"
            )
            st.info(
                f"Storage must be maintained \u2265 {sr['min_storage_temp_c']:.0f}\u00b0C "
                "to control Legionella [AS 3500.4].",
                icon="ℹ️",
            )

        st.divider()

        if tr:
            st.markdown("**TMV Result**")
            if tr["legionella_risk"]:
                st.error(
                    f"Storage at {tr['supply_temp_c']}\u00b0C is BELOW 60\u00b0C minimum "
                    "required for Legionella control [AS 3500.4]. Increase storage temperature.",
                    icon="⚠️",
                )
            if tr["tmv_required"]:
                st.warning(
                    f"**TMV REQUIRED** \u2014 {_OUTLET_LABELS[outlet_type]}. "
                    f"Maximum outlet temperature: **{tr['max_outlet_temp_c']}\u00b0C** "
                    f"[AS 3500.4 Cl. 6.5].",
                    icon="🔴",
                )
            else:
                st.success(
                    f"TMV not required for {_OUTLET_LABELS[outlet_type]}. "
                    f"Supply at {tr['supply_temp_c']}\u00b0C is within limits.",
                    icon="✅",
                )
            if tr["state_note"]:
                st.caption(f"State note: {tr['state_note']}")

        if sr and tr:
            combined = format_hot_water_result(sr) + "\n\n" + format_hot_water_result(tr)
            with st.expander("Calculation Working"):
                st.text(combined)
            _download_btn(
                "Download Calculation Note (.txt)",
                combined,
                "meridian_hot_water.txt",
                key="hw_dl",
            )


# ── Tab 4: AS 3500.3 Stormwater ───────────────────────────────────────────────

def _tab_stormwater() -> None:
    st.subheader("AS 3500.3 \u2014 Stormwater Rational Method & Pipe Sizing")
    st.caption("Q = C \u00d7 I \u00d7 A / 360  [AS 3500.3 Cl. 3.2] | "
               "Pipe sizing by Manning's equation [Section 4]")

    col_in, col_out = st.columns([1, 1], gap="large")

    with col_in:
        catchment_area = st.number_input(
            "Catchment Area (m\u00b2)",
            min_value=1.0,
            max_value=500000.0,
            value=500.0,
            step=10.0,
            key="sw_area",
        )
        surface_keys = list(RUNOFF_COEFFICIENTS.keys())
        surface_type = st.selectbox(
            "Surface Type",
            options=surface_keys,
            format_func=lambda k: _SURFACE_LABELS[k],
            key="sw_surface",
        )
        st.caption(
            f"Runoff coefficient C = {RUNOFF_COEFFICIENTS[surface_type]} "
            "[AS 3500.3 Table 3.1]"
        )
        aep_choice = st.selectbox(
            "Design Storm AEP",
            options=_AEP_OPTIONS,
            key="sw_aep",
        )
        tc = st.number_input(
            "Time of Concentration (min)",
            min_value=2.0,
            max_value=120.0,
            value=5.0,
            step=1.0,
            key="sw_tc",
            help="Typically 5 min for small roof catchments. "
                 "Use inlet time + pipe travel time for larger catchments.",
        )
        grade = st.number_input(
            "Pipe Grade (%)",
            min_value=0.1,
            max_value=20.0,
            value=1.0,
            step=0.1,
            key="sw_grade",
            help="Hydraulic gradient as a percentage (1.0 = 1 in 100 fall)",
        )
        pipe_material = st.selectbox(
            "Pipe Material",
            options=["upvc", "concrete", "cast_iron"],
            format_func=str.upper,
            key="sw_mat",
        )

        if st.button("Calculate", type="primary", key="sw_calc_btn"):
            aep_val = _AEP_VALUES[aep_choice]
            try:
                st.session_state.sw_flow_result = calculate_rational_method(
                    catchment_area_m2=catchment_area,
                    surface_type=surface_type,
                    aep_percent=aep_val,
                    time_of_concentration_min=tc,
                )
                st.session_state.sw_pipe_result = size_stormwater_pipe(
                    design_flow_ls=st.session_state.sw_flow_result["Q_ls"],
                    grade_percent=grade,
                    material=pipe_material,
                )
            except Exception as exc:
                st.error(str(exc))
                st.session_state.sw_flow_result = None
                st.session_state.sw_pipe_result = None

    with col_out:
        fr = st.session_state.sw_flow_result
        pr = st.session_state.sw_pipe_result

        if fr is None:
            st.info("Configure catchment parameters and click **Calculate**.")
            st.markdown(
                "**Key formula:**\n\n"
                "$$Q = \\frac{C \\times I \\times A}{360}$$\n\n"
                "where Q is in L/s, I in mm/hr, A in m\u00b2."
            )
            return

        fm1, fm2 = st.columns(2)
        fm1.metric("Rainfall Intensity", f"{fr['I_mm_per_hr']} mm/hr",
                   help=f"{fr['aep_percent']}% AEP, {fr['selected_duration_min']} min duration")
        fm2.metric("Design Flow", f"{fr['Q_ls']:.2f} L/s")

        if pr:
            pm1, pm2, pm3 = st.columns(3)
            pm1.metric("Selected Pipe", f"DN{pr['selected_diameter_mm']}")
            pm2.metric("Pipe Capacity", f"{pr['capacity_ls']:.2f} L/s")
            pm3.metric("Velocity", f"{pr['velocity_ms']:.3f} m/s")

            st.divider()
            utilisation = fr["Q_ls"] / pr["capacity_ls"] * 100
            if pr["compliant"]:
                st.success(
                    f"DN{pr['selected_diameter_mm']} {pipe_material.upper()} **COMPLIES** "
                    f"\u2014 capacity {pr['capacity_ls']:.2f} L/s > design flow {fr['Q_ls']:.2f} L/s "
                    f"({utilisation:.0f}% utilisation) [AS 3500.3 Section 4].",
                    icon="✅",
                )
            else:
                st.warning(
                    f"No standard size at {grade}% grade can carry {fr['Q_ls']:.2f} L/s. "
                    "Increase pipe grade or contact engineer for non-standard solution.",
                    icon="⚠️",
                )

        st.caption(
            "\u26a0\ufe0f Tabulated intensities are representative Sydney values. "
            "Obtain site-specific IFD data from the BoM IFD portal for project submissions."
        )

        combined = format_stormwater_result(fr)
        if pr:
            combined += "\n\n" + format_stormwater_result(pr)

        with st.expander("Calculation Working"):
            st.text(combined)

        _download_btn(
            "Download Calculation Note (.txt)",
            combined,
            "meridian_stormwater.txt",
            key="sw_dl",
        )


# ── Tab 5: AS 1668.4 Natural Ventilation ─────────────────────────────────────

def _tab_natural_ventilation() -> None:
    st.subheader("AS 1668.4\u20142012 \u2014 Natural Ventilation")
    st.caption("Simple Procedure (Cl. 3.4) \u2014 minimum openable window areas")

    # Check for HTML tool
    html_path = os.path.join(
        os.path.dirname(__file__), "..", "AS1668_4_Ventilation_Calculator.html"
    )
    if os.path.isfile(html_path):
        st.markdown(
            f"[\U0001f4c4 Open AS 1668.4 Calculator (HTML)]({html_path})"
        )
    else:
        st.info(
            "The AS 1668.4 Natural Ventilation Calculator is available as a standalone "
            "HTML tool. Add **AS1668_4_Ventilation_Calculator.html** to the project root "
            "to enable the link here.",
            icon="ℹ️",
        )

    st.divider()
    st.markdown("**Quick Reference \u2014 Simple Procedure Key Formulae**")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            "**Safety factors by building class** [AS 1668.4 Cl. 3.4]:\n\n"
            "| Class | Factor |\n|---|---|\n"
            "| 1, 2, 4 | 5% |\n"
            "| 5\u20139 | 10% |\n"
            "| Classroom <16 yrs | 12.5% |"
        )
    with col2:
        st.markdown(
            "**Arrangement formulae** [AS 1668.4 Cl. 3.2]:\n\n"
            "**Direct** (Cl. 3.2.1): A\u2099\u2091\u209c \u2265 sf \u00d7 A\u1D63\u1D52\u1D52\u1D6d\n\n"
            "**Borrowed** (Cl. 3.2.2): A\u1D62\u207f\u209c = 2 \u00d7 sf \u00d7 A_B; "
            "A\u1D49\u2093\u209c = sf \u00d7 (A_A + A_B)\n\n"
            "**Flowthrough** (Cl. 3.2.3): each external \u2265 sf \u00d7 total combined area"
        )

    st.divider()
    st.markdown("**Inline Quick Estimate**")
    qe1, qe2, qe3 = st.columns(3)
    with qe1:
        room_area = st.number_input(
            "Room Floor Area (m\u00b2)",
            min_value=1.0, max_value=5000.0, value=20.0, step=1.0, key="nv_area",
        )
    with qe2:
        bldg_class = st.selectbox(
            "Building Class",
            options=["Class 1/2/4 (5%)", "Class 5-9 (10%)", "Classroom <16yrs (12.5%)"],
            key="nv_class",
        )
    with qe3:
        arrangement = st.selectbox(
            "Arrangement", options=["Direct", "Borrowed", "Flowthrough"], key="nv_arr"
        )

    sf_map = {"Class 1/2/4 (5%)": 0.05, "Class 5-9 (10%)": 0.10, "Classroom <16yrs (12.5%)": 0.125}
    sf = sf_map[bldg_class]

    if arrangement == "Direct":
        req_ext = sf * room_area
        st.metric("Required External Opening Area", f"{req_ext:.2f} m\u00b2",
                  help=f"= {sf*100:.1f}% \u00d7 {room_area} m\u00b2 [AS 1668.4 Cl. 3.4]")
    elif arrangement == "Borrowed":
        area_b_val = st.number_input(
            "Area of Room B (m\u00b2)", min_value=1.0, value=10.0, step=1.0, key="nv_areab"
        )
        req_int = 2 * sf * area_b_val
        req_ext = sf * (room_area + area_b_val)
        bc1, bc2 = st.columns(2)
        bc1.metric("Required Internal Opening (A\u1D62\u207f\u209c)", f"{req_int:.2f} m\u00b2")
        bc2.metric("Required External Opening (A\u1D49\u2093\u209c)", f"{req_ext:.2f} m\u00b2")
    else:  # Flowthrough
        total_area = room_area
        req_each = sf * total_area
        st.metric("Required Opening Area (each end)", f"{req_each:.2f} m\u00b2",
                  help=f"Each external opening \u2265 {sf*100:.1f}% \u00d7 {total_area} m\u00b2")

    st.caption(
        "This is a simplified quick estimate only. Use the full HTML calculator or "
        "refer to AS 1668.4\u20142012 Cl. 3.4 for the complete procedure including "
        "corrections for obstructions and stack effect."
    )


# ── Tab 6: DA09 Psychrometrics ────────────────────────────────────────────────

def _tab_psychrometrics() -> None:
    st.subheader("AIRAH DA09 \u2014 Psychrometrics & Cooling Load")
    st.caption("Carrier Simplified Method \u2014 AIRAH DA09 Section 9")

    html_path = os.path.join(
        os.path.dirname(__file__), "..", "DA09_Psychrometric_Calculator.html"
    )
    if os.path.isfile(html_path):
        st.markdown(
            f"[\U0001f4c4 Open DA09 Psychrometric Calculator (HTML)]({html_path})"
        )
    else:
        st.info(
            "The DA09 Psychrometric Calculator is available as a standalone HTML tool. "
            "Add **DA09_Psychrometric_Calculator.html** to the project root to enable "
            "the link here.",
            icon="ℹ️",
        )

    st.divider()
    st.markdown("**Quick Reference \u2014 Carrier Simplified Method Key Equations**")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            "**Load equations** [AIRAH DA09 Sect. 9]:\n\n"
            "- ERSH = Eq. 4 (Effective Room Sensible Heat, W)\n"
            "- ERLH = Eq. 5 (Effective Room Latent Heat, W)\n"
            "- ESHF = ERSH / (ERSH + ERLH)  [Eq. 26]\n"
            "- L/s\u209a\u2095 = Eq. 36 (Dehumidified air quantity)\n\n"
            "**Key air-side constants:**\n\n"
            "- Sensible: OASH = **1.20** \u00d7 L/s \u00d7 \u0394T\n"
            "- Latent: OALH = **3.0** \u00d7 L/s \u00d7 \u0394\u03c9 (g/kg)"
        )
    with col2:
        st.markdown(
            "**Psychrometric properties:**\n\n"
            "Saturation pressure via ASHRAE Magnus equation.\n\n"
            "Humidity ratio via Sprung psychrometer formula.\n\n"
            "**Case detection thresholds:**\n\n"
            "| Case | Condition |\n|---|---|\n"
            "| General cooling | Normal |\n"
            "| High latent | ADP < 5\u00b0C |\n"
            "| Reheat | ESHF < 0.65 |\n"
            "| 100% OA | No return air |"
        )

    st.divider()
    st.markdown("**Quick Sensible Heat Estimate**")

    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        flow_ls = st.number_input(
            "Supply Air Flow (L/s)",
            min_value=1.0, max_value=100000.0, value=500.0, step=10.0, key="da09_flow",
        )
    with pc2:
        delta_t = st.number_input(
            "\u0394T Supply vs Room (\u00b0C)",
            min_value=0.1, max_value=30.0, value=10.0, step=0.5, key="da09_dt",
        )
    with pc3:
        delta_w = st.number_input(
            "\u0394\u03c9 Moisture Difference (g/kg)",
            min_value=0.0, max_value=20.0, value=5.0, step=0.5, key="da09_dw",
        )

    sensible_w = 1.20 * flow_ls * delta_t
    latent_w = 3.0 * flow_ls * delta_w
    total_w = sensible_w + latent_w
    eshf = sensible_w / total_w if total_w > 0 else 1.0

    rm1, rm2, rm3, rm4 = st.columns(4)
    rm1.metric("Sensible Capacity", f"{sensible_w / 1000:.2f} kW",
               help="1.20 \u00d7 L/s \u00d7 \u0394T")
    rm2.metric("Latent Capacity", f"{latent_w / 1000:.2f} kW",
               help="3.0 \u00d7 L/s \u00d7 \u0394\u03c9")
    rm3.metric("Total Capacity", f"{total_w / 1000:.2f} kW")
    rm4.metric("ESHF", f"{eshf:.3f}",
               help="Effective Sensible Heat Factor = Sensible / Total")

    if delta_w > 0:
        if eshf < 0.65:
            st.warning(
                f"ESHF = {eshf:.3f} < 0.65 \u2014 reheat may be required. "
                "Use the full DA09 HTML calculator to determine ADP and leaving conditions.",
                icon="⚠️",
            )
        elif latent_w > 0 and (latent_w / 1000) > 0:
            st.info(
                f"ESHF = {eshf:.3f}. "
                "Use the full DA09 HTML calculator for ADP, leaving dry bulb (LDB/EDB), "
                "and dehumidified air quantity per DA09 Eqs. 31, 32 and 36.",
                icon="ℹ️",
            )

    st.caption(
        "Quick estimate only. Constants: sensible = 1.20 W/(L/s\u00b7K), "
        "latent = 3.0 W/(L/s\u00b7g/kg). Full Carrier Simplified Method in DA09 HTML tool."
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _init_session_state()

    st.title("\u2699 Calculator Library")
    st.caption("AS/NZS Standards \u00b7 AIRAH \u00b7 Structured calculation with printable output")

    tabs = st.tabs([
        "AS 3500.1 Pipe Sizing",
        "AS 1668.2 Ventilation",
        "AS 3500.4 Hot Water",
        "AS 3500.3 Stormwater",
        "AS 1668.4 Natural Vent",
        "DA09 Psychrometrics",
    ])

    with tabs[0]:
        _tab_pipe_sizing()

    with tabs[1]:
        _tab_ventilation()

    with tabs[2]:
        _tab_hot_water()

    with tabs[3]:
        _tab_stormwater()

    with tabs[4]:
        _tab_natural_ventilation()

    with tabs[5]:
        _tab_psychrometrics()


main()
