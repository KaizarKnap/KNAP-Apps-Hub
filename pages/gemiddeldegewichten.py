import streamlit as st
import pandas as pd
from io import BytesIO
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import norm, gaussian_kde

# -------------------------------------------------------------
# CACHE DATA LOADER
# -------------------------------------------------------------
@st.cache_data
def load_file(uploaded):
    if uploaded.name.endswith("csv"):
        return pd.read_csv(uploaded, dtype=str)
    else:
        return pd.read_excel(uploaded, engine="openpyxl", dtype=str)


st.title("Gewichtsconsistentie per Bak (Leverancier → Afvalstroom → Volume)")

uploaded = st.file_uploader("Upload dataset", type=["xlsx", "xls", "csv"])


# -------------------------------------------------------------
# 1) VOLUME CLEANING FUNCTIE
# -------------------------------------------------------------
def clean_volume(v):
    if pd.isna(v):
        return "Onbekend"

    v = str(v).strip().lower().replace(" ", "").replace(",", ".")
    v = v.replace("m³", "m3")

    if "m3" in v:
        return v

    if "liter" in v:
        v = v.replace("liter", "l")
    if "ltr" in v:
        v = v.replace("ltr", "l")
    if v.endswith("l"):
        return v.upper()

    if "mini" in v:
        return "Mini"
    if "pers" in v:
        return "Perscontainer"
    if "wagen" in v:
        return "Containerwagen"

    return v


# -------------------------------------------------------------
# 2) START APP
# -------------------------------------------------------------
if uploaded:

    # ---------------- DATA INLADEN ----------------
    try:
        df = load_file(uploaded)
    except Exception as e:
        st.error("Kon bestand niet inladen: " + str(e))
        st.stop()

    required = ["Leverancier", "Afvalstroom", "Volume", "Gewicht", "# uitgevoerd"]
    missing = [c for c in required if c not in df.columns]

    if missing:
        st.error(f"Deze kolommen ontbreken: {missing}")
        st.stop()

    # ------------- VOLUME OPSCHONEN ----------------
    df["Volume"] = df["Volume"].apply(clean_volume)

    volume_order = [
        "Mini", "120L", "140L", "180L", "240L", "360L", "500L", "660L", "770L",
        "1000L", "1100L", "0.24m3", "0.36m3", "0.5m3", "1m3", "1.5m3", "2m3",
        "2.5m3", "3m3", "5m3", "7m3", "10m3", "15m3", "20m3", "25m3", "40m3",
        "Perscontainer", "Containerwagen"
    ]
    df["Volume"] = pd.Categorical(df["Volume"], categories=volume_order, ordered=True)

    # ------------- GEWICHT PER BAK -----------------
    df["# uitgevoerd"] = pd.to_numeric(df["# uitgevoerd"], errors="coerce")
    df = df[df["# uitgevoerd"] > 0]

    df["Gewicht"] = pd.to_numeric(df["Gewicht"], errors="coerce")

    df["Gewicht_per_bak"] = (df["Gewicht"] / df["# uitgevoerd"]).round(1)

    df_clean = df.dropna(subset=["Leverancier", "Afvalstroom", "Volume", "Gewicht_per_bak"])


    # -------------------------------------------------------------
    # 3) NORMAALVERDELING + KDE + HISTOGRAM
    # -------------------------------------------------------------
    st.subheader("Gewichtsverdeling per bak (filters)")

    leveranciers = sorted(df_clean["Leverancier"].unique())
    afvalstromen = sorted(df_clean["Afvalstroom"].unique())
    volumes = [v for v in df_clean["Volume"].unique().tolist() if pd.notna(v)]

    sel_lev = st.selectbox("Leverancier", ["Geen"] + leveranciers)
    sel_afr = st.selectbox("Afvalstroom", ["Geen"] + afvalstromen)
    sel_vol = st.selectbox("Volume", ["Geen"] + volumes)

    df_filt = df_clean.copy()
    if sel_lev != "Geen":
        df_filt = df_filt[df_filt["Leverancier"] == sel_lev]
    if sel_afr != "Geen":
        df_filt = df_filt[df_filt["Afvalstroom"] == sel_afr]
    if sel_vol != "Geen":
        df_filt = df_filt[df_filt["Volume"] == sel_vol]

    if len(df_filt) > 5:

        plt.style.use("default")
        fig, ax = plt.subplots(figsize=(14, 8))
        fig.patch.set_facecolor("#0d1117")
        ax.set_facecolor("#0d1117")

        ax.tick_params(colors="white")
        for spine in ax.spines.values():
            spine.set_color("white")

        ax.grid(color="white", alpha=0.15)

        data = df_filt["Gewicht_per_bak"].astype(float)
        low, high = np.percentile(data, [5, 95])
        data_trim = data[(data >= low) & (data <= high)]

        counts, bins, _ = ax.hist(
            data_trim,
            bins=15,
            alpha=0.65,
            color="#4c72b0",
            edgecolor="#2e3b55",
            label="Aantal bakken"
        )

        bin_width = bins[1] - bins[0]
        n = len(data_trim)

        kde = gaussian_kde(data_trim)
        x = np.linspace(low, high, 200)
        kde_counts = kde(x) * n * bin_width
        ax.plot(x, kde_counts, linestyle="--", linewidth=2.5,
                color="#e69f00", label="KDE (aantal bakken)")

        mu, sigma = norm.fit(data_trim)
        norm_counts = norm.pdf(x, mu, sigma) * n * bin_width
        ax.plot(x, norm_counts, linewidth=3,
                color="#d62728", alpha=0.9,
                label="Normaalverdeling")

        ax.set_xlabel("Gewicht per bak (kg)", color="white")
        ax.set_ylabel("Aantal bakken", color="white")
        ax.set_title("Gewichtsverdeling", color="white")

        legend = ax.legend(facecolor="#1a1a1a", edgecolor="white")
        for text in legend.get_texts():
            text.set_color("white")

        st.markdown(
            f"**Gemiddelde (μ):** {mu:.1f} kg — "
            f"**σ:** {sigma:.1f} — "
            f"**Aantal bakken:** {n}"
        )

        st.pyplot(fig)

    else:
        st.info("Niet genoeg data voor een betrouwbare verdeling.")


    # -------------------------------------------------------------
    # 4) EXACTE GEWICHTEN
    # -------------------------------------------------------------
    #st.subheader("Exacte gewichten (≥ 2x)")

    exact = (
        df_clean
        .groupby(["Leverancier", "Afvalstroom", "Volume", "Gewicht_per_bak"])
        .size()
        .reset_index(name="Aantal")
    )
    exact = exact[exact["Aantal"] >= 2]

    #st.dataframe(exact)


    # -------------------------------------------------------------
    # 5) SAMENVATTING
    # -------------------------------------------------------------
    st.subheader("Samenvatting gewichtspatronen")

    summary_list = []
    for (lev, afr, vol), subset in exact.groupby(["Leverancier", "Afvalstroom", "Volume"]):

        unieke = subset["Gewicht_per_bak"].nunique()
        top = subset.loc[subset["Aantal"].idxmax()]

        if unieke == 1 and top["Aantal"] > 1:
            status = "CONSISTENT"
        elif unieke > 1:
            status = "INCONSISTENT"
        else:
            status = "GEEN PATROON"

        summary_list.append({
            "Leverancier": lev,
            "Afvalstroom": afr,
            "Volume": vol,
            "Aantal unieke gewichten": unieke,
            "Meest voorkomend gewicht": top["Gewicht_per_bak"],
            "Aantal": top["Aantal"],
            "Status": status
        })

    summary = pd.DataFrame(summary_list)
    st.dataframe(summary)


    # -------------------------------------------------------------
    # 6) GEAVANCEERDE ANALYSE
    # -------------------------------------------------------------
    st.header("📊 Geavanceerde Analyse")

    # Outlier detectie
    st.subheader("Outlier detectie (gewicht ver boven of onder gemiddeld)")
    df_clean["zscore"] = (
        df_clean["Gewicht_per_bak"] - df_clean["Gewicht_per_bak"].mean()
    ) / df_clean["Gewicht_per_bak"].std()

    outliers = df_clean[abs(df_clean["zscore"]) > 2.5]
    st.write(f"**Aantal outliers:** {len(outliers)}")
    st.dataframe(outliers)


    # -------------------------------------------------------------
    # 7) TRENDS MET EIGEN FILTERS (Ophaaldatum)
    # -------------------------------------------------------------
    st.header("📈 Gemiddeld gewicht per maand (met eigen filters)")

    if "Ophaaldatum" in df_clean.columns:

        df_trend = df_clean.copy()

        t_lev = sorted(df_trend["Leverancier"].dropna().unique())
        t_afr = sorted(df_trend["Afvalstroom"].dropna().unique())
        t_vol = [v for v in df_trend["Volume"].unique().tolist() if pd.notna(v)]

        col1, col2, col3 = st.columns(3)
        with col1:
            slev = st.selectbox("Trend: Leverancier", ["Alle"] + t_lev)
        with col2:
            safr = st.selectbox("Trend: Afvalstroom", ["Alle"] + t_afr)
        with col3:
            svol = st.selectbox("Trend: Volume", ["Alle"] + t_vol)

        if slev != "Alle":
            df_trend = df_trend[df_trend["Leverancier"] == slev]
        if safr != "Alle":
            df_trend = df_trend[df_trend["Afvalstroom"] == safr]
        if svol != "Alle":
            df_trend = df_trend[df_trend["Volume"] == svol]

        if df_trend.empty:
            st.info("Geen data voor deze selectie.")
        else:
            df_trend["Ophaaldatum"] = pd.to_datetime(df_trend["Ophaaldatum"], errors="coerce")
            df_trend = df_trend.dropna(subset=["Ophaaldatum"])

            if df_trend.empty:
                st.info("Geen geldige Ophaaldatum waarden.")
            else:
                trend = (
                    df_trend.groupby(df_trend["Ophaaldatum"].dt.to_period("M"))["Gewicht_per_bak"]
                    .mean().reset_index()
                )
                trend["Ophaaldatum"] = trend["Ophaaldatum"].astype(str)

                if len(trend) < 2:
                    st.info("Niet genoeg punten voor trendlijn.")
                else:
                    st.line_chart(trend.set_index("Ophaaldatum"))

    else:
        st.info("Geen kolom 'Ophaaldatum' gevonden.")

    # -------------------------------------------------------------
    # 8) EXCEL EXPORT
    # -------------------------------------------------------------
    st.header("📥 Excel Export")

    def to_excel(df_overview, df_rows, df_exact, df_zscore):
        output = BytesIO()

        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            # Sheets
            df_overview.to_excel(writer, index=False, sheet_name="Overzicht")
            df_rows.to_excel(writer, index=False, sheet_name="Regels")
            df_exact.to_excel(writer, index=False, sheet_name="Exacte patronen")
            df_zscore.to_excel(writer, index=False, sheet_name="Zscore Analyse")

            workbook = writer.book

            header_format = workbook.add_format({
                "bold": True,
                "bg_color": "#DCE6F1",
                "border": 1
            })
            cell_format = workbook.add_format({"border": 1})

            def format_sheet(df, sheetname):
                ws = writer.sheets[sheetname]
                for col_idx, col in enumerate(df.columns):
                    max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                    ws.set_column(col_idx, col_idx, max_len, cell_format)
                    ws.write(0, col_idx, col, header_format)

            # Format all sheets
            format_sheet(df_overview, "Overzicht")
            format_sheet(df_rows, "Regels")
            format_sheet(df_exact, "Exacte patronen")
            format_sheet(df_zscore, "Zscore Analyse")

        output.seek(0)
        return output.getvalue()

    # Als er geen exacte patronen zijn → lege placeholder
    exact_export = exact if not exact.empty else pd.DataFrame(
        {"Info": ["Geen exacte patronen gevonden"]}
    )

    # Z-score data export
    zscore_export = df_clean.copy()[[
        col for col in df_clean.columns  # neem alle kolommen incl. 'zscore'
    ]]

    excel_bytes = to_excel(summary, df_clean, exact_export, zscore_export)

    st.download_button(
        "Download Excel",
        data=excel_bytes,
        file_name="gewicht_per_bak_analyse.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

#     # -------------------------------------------------------------
#     # 9) OFFLINE AI-ASSISTENT (OLLAMA) – KLEINE PROMPT, KLEINE KOLMENSSET
#     # -------------------------------------------------------------
#     st.header("🤖 Offline AI Data Assistent (Ollama)")

#     import ollama

#     st.markdown("""
#     Deze AI draait **volledig offline** via Ollama en kijkt alleen naar de belangrijkste kolommen:

#     - Leverancier  
#     - Afvalstroom  
#     - Volume  
#     - Gewicht_per_bak  
#     - Ophaaldatum (indien aanwezig)

#     Zo blijft de analyse snel en stabiel, ook bij ~55.000 regels.
#     """)

#     question = st.text_area("Stel een vraag over je dataset:")

#     if st.button("Vraag AI"):

#         if not question.strip():
#             st.warning("Typ eerst een vraag.")
#         else:
#             # Alleen de relevante kolommen gebruiken
#             basis_cols = ["Leverancier", "Afvalstroom", "Volume", "Gewicht_per_bak"]
#             cols = [c for c in basis_cols if c in df_clean.columns]

#             if "Ophaaldatum" in df_clean.columns:
#                 cols.append("Ophaaldatum")

#             df_view = df_clean[cols].copy()

#             # Kleine sample (eerste 5 regels)
#             sample_markdown = df_view.head(5).to_markdown(index=False)

#             # Eenvoudige statistieken over Gewicht_per_bak
#             if "Gewicht_per_bak" in df_view.columns:
#                 stats_markdown = df_view["Gewicht_per_bak"].describe().to_markdown()
#             else:
#                 stats_markdown = "Kolom 'Gewicht_per_bak' niet gevonden."

#             # Gemiddeld gewicht per leverancier (top 10)
#             if "Leverancier" in df_view.columns and "Gewicht_per_bak" in df_view.columns:
#                 lev_stats = (
#                     df_view.groupby("Leverancier")["Gewicht_per_bak"]
#                     .agg(["mean", "std", "count"])
#                     .reset_index()
#                     .sort_values("count", ascending=False)
#                     .head(10)
#                 )
#                 lev_stats["mean"] = lev_stats["mean"].round(1)
#                 lev_stats["std"] = lev_stats["std"].round(1)
#                 lev_markdown = lev_stats.to_markdown(index=False)
#             else:
#                 lev_markdown = "Geen leverancierstatistieken beschikbaar."

#             # Gemiddeld gewicht per afvalstroom (top 10)
#             if "Afvalstroom" in df_view.columns and "Gewicht_per_bak" in df_view.columns:
#                 afr_stats = (
#                     df_view.groupby("Afvalstroom")["Gewicht_per_bak"]
#                     .agg(["mean", "std", "count"])
#                     .reset_index()
#                     .sort_values("count", ascending=False)
#                     .head(10)
#                 )
#                 afr_stats["mean"] = afr_stats["mean"].round(1)
#                 afr_stats["std"] = afr_stats["std"].round(1)
#                 afr_markdown = afr_stats.to_markdown(index=False)
#             else:
#                 afr_markdown = "Geen afvalstroomstatistieken beschikbaar."

#             system_prompt = f"""
# Je bent een data-analist gespecialiseerd in afvalstromen en containergewichten.

# Je hebt de volgende informatie over de dataset:

# 1. Kolommen die je mag gebruiken:
#    {cols}

# 2. Voorbeeld (eerste 5 regels):
# {sample_markdown}

# 3. Statistieken van 'Gewicht_per_bak':
# {stats_markdown}

# 4. Gemiddeld gewicht per leverancier (top 10, met std en aantallen):
# {lev_markdown}

# 5. Gemiddeld gewicht per afvalstroom (top 10, met std en aantallen):
# {afr_markdown}

# Let op:
# - Gebruik alleen deze informatie.
# - Geef antwoorden in het Nederlands.
# - Leg duidelijk uit welke patronen je ziet, welke leveranciers/afvalstromen/volumes opvallend zijn,
#   en welke combinaties consistent of inconsistent lijken.
# - Als je iets niet zeker weet, geef dat expliciet aan in plaats van te gokken.
# """

#             with st.spinner("AI is bezig met analyseren..."):
#                 try:
#                     response = ollama.chat(
#                         model="phi3",   # gebruik het lichte, snelle model
#                         stream=False,
#                         messages=[
#                             {"role": "system", "content": system_prompt},
#                             {"role": "user", "content": question}
#                         ]
#                     )
#                     st.markdown("### 💡 AI antwoord:")
#                     st.write(response["message"]["content"])

#                 except Exception as e:
#                     st.error(f"AI foutmelding: {e}")
#                     st.info("Controleer of Ollama draait en of het model 'phi3' is gedownload (ollama pull phi3).")


