"""
BET Energy Simulator — Streamlit Application
============================================
Simulates energy consumption of Battery Electric Trucks (BET)
based on real-world data from the ELV-LIVE study (Öko-Institut, 2025)

Architecture:
  • Empirical model  : regression formula calibrated on 19 eActros trucks in Germany
  • Physics model    : longitudinal force balance (rolling + aero + grade + inertia)
  • Context data     : OSM routing (OSRM) + elevation (Open-Topo-Data / SRTM 30m)
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from src.vehicle_model import (
    empirical_consumption,
    physics_consumption_route,
    sensitivity_analysis,
    DEFAULT_VEHICLE,
    VEHICLE_PRESETS,
    EMPIRICAL_COEFFICIENTS,
)
from src.route_engine import full_route_pipeline

# ──────────────────────────────────────────────────────────────────────────────
# Page configuration
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BET Energy Simulator",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1e3a5f, #2d5a8e);
        border-radius: 12px;
        padding: 16px;
        color: white;
        text-align: center;
        margin: 4px;
    }
    .metric-value { font-size: 2em; font-weight: bold; }
    .metric-label { font-size: 0.85em; opacity: 0.85; }
    .model-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.8em;
        font-weight: bold;
    }
    .badge-empirical { background: #e8f4f8; color: #1565c0; }
    .badge-physics   { background: #fce4ec; color: #c62828; }
    .stAlert { border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# Session state initialisation
# ──────────────────────────────────────────────────────────────────────────────
if "route_data" not in st.session_state:
    st.session_state["route_data"] = None
if "physics_result" not in st.session_state:
    st.session_state["physics_result"] = None

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/b/b0/Openstreetmap_logo.svg", width=60)
    st.title("⚡ BET Simulator")
    st.caption("Basé sur l'étude Öko-Institut / ELV-LIVE (2025)")
    st.divider()

    # ── Vehicle preset ──────────────────────────────────────────────────────
    st.subheader("🚛 Véhicule")
    preset_name = st.selectbox("Modèle préconfiguré", list(VEHICLE_PRESETS.keys()))
    vehicle = dict(VEHICLE_PRESETS[preset_name])

    with st.expander("⚙️ Paramètres avancés du véhicule", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            vehicle["payload_t"] = st.number_input(
                "Charge utile (t)", 0.0, 30.0,
                float(vehicle.get("payload_t", 0.0)), 0.5)
            vehicle["battery_capacity_kwh"] = st.number_input(
                "Capacité batterie (kWh)", 100, 800,
                int(vehicle["battery_capacity_kwh"]), 10)
            vehicle["drag_coeff_Cd"] = st.slider(
                "Cx (Cd)", 0.3, 0.8, float(vehicle["drag_coeff_Cd"]), 0.01)
        with col2:
            vehicle["frontal_area_m2"] = st.number_input(
                "Surface frontale (m²)", 5.0, 15.0,
                float(vehicle["frontal_area_m2"]), 0.1)
            vehicle["rolling_resist_Cr"] = st.slider(
                "Résistance roulement Cr", 0.003, 0.015,
                float(vehicle["rolling_resist_Cr"]), 0.001, format="%.3f")
            vehicle["regen_efficiency"] = st.slider(
                "Efficacité récupération", 0.40, 0.90,
                float(vehicle["regen_efficiency"]), 0.01)

    # ── Mission parameters ──────────────────────────────────────────────────
    st.subheader("🌡️ Conditions de mission")
    temperature = st.slider("Température ambiante (°C)", -20, 40, 12, 1)
    avg_speed   = st.slider("Vitesse moyenne (km/h)", 10, 90, 50, 5)
    has_tcu     = st.toggle("Groupe froid / TCU (+0.092 kWh/km)", value=False)

    st.divider()

    # ── Route ───────────────────────────────────────────────────────────────
    st.subheader("🗺️ Itinéraire (OpenStreetMap)")
    origin_addr = st.text_input("Départ", "Munich, Allemagne")
    destin_addr = st.text_input("Destination", "Nuremberg, Allemagne")

    route_btn = st.button("🔍 Calculer l'itinéraire + élévation", type="primary", use_container_width=True)

    if route_btn:
        with st.spinner("🌐 Appel OSM / OSRM / SRTM…"):
            result = full_route_pipeline(
                origin_address      = origin_addr,
                destination_address = destin_addr,
                avg_speed_kmh       = avg_speed,
                n_segments          = 60,
            )

        if result is None or "error" in result:
            st.error(result.get("error", "Erreur inconnue") if result else "Erreur API")
        else:
            st.session_state["route_data"] = result
            # Run physics model immediately
            physics_res = physics_consumption_route(
                route_segments = result["segments"],
                vehicle        = vehicle,
                temperature_c  = temperature,
                avg_speed_kmh  = avg_speed,
                has_tcu        = has_tcu,
            )
            st.session_state["physics_result"] = physics_res
            st.success(f"✅ {result['distance_m']/1000:.1f} km – {result['duration_s']/3600:.1f} h")

    st.divider()
    st.caption("📖 Sources: Öko-Institut ELV-LIVE 2025 | OSRM | Open-Topo-Data SRTM30m | Nominatim")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN PANEL
# ══════════════════════════════════════════════════════════════════════════════
st.title("⚡ Simulateur de consommation — Camion électrique BET")
st.markdown("""
Modèle hybride calibré sur **19 camions Daimler eActros** en Allemagne (2023-2024).
Combine un modèle **empirique** (régression OLS) et un modèle **physique** (bilan de forces).
""")

# ── TABS ─────────────────────────────────────────────────────────────────────
tab_route, tab_empirique, tab_physique, tab_sensi, tab_methode = st.tabs([
    "🗺️ Itinéraire & Élévation",
    "📊 Modèle Empirique",
    "⚙️ Modèle Physique",
    "📐 Sensibilité",
    "📖 Méthodologie",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Route & elevation
# ══════════════════════════════════════════════════════════════════════════════
with tab_route:
    route_data = st.session_state.get("route_data")

    if route_data is None:
        st.info("👈 Renseignez un itinéraire dans la barre latérale et cliquez sur **Calculer**.")
        # Show demo map
        st.markdown("### Exemple de tracé (démo statique)")
        demo_coords = [
            [11.5820, 48.1351],  # Munich
            [11.6000, 48.3000],
            [11.0000, 49.0000],
            [11.0748, 49.4521],  # Nuremberg
        ]
        fig_map = go.Figure(go.Scattermapbox(
            lat=[c[1] for c in demo_coords],
            lon=[c[0] for c in demo_coords],
            mode="lines+markers",
            marker=dict(size=10, color=["green", "blue", "blue", "red"]),
            line=dict(width=3, color="royalblue"),
            name="Tracé exemple",
        ))
        fig_map.update_layout(
            mapbox=dict(style="open-street-map", zoom=6, center=dict(lat=48.7, lon=11.3)),
            height=400, margin=dict(l=0, r=0, t=0, b=0),
        )
        st.plotly_chart(fig_map, use_container_width=True)
    else:
        dist_km  = route_data["distance_m"] / 1000.0
        dur_h    = route_data["duration_s"] / 3600.0
        alt_diff = route_data["alt_diff_m"]
        ascent   = route_data["total_ascent_m"]
        descent  = route_data["total_descent_m"]

        # KPI row
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("📏 Distance", f"{dist_km:.1f} km")
        k2.metric("⏱️ Durée estimée", f"{dur_h:.1f} h")
        k3.metric("⛰️ Dénivelé total", f"+{ascent:.0f} m / -{descent:.0f} m")
        k4.metric("↕️ Diff. altitude", f"{alt_diff:+.0f} m")

        st.divider()

        col_map, col_elev = st.columns([3, 2])

        with col_map:
            st.markdown("**Carte de l'itinéraire (OpenStreetMap)**")
            coords = route_data["coordinates"]
            lats = [c[1] for c in coords]
            lons = [c[0] for c in coords]

            fig_map = go.Figure()
            fig_map.add_trace(go.Scattermapbox(
                lat=lats, lon=lons,
                mode="lines",
                line=dict(width=4, color="royalblue"),
                name="Itinéraire",
            ))
            # Start / End markers
            fig_map.add_trace(go.Scattermapbox(
                lat=[lats[0], lats[-1]],
                lon=[lons[0], lons[-1]],
                mode="markers+text",
                marker=dict(size=14, color=["#2ecc71", "#e74c3c"]),
                text=["Départ", "Arrivée"],
                textposition="top right",
                name="Points clés",
            ))
            fig_map.update_layout(
                mapbox=dict(
                    style="open-street-map",
                    zoom=7,
                    center=dict(lat=np.mean(lats), lon=np.mean(lons)),
                ),
                height=420, margin=dict(l=0, r=0, t=0, b=0),
                legend=dict(orientation="h", y=0),
            )
            st.plotly_chart(fig_map, use_container_width=True)

        with col_elev:
            st.markdown("**Profil altimétrique (SRTM 30m)**")
            elevations = route_data["elevations"]
            n_elev = len(elevations)
            dist_arr = np.linspace(0, dist_km, n_elev)

            fig_elev = go.Figure()
            fig_elev.add_trace(go.Scatter(
                x=dist_arr, y=elevations,
                mode="lines",
                fill="tozeroy",
                fillcolor="rgba(52, 152, 219, 0.15)",
                line=dict(color="steelblue", width=2),
                name="Altitude",
            ))
            fig_elev.update_layout(
                xaxis_title="Distance (km)",
                yaxis_title="Altitude (m)",
                height=200,
                margin=dict(l=0, r=0, t=10, b=0),
                showlegend=False,
            )
            st.plotly_chart(fig_elev, use_container_width=True)

            # Slope histogram
            st.markdown("**Distribution des pentes**")
            segs   = route_data["segments"]
            slopes = [s["slope_deg"] for s in segs]
            fig_hist = px.histogram(
                x=slopes, nbins=30,
                color_discrete_sequence=["#3498db"],
                labels={"x": "Pente (°)", "y": "Fréquence"},
            )
            fig_hist.update_layout(height=180, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
            st.plotly_chart(fig_hist, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Empirical model
# ══════════════════════════════════════════════════════════════════════════════
with tab_empirique:
    st.markdown("""
    ### Modèle empirique ELV-LIVE (Öko-Institut, 2025)
    Formule calibrée sur 19 camions Daimler eActros (807 trajets) :

    $$C = m_1 \\cdot e^{-k_1 \\cdot s} + m_2 \\cdot t + m_3 \\cdot w + m_4 \\cdot a + m_5$$

    | Variable | Description | Plage mesurée |
    |----------|-------------|---------------|
    | $s$ | Vitesse moyenne (km/h) | 0.02 – 90 |
    | $t$ | Température extérieure (°C) | -7 – 36 |
    | $w$ | Poids total en charge (tonnes) | 11 – 40 |
    | $a$ | Différence d'altitude O→D (m) | -785 – 786 |
    """)

    st.divider()

    # Current point estimate
    gross_weight_emp = vehicle["curb_weight_t"] + vehicle["payload_t"]
    route_data = st.session_state.get("route_data")
    alt_diff_emp = route_data["alt_diff_m"] if route_data else 0.0

    C_emp = empirical_consumption(
        speed_kmh     = avg_speed,
        temperature_c = temperature,
        weight_tonnes = gross_weight_emp,
        altitude_diff_m = alt_diff_emp,
        has_tcu       = has_tcu,
    )

    # If route available, compute total
    dist_km_emp = route_data["distance_m"] / 1000.0 if route_data else None
    total_kwh_emp = C_emp * dist_km_emp if dist_km_emp else None
    soc_end_emp   = None
    if total_kwh_emp:
        remaining = vehicle["battery_capacity_kwh"] - total_kwh_emp
        soc_end_emp = max(0, remaining / vehicle["battery_capacity_kwh"] * 100)
        range_remain = remaining / C_emp if remaining > 0 else 0

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔋 Consommation", f"{C_emp:.3f} kWh/km",
                delta=f"TCU: +{EMPIRICAL_COEFFICIENTS['tcu_penalty']:.3f}" if has_tcu else None)
    col2.metric("📏 Distance route", f"{dist_km_emp:.1f} km" if dist_km_emp else "N/A")
    col3.metric("⚡ Énergie totale", f"{total_kwh_emp:.1f} kWh" if total_kwh_emp else "—")
    col4.metric("🔋 SoC final estimé", f"{soc_end_emp:.0f} %" if soc_end_emp is not None else "—",
                delta=f"Autonomie restante ~{range_remain:.0f} km" if soc_end_emp and soc_end_emp > 0 else None)

    st.divider()

    # Curves
    col_spd, col_wgt = st.columns(2)

    with col_spd:
        st.markdown("**Consommation vs Vitesse**")
        speeds = np.linspace(5, 90, 100)
        C_spds = [empirical_consumption(s, temperature, gross_weight_emp, alt_diff_emp, has_tcu) for s in speeds]
        fig_spd = go.Figure()
        fig_spd.add_trace(go.Scatter(x=speeds, y=C_spds, mode="lines",
                                     line=dict(color="#1565c0", width=2.5), name="C(s)"))
        fig_spd.add_vline(x=avg_speed, line_dash="dash", line_color="red",
                          annotation_text=f"v={avg_speed} km/h")
        fig_spd.update_layout(xaxis_title="Vitesse (km/h)", yaxis_title="C (kWh/km)",
                              height=300, margin=dict(t=10, b=0))
        st.plotly_chart(fig_spd, use_container_width=True)

    with col_wgt:
        st.markdown("**Consommation vs Poids total**")
        weights = np.linspace(10, 44, 100)
        C_wgts = [empirical_consumption(avg_speed, temperature, w, alt_diff_emp, has_tcu) for w in weights]
        fig_wgt = go.Figure()
        fig_wgt.add_trace(go.Scatter(x=weights, y=C_wgts, mode="lines",
                                     line=dict(color="#2e7d32", width=2.5), name="C(w)"))
        fig_wgt.add_vline(x=gross_weight_emp, line_dash="dash", line_color="red",
                          annotation_text=f"w={gross_weight_emp:.1f} t")
        fig_wgt.update_layout(xaxis_title="Poids (t)", yaxis_title="C (kWh/km)",
                              height=300, margin=dict(t=10, b=0))
        st.plotly_chart(fig_wgt, use_container_width=True)

    col_temp, col_alt = st.columns(2)

    with col_temp:
        st.markdown("**Consommation vs Température**")
        temps = np.linspace(-20, 40, 100)
        C_temps = [empirical_consumption(avg_speed, t, gross_weight_emp, alt_diff_emp, has_tcu) for t in temps]
        fig_temp = go.Figure()
        fig_temp.add_trace(go.Scatter(x=temps, y=C_temps, mode="lines",
                                      line=dict(color="#e65100", width=2.5)))
        fig_temp.add_vline(x=temperature, line_dash="dash", line_color="red",
                           annotation_text=f"T={temperature} °C")
        fig_temp.update_layout(xaxis_title="T (°C)", yaxis_title="C (kWh/km)",
                               height=300, margin=dict(t=10, b=0))
        st.plotly_chart(fig_temp, use_container_width=True)

    with col_alt:
        st.markdown("**Consommation vs Dénivelé**")
        alts = np.linspace(-800, 800, 100)
        C_alts = [empirical_consumption(avg_speed, temperature, gross_weight_emp, a, has_tcu) for a in alts]
        fig_alt = go.Figure()
        fig_alt.add_trace(go.Scatter(x=alts, y=C_alts, mode="lines",
                                     line=dict(color="#6a1b9a", width=2.5)))
        fig_alt.add_vline(x=alt_diff_emp, line_dash="dash", line_color="red",
                          annotation_text=f"Δh={alt_diff_emp:+.0f} m")
        fig_alt.update_layout(xaxis_title="Diff. altitude (m)", yaxis_title="C (kWh/km)",
                              height=300, margin=dict(t=10, b=0))
        st.plotly_chart(fig_alt, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Physics model
# ══════════════════════════════════════════════════════════════════════════════
with tab_physique:
    physics_res = st.session_state.get("physics_result")

    if physics_res is None and st.session_state.get("route_data") is not None:
        # Auto-run with current params
        physics_res = physics_consumption_route(
            route_segments = st.session_state["route_data"]["segments"],
            vehicle        = vehicle,
            temperature_c  = temperature,
            avg_speed_kmh  = avg_speed,
            has_tcu        = has_tcu,
        )
        st.session_state["physics_result"] = physics_res

    st.markdown("""
    ### Modèle physique — Bilan de forces longitudinal

    $$F_{total} = \\underbrace{C_r \\cdot m \\cdot g \\cdot \\cos\\theta}_{Roulement}
    + \\underbrace{\\frac{1}{2} \\rho C_d A v^2}_{Aéro}
    + \\underbrace{m \\cdot g \\cdot \\sin\\theta}_{Pente}$$

    Avec récupération d'énergie au freinage : $E_{regen} = \\eta_{regen} \\cdot |F_{frein}| \\cdot d$
    """)

    if physics_res is None:
        st.info("👈 Calculez d'abord un itinéraire pour activer le modèle physique.")

        # Show a simple demo run without route
        st.markdown("#### Simulation sur pente variable (démo)")
        demo_segs = []
        for i in range(60):
            slope = 3.0 * np.sin(i / 10.0)
            demo_segs.append({"distance_m": 1000, "slope_deg": slope, "speed_kmh": avg_speed})
        demo_result = physics_consumption_route(
            route_segments = demo_segs,
            vehicle        = vehicle,
            temperature_c  = temperature,
            avg_speed_kmh  = avg_speed,
            has_tcu        = has_tcu,
        )
        physics_res = demo_result
        st.info("ℹ️ Simulation sur itinéraire fictif (pente sinusoïdale) — ajoutez un itinéraire OSM pour la réalité.")
    
    # Metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("⚡ Consommation moy.", f"{physics_res['avg_kwhpkm']:.3f} kWh/km")
    c2.metric("🔋 Énergie totale", f"{physics_res['total_kwh']:.1f} kWh")
    c3.metric("♻️ Énergie récupérée", f"{physics_res['regen_kwh']:.1f} kWh",
              delta=f"{physics_res['regen_kwh']/max(physics_res['traction_kwh'],0.01)*100:.0f}% récupéré")
    c4.metric("🔌 SoC final", f"{physics_res['final_soc_pct']:.0f} %")
    c5.metric("🛣️ Autonomie restante", f"~{physics_res['extra_range_km']:.0f} km")

    st.divider()

    # Energy waterfall
    labels = ["Traction", "Auxiliaires", "Récupération", "Batterie nette"]
    values = [
        physics_res["traction_kwh"],
        physics_res["aux_kwh"],
        -physics_res["regen_kwh"],
        physics_res["total_kwh"],
    ]
    fig_wf = go.Figure(go.Waterfall(
        name="Bilan énergétique",
        orientation="v",
        measure=["relative", "relative", "relative", "total"],
        x=labels,
        y=values,
        connector=dict(line=dict(color="rgb(63, 63, 63)")),
        decreasing=dict(marker_color="#2ecc71"),
        increasing=dict(marker_color="#e74c3c"),
        totals=dict(marker_color="#3498db"),
    ))
    fig_wf.update_layout(
        title="Bilan énergétique du trajet (kWh)",
        height=350, margin=dict(t=40, b=0),
    )
    st.plotly_chart(fig_wf, use_container_width=True)

    # Segment-level charts
    segs_df = pd.DataFrame(physics_res["segments"])

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Consommation nette par segment**")
        fig_seg = make_subplots(specs=[[{"secondary_y": True}]])
        fig_seg.add_trace(go.Bar(
            x=segs_df["cum_km"], y=segs_df["net_kwh"],
            name="Énergie nette (kWh)",
            marker_color=np.where(segs_df["net_kwh"] > 0, "#e74c3c", "#2ecc71"),
        ))
        fig_seg.add_trace(go.Scatter(
            x=segs_df["cum_km"], y=segs_df["soc_pct"],
            mode="lines", name="SoC (%)",
            line=dict(color="steelblue", width=2),
        ), secondary_y=True)
        fig_seg.update_layout(height=320, margin=dict(t=10, b=0))
        fig_seg.update_xaxes(title_text="Distance (km)")
        fig_seg.update_yaxes(title_text="kWh / segment", secondary_y=False)
        fig_seg.update_yaxes(title_text="SoC (%)", secondary_y=True, range=[0, 105])
        st.plotly_chart(fig_seg, use_container_width=True)

    with col_b:
        st.markdown("**Décomposition des forces motrices**")
        fig_forces = go.Figure()
        fig_forces.add_trace(go.Scatter(x=segs_df["cum_km"], y=segs_df["F_rolling_N"]/1000,
                                         fill="tozeroy", name="Roulement (kN)",
                                         line=dict(color="#f39c12")))
        fig_forces.add_trace(go.Scatter(x=segs_df["cum_km"], y=segs_df["F_aero_N"]/1000,
                                         fill="tozeroy", name="Aérodynamique (kN)",
                                         line=dict(color="#3498db")))
        fig_forces.add_trace(go.Scatter(x=segs_df["cum_km"], y=segs_df["F_grade_N"]/1000,
                                         name="Pente (kN)", line=dict(color="#e74c3c")))
        fig_forces.update_layout(height=320, margin=dict(t=10, b=0),
                                  xaxis_title="Distance (km)", yaxis_title="Force (kN)")
        st.plotly_chart(fig_forces, use_container_width=True)

    # Vehicle params recap
    with st.expander("📋 Paramètres véhicule utilisés"):
        veh_df = pd.DataFrame({
            "Paramètre": [
                "Poids total (t)", "Charge utile (t)", "Batterie (kWh)",
                "Cx", "Surface frontale (m²)", "Cr", "η moteur", "η récupération"
            ],
            "Valeur": [
                f"{vehicle['curb_weight_t'] + vehicle['payload_t']:.1f}",
                f"{vehicle['payload_t']:.1f}",
                f"{vehicle['battery_capacity_kwh']:.0f}",
                f"{vehicle['drag_coeff_Cd']:.2f}",
                f"{vehicle['frontal_area_m2']:.1f}",
                f"{vehicle['rolling_resist_Cr']:.3f}",
                f"{vehicle['motor_efficiency']:.2f}",
                f"{vehicle['regen_efficiency']:.2f}",
            ],
        })
        st.dataframe(veh_df, hide_index=True, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Sensitivity analysis
# ══════════════════════════════════════════════════════════════════════════════
with tab_sensi:
    st.markdown("""
    ### Analyse de sensibilité
    Impact de chaque paramètre sur la consommation (**modèle empirique ELV-LIVE**).
    """)

    gross_weight_sa = vehicle["curb_weight_t"] + vehicle["payload_t"]
    alt_diff_sa = route_data["alt_diff_m"] if route_data else 0.0

    base_params = dict(
        speed_kmh       = avg_speed,
        temperature_c   = temperature,
        weight_tonnes   = gross_weight_sa,
        altitude_diff_m = alt_diff_sa,
        has_tcu         = has_tcu,
    )
    C_base = empirical_consumption(**base_params)
    sensitivities = sensitivity_analysis(vehicle, base_params)

    st.metric("📍 Consommation de référence", f"{C_base:.3f} kWh/km")
    st.divider()

    # Tornado chart
    params_labels = {
        "speed_kmh":       f"Vitesse ±5 km/h (base: {avg_speed} km/h)",
        "temperature_c":   f"Température ±10°C (base: {temperature} °C)",
        "weight_tonnes":   f"Poids ±5 t (base: {gross_weight_sa:.1f} t)",
        "altitude_diff_m": f"Dénivelé ±100 m (base: {alt_diff_sa:+.0f} m)",
    }

    tornado_data = []
    for k, label in params_labels.items():
        s = sensitivities[k]
        tornado_data.append({
            "Paramètre": label,
            "Impact +": s["dC_up"],
            "Impact -": s["dC_dn"],
            "|Impact max|": max(abs(s["dC_up"]), abs(s["dC_dn"])),
        })

    df_tornado = pd.DataFrame(tornado_data).sort_values("|Impact max|")

    fig_tornado = go.Figure()
    for _, row in df_tornado.iterrows():
        fig_tornado.add_trace(go.Bar(
            name=f"Δ+ ({row['Impact +']:+.3f})",
            y=[row["Paramètre"]],
            x=[row["Impact +"]],
            orientation="h",
            marker_color="#e74c3c" if row["Impact +"] > 0 else "#2ecc71",
            showlegend=False,
        ))
        fig_tornado.add_trace(go.Bar(
            name=f"Δ- ({row['Impact -']:+.3f})",
            y=[row["Paramètre"]],
            x=[row["Impact -"]],
            orientation="h",
            marker_color="#2ecc71" if row["Impact -"] < 0 else "#e74c3c",
            showlegend=False,
        ))

    fig_tornado.add_vline(x=0, line_width=1.5, line_color="black")
    fig_tornado.update_layout(
        title="Diagramme Tornade — Variation de consommation (kWh/km)",
        barmode="overlay",
        height=350,
        xaxis_title="ΔC (kWh/km)",
        margin=dict(t=40, b=0),
    )
    st.plotly_chart(fig_tornado, use_container_width=True)

    # Real-world comparison table
    st.markdown("#### Comparaison avec les résultats réels de l'étude")
    comp_data = {
        "Condition": [
            "Plat, 44 km/h, 20t, 12°C",
            "Montagneux (+200m), 44 km/h, 20t, 12°C",
            "Hiver (-5°C), 44 km/h, 20t",
            "Surchargé (35t), 44 km/h, 12°C",
            "Vitesse autoroute (80 km/h), 20t, 12°C",
            "Urbain lent (25 km/h), 20t, 12°C",
        ],
        "C simulée (kWh/km)": [
            empirical_consumption(44, 12, 20, 0),
            empirical_consumption(44, 12, 20, 200),
            empirical_consumption(44, -5, 20, 0),
            empirical_consumption(44, 12, 35, 0),
            empirical_consumption(80, 12, 20, 0),
            empirical_consumption(25, 12, 20, 0),
        ],
        "Ref. étude (kWh/km)": [
            "≈ 1.0 – 1.3",
            "≈ 1.2 – 1.5",
            "≈ 1.3 – 1.6",
            "≈ 1.1 – 1.4",
            "≈ 0.9 – 1.2",
            "≈ 1.5 – 3.0",
        ],
    }
    df_comp = pd.DataFrame(comp_data)
    df_comp["C simulée (kWh/km)"] = df_comp["C simulée (kWh/km)"].round(3)
    st.dataframe(df_comp, hide_index=True, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Methodology
# ══════════════════════════════════════════════════════════════════════════════
with tab_methode:
    st.markdown("""
    ## 📖 Base scientifique & Architecture du modèle

    ### 1. Source principale
    > **"Real-world data analysis of energy consumption, activity and charging patterns
    > of battery electric trucks operating in Germany"**
    > Öko-Institut e.V. / ELV-LIVE (Berlin, juillet 2025)
    > Auteurs : Le Corguillé, Hacker, Göckeler, Mottschall, Dolinga

    - **Véhicules** : 19 camions Daimler eActros 300/400 (catégorie N3, >12t)
    - **Données** : 807 trajets sur 16 semaines (sept. 2023 – janv. 2025)
    - **Régions** : Allemagne (plat, semi-montagneux, montagneux)

    ---

    ### 2. Modèle empirique (Équation 2 de l'étude)

    $$C = m_1 \\cdot e^{-k_1 \\cdot s} + m_2 \\cdot t + m_3 \\cdot w + m_4 \\cdot a + m_5$$

    | Coeff. | Valeur | Interprétation |
    |--------|--------|----------------|
    | $k_1$ | 0.17 | Constante de décroissance vitesse |
    | $m_1$ | 0.80 | Amplitude terme vitesse |
    | $m_2$ | -0.013 | -0.13 kWh/km per +10°C |
    | $m_3$ | 0.018 | +0.18 kWh/km per +10t |
    | $m_4$ | 0.0011 | ~+0.11 kWh/km per +100m |
    | $m_5$ | 0.30 | Constante d'intercept |
    | TCU | +0.092 | Groupe froid actif |

    ---

    ### 3. Modèle physique (bilan de forces)

    ```
    ┌────────────────────────────────────────────────────────────┐
    │  F_total = F_rolling + F_aero + F_grade + F_inertia        │
    │                                                            │
    │  F_rolling = Cr · m · g · cos(θ)                          │
    │  F_aero    = ½ · ρ · Cd · A · v²                          │
    │  F_grade   = m · g · sin(θ)                               │
    │  F_inertia = m · a                                        │
    │                                                            │
    │  E_bat = (F·v / η_drivetrain - E_regen + P_aux) · dt      │
    └────────────────────────────────────────────────────────────┘
    ```

    ---

    ### 4. Données géographiques

    | Source | API | Usage |
    |--------|-----|-------|
    | **Nominatim** (OSM) | `nominatim.openstreetmap.org` | Géocodage adresses |
    | **OSRM** | `router.project-osrm.org` | Calcul d'itinéraire routier |
    | **Open-Topo-Data** | `api.opentopodata.org/v1/srtm30m` | Élévation SRTM 30m |

    ---

    ### 5. Références complémentaires
    - OpenVD (véhicule dynamique) : https://andresmendes.github.io/openvd/
    - Autonomie (ANL) : https://vms.taps.anl.gov/tools/autonomie/
    - ICCT BET China study (Mao et al. 2023)
    - Cenex BET UK study (Cenex 2024)
    """)

    st.info("""
    **Limites du modèle** : calibré uniquement sur eActros 300/400, 
    non représentatif de tous les BET. 
    La différence d'altitude entre O et D est un proxy imparfait de la topographie réelle.
    Pour la production, utiliser des données GPS haute fréquence.
    """)
