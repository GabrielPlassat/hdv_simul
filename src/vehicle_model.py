"""
Vehicle energy consumption models for Battery Electric Trucks (BET)
Based on: Öko-Institut / ELV-LIVE study (2025)
"Real-world data analysis of energy consumption, activity and charging
 patterns of battery electric trucks operating in Germany"

Two complementary models:
  1. Empirical regression model  (Eq. 2 of the study)
  2. Physics-based longitudinal dynamics model
"""

import numpy as np

# ──────────────────────────────────────────────────────────────────────────────
# 1. EMPIRICAL MODEL (calibrated from real eActros 300/400 data)
# ──────────────────────────────────────────────────────────────────────────────
# Formula (equation 2 of the study):
#   C [kWh/km] = m1 * exp(-k1 * s) + m2 * t + m3 * w + m4 * a + m5
#
# Variable meanings:
#   s = average speed          [km/h]
#   t = exterior temperature   [°C]
#   w = gross combination weight [tonnes]
#   a = altitude difference    [m]  (end_alt - start_alt over the trip)
#
# Coefficients estimated from study results (executive summary p.4):
#   • +0.18 kWh/km per +10 t  → m3 ≈ 0.018
#   • −0.13 kWh/km per +10 °C → m2 ≈ −0.013
#   • k1 ≈ 0.17 (fitted from speed curve, eq. 1)
#   • m1 calibrated so that at s=44 km/h, w=20 t, t=12 °C, a=0 → C ≈ 1.05 kWh/km
#   • m4 calibrated from altitude slope figure (≈ 0.001 kWh/km/m)
#   • m5 = intercept

EMPIRICAL_COEFFICIENTS = {
    # k1 = 0.17 from Eq.1 fit in the study (speed-only curve)
    "k1": 0.17,
    # m1 calibrated so that at very low speed (s~2 km/h), the
    # startup peak gives C ~ 5-10 kWh/km as seen in Figure 3-1
    "m1": 4.50,
    # m2 = -0.013 : -0.13 kWh/km per +10°C (executive summary)
    "m2": -0.013,
    # m3 = 0.018 : +0.18 kWh/km per +10 tonnes (executive summary)
    "m3": 0.018,
    # m4 = 0.0011 : ~+0.11 kWh/km per +100 m altitude diff (Fig 3-4 slope)
    "m4": 0.0011,
    # m5 = intercept calibrated so that at s=44, t=12, w=20, a=0 → C ≈ 1.05
    # C = m1*exp(-k1*s) + m2*t + m3*w + m4*a + m5
    # ≈ 0 + (-0.156) + 0.36 + 0 + m5 = 1.05  → m5 = 0.846
    "m5": 0.85,
    "tcu_penalty": 0.092,  # extra for Temperature Control Unit [kWh/km]
}


def empirical_consumption(
    speed_kmh: float,
    temperature_c: float,
    weight_tonnes: float,
    altitude_diff_m: float,
    has_tcu: bool = False,
    coeffs: dict = None,
) -> float:
    """
    Empirical energy consumption model (ELV-LIVE Eq. 2).

    Returns average consumption C [kWh/km].
    """
    if coeffs is None:
        coeffs = EMPIRICAL_COEFFICIENTS

    k1, m1 = coeffs["k1"], coeffs["m1"]
    m2, m3, m4, m5 = coeffs["m2"], coeffs["m3"], coeffs["m4"], coeffs["m5"]

    speed_term  = m1 * np.exp(-k1 * speed_kmh)
    temp_term   = m2 * temperature_c
    weight_term = m3 * weight_tonnes
    alt_term    = m4 * altitude_diff_m

    C = speed_term + temp_term + weight_term + alt_term + m5

    if has_tcu:
        C += coeffs["tcu_penalty"]

    return max(C, 0.1)   # physical lower bound


# ──────────────────────────────────────────────────────────────────────────────
# 2. PHYSICS-BASED MODEL  (longitudinal force balance)
# ──────────────────────────────────────────────────────────────────────────────
# Energy at wheels:
#   E_traction = ∫ F_total · ds
#   F_total = F_rolling + F_aero + F_grade + F_accel
#
# With regenerative braking (recuperation):
#   E_regen = η_regen · ∫ F_brake · ds   (on downhill or deceleration)
#
# Net battery energy:
#   E_battery = (E_traction / η_drivetrain) - E_regen + E_aux

# Physical constants
GRAVITY = 9.81       # m/s²
AIR_DENSITY = 1.225  # kg/m³ at 15 °C, sea level

# Default vehicle parameters (Daimler eActros 400 6×4)
DEFAULT_VEHICLE = {
    # ── Geometry & Mass ──────────────────────────────────────
    "gross_weight_t": 40.0,          # GVW [tonnes]
    "curb_weight_t": 12.4,           # unladen vehicle [tonnes]
    "payload_t": 0.0,                # cargo [tonnes]

    # ── Aerodynamics ─────────────────────────────────────────
    "drag_coeff_Cd": 0.55,           # drag coefficient [-]
    "frontal_area_m2": 9.5,          # frontal area [m²]

    # ── Rolling resistance ───────────────────────────────────
    "rolling_resist_Cr": 0.007,      # rolling resistance coefficient [-]

    # ── Drivetrain efficiencies ───────────────────────────────
    "motor_efficiency": 0.92,        # motor efficiency [-]
    "transmission_efficiency": 0.97, # gearbox [-]
    "regen_efficiency": 0.70,        # recuperation efficiency [-]
    "battery_efficiency": 0.97,      # charge/discharge efficiency [-]

    # ── Auxiliaries ───────────────────────────────────────────
    "aux_power_kw": 2.0,             # base auxiliaries (lighting, HVAC cab) [kW]
    "tcu_power_kw": 5.0,             # temperature control unit [kW]

    # ── Battery ───────────────────────────────────────────────
    "battery_capacity_kwh": 400.0,   # usable capacity [kWh]
    "initial_soc_pct": 100.0,        # initial SoC [%]
}

# Typical vehicle presets
VEHICLE_PRESETS = {
    "eActros 300 (4×2, 37t)": {
        **DEFAULT_VEHICLE,
        "gross_weight_t": 37.0,
        "curb_weight_t": 11.0,
        "battery_capacity_kwh": 300.0,
        "frontal_area_m2": 9.0,
        "drag_coeff_Cd": 0.52,
    },
    "eActros 400 (6×4, 40t)": DEFAULT_VEHICLE,
    "eActros 600 (semi, 44t)": {
        **DEFAULT_VEHICLE,
        "gross_weight_t": 44.0,
        "curb_weight_t": 10.5,
        "battery_capacity_kwh": 600.0,
        "frontal_area_m2": 10.0,
        "drag_coeff_Cd": 0.48,
    },
    "Poids léger électrique (26t)": {
        **DEFAULT_VEHICLE,
        "gross_weight_t": 26.0,
        "curb_weight_t": 8.0,
        "battery_capacity_kwh": 200.0,
        "frontal_area_m2": 8.5,
        "drag_coeff_Cd": 0.50,
    },
}


def physics_consumption_segment(
    speed_ms: float,
    slope_deg: float,
    accel_ms2: float,
    vehicle: dict,
    temperature_c: float = 15.0,
    has_tcu: bool = False,
) -> dict:
    """
    Instantaneous power demand [kW] for a single segment.

    Args:
        speed_ms:      vehicle speed [m/s]
        slope_deg:     road slope [degrees, positive = uphill]
        accel_ms2:     acceleration [m/s²]
        vehicle:       vehicle parameter dict
        temperature_c: ambient temperature [°C]
        has_tcu:       temperature control unit active

    Returns:
        dict with traction_kw, regen_kw, aux_kw, net_kw
    """
    slope_rad = np.radians(slope_deg)
    mass_kg   = (vehicle["curb_weight_t"] + vehicle["payload_t"]) * 1000.0

    # Forces [N]
    F_rolling = vehicle["rolling_resist_Cr"] * mass_kg * GRAVITY * np.cos(slope_rad)
    F_aero    = 0.5 * AIR_DENSITY * vehicle["drag_coeff_Cd"] * vehicle["frontal_area_m2"] * speed_ms**2
    F_grade   = mass_kg * GRAVITY * np.sin(slope_rad)
    F_inertia = mass_kg * accel_ms2

    F_total = F_rolling + F_aero + F_grade + F_inertia

    eta_chain = vehicle["motor_efficiency"] * vehicle["transmission_efficiency"]

    if F_total >= 0:
        # Traction mode
        traction_kw = (F_total * speed_ms) / (eta_chain * 1000.0)
        regen_kw    = 0.0
    else:
        # Braking/regen mode
        traction_kw = 0.0
        regen_kw    = abs(F_total * speed_ms) * vehicle["regen_efficiency"] / 1000.0

    # Auxiliaries: temperature dependent HVAC adjustment
    delta_T = abs(temperature_c - 20.0)
    hvac_factor = 1.0 + 0.02 * delta_T       # +2% per °C deviation from 20°C
    aux_kw = vehicle["aux_power_kw"] * hvac_factor

    if has_tcu:
        aux_kw += vehicle["tcu_power_kw"]

    net_kw = (traction_kw + aux_kw - regen_kw) / vehicle.get("battery_efficiency", 0.97)

    return {
        "traction_kw": traction_kw,
        "regen_kw":    regen_kw,
        "aux_kw":      aux_kw,
        "net_kw":      max(net_kw, -regen_kw),  # battery limited
        "F_rolling_N": F_rolling,
        "F_aero_N":    F_aero,
        "F_grade_N":   F_grade,
    }


def physics_consumption_route(
    route_segments: list,
    vehicle: dict,
    temperature_c: float = 15.0,
    avg_speed_kmh: float = 50.0,
    has_tcu: bool = False,
) -> dict:
    """
    Compute energy consumption over a complete route.

    Args:
        route_segments: list of dicts with keys:
                         - distance_m  [m]
                         - slope_deg   [degrees]
                         - speed_kmh   [km/h] (optional, overrides avg_speed_kmh)
        vehicle:        vehicle parameter dict
        temperature_c:  ambient temperature [°C]
        avg_speed_kmh:  fallback average speed [km/h]
        has_tcu:        TCU active

    Returns:
        dict with energy totals and per-segment breakdown
    """
    total_traction_kwh   = 0.0
    total_regen_kwh      = 0.0
    total_aux_kwh        = 0.0
    total_distance_m     = 0.0
    segment_results      = []
    soc_pct              = vehicle.get("initial_soc_pct", 100.0)
    battery_kwh          = vehicle["battery_capacity_kwh"]

    for seg in route_segments:
        dist_m    = seg["distance_m"]
        slope_deg = seg.get("slope_deg", 0.0)
        spd_kmh   = seg.get("speed_kmh", avg_speed_kmh)
        spd_ms    = spd_kmh / 3.6
        dt_s      = dist_m / max(spd_ms, 0.1)   # time [s]

        result = physics_consumption_segment(
            speed_ms      = spd_ms,
            slope_deg     = slope_deg,
            accel_ms2     = 0.0,
            vehicle       = vehicle,
            temperature_c = temperature_c,
            has_tcu       = has_tcu,
        )

        seg_traction_kwh = result["traction_kw"] * dt_s / 3600.0
        seg_regen_kwh    = result["regen_kw"]    * dt_s / 3600.0
        seg_aux_kwh      = result["aux_kw"]       * dt_s / 3600.0
        seg_net_kwh      = result["net_kw"]       * dt_s / 3600.0

        total_traction_kwh += seg_traction_kwh
        total_regen_kwh    += seg_regen_kwh
        total_aux_kwh      += seg_aux_kwh
        total_distance_m   += dist_m

        # Update SoC
        soc_pct -= (seg_net_kwh / battery_kwh) * 100.0
        soc_pct  = max(0.0, min(100.0, soc_pct))

        segment_results.append({
            "distance_m":  dist_m,
            "slope_deg":   slope_deg,
            "speed_kmh":   spd_kmh,
            "net_kwh":     seg_net_kwh,
            "regen_kwh":   seg_regen_kwh,
            "soc_pct":     soc_pct,
            **result,
        })

    total_kwh      = total_traction_kwh + total_aux_kwh - total_regen_kwh
    total_km       = total_distance_m / 1000.0
    avg_kwhpkm     = total_kwh / max(total_km, 0.01)
    final_soc_pct  = soc_pct
    remaining_kwh  = final_soc_pct / 100.0 * battery_kwh
    extra_range_km = remaining_kwh / max(avg_kwhpkm, 0.1)

    return {
        "total_kwh":         total_kwh,
        "total_km":          total_km,
        "avg_kwhpkm":        avg_kwhpkm,
        "traction_kwh":      total_traction_kwh,
        "regen_kwh":         total_regen_kwh,
        "aux_kwh":           total_aux_kwh,
        "final_soc_pct":     final_soc_pct,
        "extra_range_km":    extra_range_km,
        "segments":          segment_results,
    }


def sensitivity_analysis(base_vehicle: dict, base_params: dict) -> dict:
    """
    Compute sensitivity of energy consumption to each key parameter.
    Uses the empirical model for speed.
    """
    base_C = empirical_consumption(**base_params)
    sensitivities = {}

    deltas = {
        "speed_kmh":       5.0,
        "temperature_c":   10.0,
        "weight_tonnes":   5.0,
        "altitude_diff_m": 100.0,
    }

    for param, delta in deltas.items():
        p_up = {**base_params, param: base_params[param] + delta}
        p_dn = {**base_params, param: base_params[param] - delta}
        C_up = empirical_consumption(**p_up)
        C_dn = empirical_consumption(**p_dn)
        sensitivities[param] = {
            "delta":        delta,
            "dC_up":        C_up - base_C,
            "dC_dn":        C_dn - base_C,
            "dC_per_unit":  (C_up - C_dn) / (2 * delta),
        }

    return sensitivities
