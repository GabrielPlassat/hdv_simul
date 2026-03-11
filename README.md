# ⚡ BET Energy Simulator

> Simulateur de consommation énergétique pour **camions électriques (BET)**
> calibré sur l'étude terrain **Öko-Institut ELV-LIVE (2025)**.

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/VOTRE_USERNAME/bet-simulator/blob/main/notebooks/BET_simulator_colab.ipynb)
[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://votre-app.streamlit.app)

---

## 🧠 Modèles implémentés

### Modèle empirique (Öko-Institut, 2025)
Formule calibrée sur **19 eActros 300/400** en Allemagne (807 trajets) :

```
C [kWh/km] = m₁ · e^(-k₁·s) + m₂·t + m₃·w + m₄·a + m₅
```

| Variable | Description |
|----------|-------------|
| `s` | Vitesse moyenne (km/h) |
| `t` | Température extérieure (°C) |
| `w` | Poids total en charge (tonnes) |
| `a` | Différence d'altitude O→D (m) |

### Modèle physique (bilan de forces)
```
F_total = F_roulement + F_aérodynamique + F_pente + F_inertie
```
Avec récupération d'énergie au freinage (frein régénératif).

---

## 🗺️ Données géographiques (gratuites, open source)

| Source | Usage |
|--------|-------|
| **Nominatim** (OSM) | Géocodage d'adresses |
| **OSRM** | Calcul d'itinéraire routier |
| **Open-Topo-Data SRTM 30m** | Élévation du profil de route |

---

## 🚀 Démarrage rapide

### Option 1 — Streamlit Cloud (recommandé, sans installation)
1. Forkez ce dépôt sur votre compte GitHub
2. Allez sur [share.streamlit.io](https://share.streamlit.io)
3. Connectez votre GitHub et déployez `app.py`

### Option 2 — Google Colab
1. Ouvrez le badge **Open in Colab** ci-dessus
2. Exécutez les cellules une par une

### Option 3 — Local (si vous avez Python)
```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## 📂 Structure du projet

```
bet-simulator/
├── app.py                      # Application Streamlit principale
├── requirements.txt
├── README.md
├── src/
│   ├── vehicle_model.py        # Modèles empirique + physique
│   └── route_engine.py         # OSM routing + élévation
└── notebooks/
    └── BET_simulator_colab.ipynb
```

---

## 📖 Sources

- **Öko-Institut ELV-LIVE** (2025) : analyse de 19 eActros en Allemagne
- **OpenVD** : https://andresmendes.github.io/openvd/
- **Autonomie (ANL)** : https://vms.taps.anl.gov/tools/autonomie/
- Données OSM sous licence ODbL

---

## ⚠️ Limites

- Modèle calibré sur eActros 300/400 uniquement (N3, >12t)
- La différence d'altitude O→D est un proxy imparfait de la topographie réelle
- Pas de modélisation de l'état de la chaussée ni du vent
- Pour la production : utiliser des données GPS haute fréquence
