"""
Meridian -- Psychrometric and cooling load calculator.
Standard: AIRAH DA09 Section 9, Carrier Simplified Method.

Key equations (DA09 references):
  ERSH   (Eq. 4)  -- Effective Room Sensible Heat (W)
  ERLH   (Eq. 5)  -- Effective Room Latent Heat (W)
  ERTH   (Eq. 6)  -- Effective Room Total Heat (W)
  ESHF   (Eq. 26) -- Effective Sensible Heat Factor
  L/s_DA (Eq. 36) -- Dehumidified air quantity (L/s)
  EDB    (Eq. 31) -- Effective Dry Bulb at coil leaving conditions
  LDB    (Eq. 32) -- Leaving Dry Bulb at coil

Key constants:
  Sensible air-side: OASH = 1.20 x L/s x delta_T      (W)
  Latent air-side:   OALH = 3.0  x L/s x delta_omega  (W, omega in g/kg)

Psychrometric property equations:
  Saturation pressure: ASHRAE Magnus equation
  Humidity ratio:      Sprung psychrometer formula
  ADP: iterative -- ESHF line intersection with saturation curve

Case detection thresholds:
  General cooling  -- normal ESHF >= 0.65, ADP >= 5 deg C
  High latent      -- ADP < 5 deg C
  Reheat required  -- ESHF < 0.65
  100% OA          -- outdoor_air_fraction = 1.0

NOTE: The full Carrier Simplified Method (including ADP iteration and
leaving conditions) is implemented in the standalone HTML tool
DA09_Psychrometric_Calculator.html. This Python module provides the
simplified air-side load estimates and psychrometric property calculations
that are sufficient for preliminary sizing and agent-tool responses.
The HTML tool must be used for detailed coil selection and final documentation.
"""

from __future__ import annotations

import math

# ── Air-side constants ─────────────────────────────────────────────────────────

SENSIBLE_FACTOR: float = 1.20   # W / (L/s * K)   -- OASH = 1.20 x L/s x delta_T
LATENT_FACTOR: float = 3.0      # W / (L/s * g/kg) -- OALH = 3.0  x L/s x delta_omega

ESHF_REHEAT_THRESHOLD: float = 0.65   # ESHF < 0.65 -> reheat may be required
ADP_HIGH_LATENT_THRESHOLD: float = 5.0  # ADP < 5 deg C -> high latent case


# ── Psychrometric property functions ──────────────────────────────────────────

def saturation_pressure_kpa(dry_bulb_c: float) -> float:
    """Calculate saturation vapour pressure at ``dry_bulb_c`` via Magnus equation.

    Args:
        dry_bulb_c: Dry bulb temperature in degrees C.

    Returns:
        Saturation pressure in kPa.
    """
    # ASHRAE Fundamentals Magnus form
    return 0.6108 * math.exp(17.27 * dry_bulb_c / (dry_bulb_c + 237.3))


def humidity_ratio_from_wb(
    dry_bulb_c: float,
    wet_bulb_c: float,
    pressure_kpa: float = 101.325,
) -> float:
    """Calculate humidity ratio using the Sprung psychrometer formula.

    Args:
        dry_bulb_c: Dry bulb temperature (deg C).
        wet_bulb_c: Wet bulb temperature (deg C).
        pressure_kpa: Atmospheric pressure (default 101.325 kPa at sea level).

    Returns:
        Humidity ratio in g/kg (grams of water per kg dry air).

    Raises:
        ValueError: If wet_bulb_c > dry_bulb_c.
    """
    if wet_bulb_c > dry_bulb_c:
        raise ValueError(
            f"wet_bulb_c ({wet_bulb_c}) cannot exceed dry_bulb_c ({dry_bulb_c})"
        )
    pws_wb = saturation_pressure_kpa(wet_bulb_c)
    omega_wb = 0.622 * pws_wb / (pressure_kpa - pws_wb)  # saturation humidity ratio at wb
    # Sprung psychrometer formula
    omega = omega_wb - 0.000799 * (dry_bulb_c - wet_bulb_c) * (1 + wet_bulb_c / 610.0)
    return max(omega * 1000.0, 0.0)  # convert kg/kg to g/kg, clamp to 0


def relative_humidity_from_omega(
    dry_bulb_c: float,
    humidity_ratio_g_per_kg: float,
    pressure_kpa: float = 101.325,
) -> float:
    """Calculate relative humidity from humidity ratio.

    Args:
        dry_bulb_c: Dry bulb temperature (deg C).
        humidity_ratio_g_per_kg: Humidity ratio (g/kg).
        pressure_kpa: Atmospheric pressure (kPa).

    Returns:
        Relative humidity as a fraction (0.0 to 1.0).
    """
    omega_kg = humidity_ratio_g_per_kg / 1000.0
    pws = saturation_pressure_kpa(dry_bulb_c)
    pw = omega_kg * pressure_kpa / (0.622 + omega_kg)
    return min(pw / pws, 1.0)


# ── Simplified load calculations ──────────────────────────────────────────────

def calculate_air_side_loads(
    supply_flow_ls: float,
    room_db_c: float,
    supply_db_c: float,
    room_humidity_ratio_g_per_kg: float,
    supply_humidity_ratio_g_per_kg: float,
) -> dict:
    """Calculate sensible, latent, and total cooling capacity for a given airflow.

    Uses the DA09 simplified air-side equations:
      Sensible: Q_s = 1.20 x L/s x (T_room - T_supply)  [W]
      Latent:   Q_l = 3.0  x L/s x (omega_room - omega_supply)  [W]

    Args:
        supply_flow_ls: Supply air flow rate (L/s).
        room_db_c: Room dry bulb temperature (deg C).
        supply_db_c: Supply air dry bulb temperature (deg C).
        room_humidity_ratio_g_per_kg: Room humidity ratio (g/kg).
        supply_humidity_ratio_g_per_kg: Supply air humidity ratio (g/kg).

    Returns:
        Dict with keys: ``supply_flow_ls``, ``sensible_w``, ``latent_w``,
        ``total_w``, ``eshf``, ``case``, ``clause_ref``.
    """
    delta_t = room_db_c - supply_db_c
    delta_omega = room_humidity_ratio_g_per_kg - supply_humidity_ratio_g_per_kg

    sensible_w = SENSIBLE_FACTOR * supply_flow_ls * delta_t
    latent_w = LATENT_FACTOR * supply_flow_ls * max(delta_omega, 0.0)
    total_w = sensible_w + latent_w
    eshf = sensible_w / total_w if total_w > 0 else 1.0

    if eshf < ESHF_REHEAT_THRESHOLD:
        case = "reheat_required"
    elif latent_w > sensible_w:
        case = "high_latent"
    else:
        case = "general_cooling"

    return {
        "supply_flow_ls": supply_flow_ls,
        "delta_t_k": round(delta_t, 2),
        "delta_omega_g_per_kg": round(delta_omega, 3),
        "sensible_w": round(sensible_w, 0),
        "latent_w": round(latent_w, 0),
        "total_w": round(total_w, 0),
        "sensible_kw": round(sensible_w / 1000, 3),
        "latent_kw": round(latent_w / 1000, 3),
        "total_kw": round(total_w / 1000, 3),
        "eshf": round(eshf, 4),
        "case": case,
        "clause_ref": "AIRAH DA09 Section 9, Eqs. 4-6, 26",
    }


def calculate_psychrometrics(
    room_sensible_w: float,
    room_latent_w: float,
    outdoor_db: float,
    outdoor_wb: float,
    room_db: float,
    room_rh: float,
    outdoor_air_fraction: float,
) -> dict:
    """Estimate cooling load parameters using the DA09 simplified air-side method.

    Provides a preliminary estimate of ESHF, estimated design airflow, and
    case classification. For full Carrier Simplified Method output including
    ADP iteration and leaving conditions, use the DA09 HTML tool.

    Args:
        room_sensible_w: Room sensible heat gain (W).
        room_latent_w: Room latent heat gain (W).
        outdoor_db: Outdoor design dry bulb temperature (deg C).
        outdoor_wb: Outdoor design wet bulb temperature (deg C).
        room_db: Room design dry bulb temperature (deg C).
        room_rh: Room design relative humidity as a fraction (0.0-1.0).
        outdoor_air_fraction: Fraction of supply air that is outdoor air (0.0-1.0).

    Returns:
        Dict with keys: ``ersh_w``, ``erlh_w``, ``erth_w``, ``eshf``,
        ``estimated_supply_ls``, ``outdoor_humidity_ratio_g_per_kg``,
        ``room_humidity_ratio_g_per_kg``, ``case``, ``note``, ``clause_ref``.

    Raises:
        ValueError: For invalid inputs.
    """
    if not (0.0 <= outdoor_air_fraction <= 1.0):
        raise ValueError(f"outdoor_air_fraction must be 0-1, got {outdoor_air_fraction}")
    if not (0.0 < room_rh <= 1.0):
        raise ValueError(f"room_rh must be 0-1 (fraction), got {room_rh}")
    if room_sensible_w < 0 or room_latent_w < 0:
        raise ValueError("room_sensible_w and room_latent_w must be non-negative")

    erth_w = room_sensible_w + room_latent_w
    eshf = room_sensible_w / erth_w if erth_w > 0 else 1.0

    # Psychrometric properties
    outdoor_omega = humidity_ratio_from_wb(outdoor_db, outdoor_wb)
    pws_room = saturation_pressure_kpa(room_db)
    # Humidity ratio from RH: omega = 0.622 x phi x pws / (101.325 - phi x pws)
    pw_room = room_rh * pws_room
    room_omega = 0.622 * pw_room / (101.325 - pw_room) * 1000.0  # g/kg

    # Estimated design temperature difference (supply 10-12 K below room is typical)
    # For preliminary estimate: use ESHF to back-calculate delta_T at delta_omega
    delta_omega = room_omega - min(outdoor_omega, room_omega)
    # From ESHF: delta_T = (sensible / latent) * (1/n_factor) * delta_omega
    # Approximate: supply at roughly 12 K below room for a typical ESHF
    estimated_delta_t = 12.0 if eshf > 0.8 else 10.0

    # Estimated supply airflow: Q_s = 1.20 x L/s x delta_T -> L/s = Q_s / (1.20 x delta_T)
    estimated_supply_ls = (
        room_sensible_w / (SENSIBLE_FACTOR * estimated_delta_t)
        if estimated_delta_t > 0 else 0.0
    )

    if eshf < ESHF_REHEAT_THRESHOLD:
        case = "reheat_required"
    elif outdoor_air_fraction >= 1.0:
        case = "100_pct_oa"
    elif eshf < 0.75:
        case = "high_latent"
    else:
        case = "general_cooling"

    note = (
        "PRELIMINARY ESTIMATE ONLY. This module provides simplified air-side calculations. "
        "For full Carrier Simplified Method output (ADP, LDB, EDB, coil leaving conditions "
        "per DA09 Eqs. 31, 32, 36), use the DA09_Psychrometric_Calculator.html tool."
    )
    if case == "reheat_required":
        note = f"ESHF = {eshf:.3f} < {ESHF_REHEAT_THRESHOLD} -- reheat may be required. " + note
    elif case == "high_latent":
        note = f"ESHF = {eshf:.3f} -- high latent load; check ADP temperature. " + note

    return {
        "ersh_w": round(room_sensible_w, 0),
        "erlh_w": round(room_latent_w, 0),
        "erth_w": round(erth_w, 0),
        "ersh_kw": round(room_sensible_w / 1000, 3),
        "erlh_kw": round(room_latent_w / 1000, 3),
        "erth_kw": round(erth_w / 1000, 3),
        "eshf": round(eshf, 4),
        "outdoor_db_c": outdoor_db,
        "outdoor_wb_c": outdoor_wb,
        "outdoor_humidity_ratio_g_per_kg": round(outdoor_omega, 2),
        "room_db_c": room_db,
        "room_rh_pct": round(room_rh * 100, 1),
        "room_humidity_ratio_g_per_kg": round(room_omega, 2),
        "outdoor_air_fraction": outdoor_air_fraction,
        "estimated_supply_ls": round(estimated_supply_ls, 0),
        "estimated_delta_t_k": estimated_delta_t,
        "case": case,
        "note": note,
        "clause_ref": "AIRAH DA09 Section 9, Eqs. 4-6, 26",
    }


def format_psychrometrics_result(result: dict) -> str:
    """Format a psychrometrics result dict as a calculation note.

    Args:
        result: Output of ``calculate_psychrometrics`` or
                ``calculate_air_side_loads``.

    Returns:
        Multi-line formatted string.
    """
    lines: list[str] = [
        "## Psychrometrics -- AIRAH DA09 Section 9 (Simplified)",
        "",
        "### Inputs",
        f"  Room sensible load:     {result.get('ersh_kw', result.get('sensible_kw', '?')):.3f} kW",
        f"  Room latent load:       {result.get('erlh_kw', result.get('latent_kw', '?')):.3f} kW",
        f"  Room total load:        {result.get('erth_kw', result.get('total_kw', '?')):.3f} kW",
        "",
        "### Results",
        f"  ESHF:                   {result['eshf']:.4f}  [DA09 Eq. 26]",
    ]

    if "estimated_supply_ls" in result:
        lines += [
            f"  Est. supply airflow:    {result['estimated_supply_ls']:.0f} L/s  (preliminary)",
            f"  Outdoor air DB/WB:      {result['outdoor_db_c']}/{result['outdoor_wb_c']} deg C",
            f"  Outdoor humidity ratio: {result['outdoor_humidity_ratio_g_per_kg']:.1f} g/kg",
            f"  Room humidity ratio:    {result['room_humidity_ratio_g_per_kg']:.1f} g/kg",
        ]

    lines += [
        f"  Case:                   {result['case'].replace('_', ' ').upper()}",
        "",
        f"  {result.get('note', '')}",
        "",
        f"  [{result['clause_ref']}]",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print("Meridian -- Psychrometrics Worked Example")
    print("AIRAH DA09 Section 9 (Simplified Method)")
    print("=" * 60)

    # Typical Brisbane office: outdoor 34/25 deg C, room 24/50%RH
    result = calculate_psychrometrics(
        room_sensible_w=20000,
        room_latent_w=5000,
        outdoor_db=34.0,
        outdoor_wb=25.0,
        room_db=24.0,
        room_rh=0.50,
        outdoor_air_fraction=0.25,
    )
    print()
    print(format_psychrometrics_result(result))

    print("\n-- Air properties --")
    out_omega = humidity_ratio_from_wb(34.0, 25.0)
    print(f"Outdoor humidity ratio (34 DB / 25 WB): {out_omega:.2f} g/kg")
    pws_r = saturation_pressure_kpa(24.0)
    rh_check = relative_humidity_from_omega(24.0, result["room_humidity_ratio_g_per_kg"])
    print(f"Room RH check: {rh_check*100:.1f}% (input was 50%)")
