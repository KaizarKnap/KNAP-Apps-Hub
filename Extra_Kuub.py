# Extra_Kuub.py
import streamlit as st
import pandas as pd
import numpy as np
import io
import locale

try:
    locale.setlocale(locale.LC_TIME, "nl_NL.UTF-8")
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, "nl_NL")
    except locale.Error:
        locale.setlocale(locale.LC_TIME, "C")


def run():
    st.title("🚛 Extra Afval Dashboard")
    st.write(
        """
Analyseer automatisch extra afval per order en zie direct hoeveel **extra bakken** zijn geledigd.  
Deze versie berekent het aantal extra bakken op basis van **Extra m³ / Volume per bak**.
"""
    )

    # 🔹 GEEN CSS MEER LADEN – die gaf fouten als style.css ontbrak

    uploaded_file = st.file_uploader(
        "📂 Upload je Excel-bestand", type=["xlsx"]
    )

    if uploaded_file is None:
        st.info("Upload eerst een Excel-bestand om te beginnen.")
        return

    # --- Slimme Excel-lezer ---
    def read_excel_smart(uploaded_file):
        temp_df = pd.read_excel(uploaded_file, header=None)
        for i in range(len(temp_df)):
            row_values = temp_df.iloc[i].astype(str).tolist()
            if any(
                x in row_values
                for x in [
                    "Ophaaldatum",
                    "Locatienummer",
                    "Klantnaam",
                    "# uitgevoerd",
                    "Extra m3",
                ]
            ):
                df = pd.read_excel(uploaded_file, skiprows=i)
                return df, i
        # fallback: als er niets wordt gevonden
        df = pd.read_excel(uploaded_file)
        return df, 0

    # --- Bestand inladen met automatische detectie ---
    df, header_row = read_excel_smart(uploaded_file)
    st.success(f"✅ Bestand geladen vanaf rij {header_row + 1}")

    # Controle op verplichte kolommen
    required_cols = [
        "Locatienummer",
        "Klantnaam",
        "Ophaaldatum",
        "Volume",
        "# uitgevoerd",
        "Extra m3",
    ]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        st.error(f"❌ Ontbrekende kolommen: {', '.join(missing_cols)}")
        return

    # --- Data voorbereiden ---
    df["Ophaaldatum"] = pd.to_datetime(df["Ophaaldatum"], errors="coerce")
    df["Extra m3"] = pd.to_numeric(df["Extra m3"], errors="coerce")
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
    df["# uitgevoerd"] = pd.to_numeric(df["# uitgevoerd"], errors="coerce")

    df = df.dropna(subset=["Ophaaldatum", "Locatienummer"])

    # Extra bakken = Extra m3 / Volume per bak
    df["Extra bakken"] = df["Extra m3"] / df["Volume"]
    df["Extra bakken"] = df["Extra bakken"].fillna(0)

    st.subheader("Overzicht per order")
    st.dataframe(df, use_container_width=True)

    st.subheader("Aggregatie per locatie")
    agg = (
        df.groupby(["Locatienummer", "Klantnaam"], as_index=False)[
            ["Extra m3", "Extra bakken"]
        ]
        .sum()
    )
    st.dataframe(agg, use_container_width=True)

    # Download
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Details", index=False)
        agg.to_excel(writer, sheet_name="Per locatie", index=False)
    buffer.seek(0)

    st.download_button(
        "📥 Download resultaat (Excel)",
        buffer,
        file_name="extra_afval_resultaat.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
