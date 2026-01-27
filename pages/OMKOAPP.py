# streamlit_omwissel_app.py
# ------------------------------------------------------------
# Simpele omwisselkosten checker
# - Vaste kolommen
# - Negeert aantallen
# - Vaste omwisselkosten
# - Toont en exporteert ALLEEN Omwisselkosten = JA
# ------------------------------------------------------------

import io
import re
import pandas as pd
import streamlit as st


# =============================
# CONFIG
# =============================
COL_OMSCHRIJVING = "Productomschrijving"
COL_DATUM = "Uitvoerdatum"
COL_LOCATIE = "Locatienummer"
COL_AFVALSTROOM = "Afvalstroom"
COL_EVENT = "Omwissel"      # als deze niet bestaat → fallback

DEFAULT_OMWISSELKOSTEN = 45.0


# =============================
# HULPFUNCTIES
# =============================
def classify_order(text):
    if pd.isna(text):
        return None
    t = str(text).lower()
    if "afvoeren" in t:
        return "AFVOEREN"
    if "plaatsen" in t:
        return "PLAATSEN"
    return None


def extract_volume_liters(text):
    """Zoekt 240L, 1100 L, 3m3, 2.5 m3, 2,5 m3"""
    if pd.isna(text):
        return None

    t = str(text).lower().replace(",", ".")

    m_l = re.search(r"(\d+(?:\.\d+)?)\s*l", t)
    if m_l:
        return float(m_l.group(1))

    m_m3 = re.search(r"(\d+(?:\.\d+)?)\s*m\s*(?:3|³)", t)
    if m_m3:
        return float(m_m3.group(1)) * 1000

    return None


def build_event_key(df):
    if COL_EVENT in df.columns:
        return df[COL_EVENT].astype("string")

    return (
        df[COL_LOCATIE].astype("string").fillna("") + "|"
        + df[COL_AFVALSTROOM].astype("string").fillna("") + "|"
        + df[COL_DATUM].astype("string").fillna("")
    )


def bepaal_omwissel(df):
    df = df.copy()

    df["OrderType"] = df[COL_OMSCHRIJVING].apply(classify_order)
    df["Volume_L"] = df[COL_OMSCHRIJVING].apply(extract_volume_liters)
    df["EventKey"] = build_event_key(df)

    df = df[df["OrderType"].isin(["AFVOEREN", "PLAATSEN"])]

    df["_dt"] = pd.to_datetime(df[COL_DATUM], errors="coerce")
    df["_idx"] = df.index
    df = df.sort_values(["EventKey", "_dt", "_idx"])

    resultaten = []

    for event, g in df.groupby("EventKey"):
        afv = g[g["OrderType"] == "AFVOEREN"]
        pl = g[g["OrderType"] == "PLAATSEN"]

        if afv.empty or pl.empty:
            continue

        oud = afv.iloc[0]
        nieuw = pl.iloc[0]

        if pd.isna(oud["Volume_L"]) or pd.isna(nieuw["Volume_L"]):
            continue

        if nieuw["Volume_L"] < oud["Volume_L"]:
            resultaten.append({
                "EventKey": event,
                COL_DATUM: nieuw[COL_DATUM],
                COL_LOCATIE: nieuw[COL_LOCATIE],
                COL_AFVALSTROOM: nieuw[COL_AFVALSTROOM],
                "Oud_volume_L": oud["Volume_L"],
                "Nieuw_volume_L": nieuw["Volume_L"],
                "Omwisselkosten": "JA",
                "Afvoeren_omschrijving": oud[COL_OMSCHRIJVING],
                "Plaatsen_omschrijving": nieuw[COL_OMSCHRIJVING],
            })

    return pd.DataFrame(resultaten)


def to_excel(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Omwisselkosten_JA")
    buffer.seek(0)
    return buffer


# =============================
# STREAMLIT UI
# =============================
st.set_page_config(layout="wide")
st.title("Omwisselkosten checker")
st.caption("Toont en exporteert alleen orders waar omwisselkosten moeten worden doorbelast")

omwisselkosten = st.number_input(
    "Vaste omwisselkosten (€)",
    min_value=0.0,
    value=DEFAULT_OMWISSELKOSTEN,
    step=1.0
)

file = st.file_uploader("Upload Excel", type=["xlsx"])

if file:
    df_raw = pd.read_excel(file)

    verplichte_kolommen = [
        COL_OMSCHRIJVING,
        COL_DATUM,
        COL_LOCATIE,
        COL_AFVALSTROOM,
    ]

    ontbrekend = [c for c in verplichte_kolommen if c not in df_raw.columns]
    if ontbrekend:
        st.error(f"Ontbrekende kolommen: {', '.join(ontbrekend)}")
        st.stop()

    df_ja = bepaal_omwissel(df_raw)
    df_ja["Omwisselkosten_EUR"] = omwisselkosten

    st.subheader("Orders met omwisselkosten = JA")
    st.write(f"Aantal: **{len(df_ja)}**")
    st.dataframe(df_ja, use_container_width=True)

    st.download_button(
        "Download Excel (alleen JA)",
        data=to_excel(df_ja),
        file_name="omwisselkosten_JA.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
