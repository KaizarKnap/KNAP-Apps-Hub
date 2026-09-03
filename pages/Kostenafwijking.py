"""Kostenafwijking — verklaar een maand-op-maand verschil in kosten of omzet.

Losse pagina voor de KNAP APPS Streamlit-app. Geen imports uit andere pagina's,
dus hij draait ook los:  streamlit run Kostenafwijking.py
"""

import io

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Kostenafwijking", page_icon="📉", layout="wide")

WEEKDAGEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]


# ---------------------------------------------------------------- inlezen

@st.cache_data(show_spinner=False)
def lees(bestand_bytes, naam, sheet):
    if naam.lower().endswith((".csv", ".tsv")):
        sep = "\t" if naam.lower().endswith(".tsv") else None
        return pd.read_csv(io.BytesIO(bestand_bytes), sep=sep, engine="python")
    return pd.read_excel(io.BytesIO(bestand_bytes), sheet_name=sheet)


@st.cache_data(show_spinner=False)
def sheetnamen(bestand_bytes, naam):
    if naam.lower().endswith((".csv", ".tsv")):
        return []
    return pd.ExcelFile(io.BytesIO(bestand_bytes)).sheet_names


def raad(kolommen, *woorden):
    """Eerste kolom waarvan de naam een van de woorden bevat."""
    for w in woorden:
        for c in kolommen:
            if w.lower() in str(c).lower():
                return c
    return None


# ---------------------------------------------------------------- rekenen

def maandtabel(df, datum, kosten):
    """Alleen werkdagen. Weekendregels zijn nawerk en correcties; die vertekenen
    het daggemiddelde."""
    wd = df[df[datum].dt.weekday < 5].copy()
    wd["_m"] = wd[datum].dt.to_period("M")
    t = wd.groupby("_m").agg(
        kosten=(kosten, "sum"), regels=(kosten, "size"), werkdagen=(datum, "nunique")
    )
    t["per_werkdag"] = t["kosten"] / t["werkdagen"]
    t["regels_per_werkdag"] = t["regels"] / t["werkdagen"]
    t["per_regel"] = t["kosten"] / t["regels"]
    return t


def decompositie(t, a, b):
    """Splits het verschil b-a in drie effecten die exact optellen tot het totaal."""
    ra, rb = t.loc[a], t.loc[b]
    return {
        "Werkdagen": (rb.werkdagen - ra.werkdagen) * ra.per_werkdag,
        "Volume": rb.werkdagen * (rb.regels_per_werkdag - ra.regels_per_werkdag) * ra.per_regel,
        "Tarief/mix": rb.werkdagen * rb.regels_per_werkdag * (rb.per_regel - ra.per_regel),
    }


def volledigheid(df, datum, kosten, factuurdatum, maand):
    """Een lage maand is vaker onvolledig dan echt laag."""
    m = df[df[datum].dt.to_period("M") == maand]
    wd = m[m[datum].dt.weekday < 5]
    uit = {}

    kalender = pd.date_range(maand.start_time, maand.end_time, freq="B")
    uit["ontbrekend"] = sorted(set(kalender.date) - set(wd[datum].dt.date))

    if not wd.empty:
        laatste = wd[datum].max()
        peer = wd[(wd[datum].dt.weekday == laatste.weekday()) & (wd[datum] < laatste)]
        n = len(wd[wd[datum] == laatste])
        mediaan = peer.groupby(peer[datum].dt.date).size().median() if not peer.empty else None
        uit["laatste_dag"] = (laatste, n, mediaan)

    if factuurdatum:
        open_ = m[m[factuurdatum].isna()]
        uit["open_regels"] = len(open_)
        uit["open_bedrag"] = open_[kosten].sum()
        uit["maandtotaal"] = m[kosten].sum()
        uit["export_tot"] = df[factuurdatum].max()
    return uit


def per_dimensie(df, datum, kosten, t, a, b, dim):
    """Per werkdag vergelijken — op maandtotaal daalt élke categorie zodra de
    maand korter is, en dan lijkt alles een bevinding."""
    d = df[df[datum].dt.to_period("M").isin([a, b])].copy()
    d["_m"] = d[datum].dt.to_period("M").astype(str)
    p = d.pivot_table(index=dim, columns="_m", values=kosten, aggfunc="sum").fillna(0)
    ka, kb = str(a), str(b)
    if ka not in p.columns or kb not in p.columns:
        return None
    out = pd.DataFrame({
        f"{ka} p/wd": p[ka] / t.loc[a].werkdagen,
        f"{kb} p/wd": p[kb] / t.loc[b].werkdagen,
    })
    out["Verschil p/wd"] = out[f"{kb} p/wd"] - out[f"{ka} p/wd"]
    basis = out[f"{ka} p/wd"].replace(0, float("nan"))
    out["%"] = (out["Verschil p/wd"] / basis * 100).round(0)
    return out.sort_values("Verschil p/wd")


# ---------------------------------------------------------------- pagina

st.title("📉 Kostenafwijking")
st.caption(
    "Verklaart een maand-op-maand verschil. Eerst normaliseren op werkdagen, "
    "dan controleren of de maand wel af is, dan pas naar oorzaken kijken."
)

bestand = st.file_uploader("Export (xlsx of csv)", type=["xlsx", "xlsm", "csv", "tsv"])
if not bestand:
    st.info("Upload een export met minimaal een datumkolom en een bedragkolom.")
    st.stop()

data = bestand.getvalue()
sheets = sheetnamen(data, bestand.name)
sheet = st.sidebar.selectbox("Tabblad", sheets) if sheets else 0

df = lees(data, bestand.name, sheet).copy()
df.columns = [str(c).strip() for c in df.columns]
kolommen = list(df.columns)

st.sidebar.header("Kolommen")
datum = st.sidebar.selectbox(
    "Uitvoerdatum", kolommen,
    index=kolommen.index(raad(kolommen, "datum")) if raad(kolommen, "datum") else 0,
)
num = [c for c in kolommen if pd.api.types.is_numeric_dtype(df[c])]
gok_kosten = raad(num, "netto kosten", "kosten", "bedrag", "omzet")
kosten = st.sidebar.selectbox(
    "Bedrag", num, index=num.index(gok_kosten) if gok_kosten else 0,
)
gok_fact = raad(kolommen, "factuurdatum")
factuurdatum = st.sidebar.selectbox(
    "Factuurdatum (optioneel)", ["— geen —"] + kolommen,
    index=(kolommen.index(gok_fact) + 1) if gok_fact else 0,
)
factuurdatum = None if factuurdatum == "— geen —" else factuurdatum

df[datum] = pd.to_datetime(df[datum], errors="coerce")
if factuurdatum:
    df[factuurdatum] = pd.to_datetime(df[factuurdatum], errors="coerce")

zonder_datum = df[datum].isna().sum()
if zonder_datum:
    st.warning(f"{zonder_datum:,.0f} regels zonder geldige datum — buiten beschouwing gelaten.")
    df = df.dropna(subset=[datum])
if df.empty:
    st.error("Geen bruikbare regels over.")
    st.stop()

t = maandtabel(df, datum, kosten)
if len(t) < 2:
    st.error("Er zitten minder dan twee maanden in deze export.")
    st.stop()

maanden = [str(m) for m in t.index]
c1, c2 = st.columns(2)
a = pd.Period(c1.selectbox("Vergelijk met", maanden, index=len(maanden) - 2), freq="M")
b = pd.Period(c2.selectbox("Maand", maanden, index=len(maanden) - 1), freq="M")
if a == b:
    st.error("Kies twee verschillende maanden.")
    st.stop()

ra, rb = t.loc[a], t.loc[b]
verschil = rb.kosten - ra.kosten

k1, k2, k3, k4 = st.columns(4)
k1.metric(f"Totaal {b}", f"€ {rb.kosten:,.0f}", f"{verschil:,.0f} t.o.v. {a}")
k2.metric("Werkdagen", int(rb.werkdagen), int(rb.werkdagen - ra.werkdagen))
k3.metric("Per werkdag", f"€ {rb.per_werkdag:,.0f}",
          f"{rb.per_werkdag - ra.per_werkdag:,.0f}")
k4.metric("Regels per werkdag", f"{rb.regels_per_werkdag:,.0f}",
          f"{rb.regels_per_werkdag - ra.regels_per_werkdag:,.0f}")

st.subheader("Waar zit het verschil in")
dec = decompositie(t, a, b)
kolom_l, kolom_r = st.columns([2, 3])
with kolom_l:
    tabel = pd.DataFrame({"Effect": list(dec), "Bedrag": list(dec.values())})
    tabel["Aandeel"] = (tabel["Bedrag"] / verschil * 100).round(0) if verschil else 0
    st.dataframe(
        tabel.style.format({"Bedrag": "€ {:,.0f}", "Aandeel": "{:.0f}%"}),
        hide_index=True, use_container_width=True,
    )
    if abs(sum(dec.values()) - verschil) > 1:
        st.error("Decompositie sluit niet — controleer de kolomkeuze.")
    else:
        st.caption(f"Sluit exact op € {verschil:,.0f}.")
with kolom_r:
    st.bar_chart(pd.Series(dec, name="€"))

deel = dec["Werkdagen"] / verschil if verschil else 0
if abs(deel) > 0.4:
    st.success(
        f"**{deel:.0%} van het verschil is puur kalender** — {int(rb.werkdagen)} werkdagen "
        f"tegen {int(ra.werkdagen)}. Bij gelijk aantal werkdagen zou {b} op "
        f"€ {rb.per_werkdag * ra.werkdagen:,.0f} zijn uitgekomen."
    )

st.subheader(f"Is {b} wel compleet?")
v = volledigheid(df, datum, kosten, factuurdatum, b)
if v["ontbrekend"]:
    st.error(f"Ontbrekende werkdagen: {', '.join(str(d) for d in v['ontbrekend'])}")
else:
    st.write("✅ Alle werkdagen aanwezig")

if "laatste_dag" in v:
    dag, n, mediaan = v["laatste_dag"]
    label = WEEKDAGEN[dag.weekday()]
    if mediaan and n < 0.8 * mediaan:
        st.warning(
            f"⚠️ Laatste dag ({dag.date()}, {label}) heeft {n} regels tegen een mediaan van "
            f"{mediaan:.0f} op dezelfde weekdag — waarschijnlijk nog niet volledig doorgekomen."
        )
    else:
        st.write(f"✅ Laatste dag ({dag.date()}) is in lijn met andere {label}-dagen")

if factuurdatum and v.get("maandtotaal"):
    aandeel = v["open_bedrag"] / v["maandtotaal"]
    st.write(
        f"Nog niet gefactureerd: **{v['open_regels']:,} regels, € {v['open_bedrag']:,.0f}** "
        f"({aandeel:.0%} van de maand). Export loopt tot factuurdatum "
        f"**{v['export_tot'].date()}**."
    )
    if aandeel > 0.2:
        st.caption(
            "Die regels staan er al met prijs en gewicht in, dus ze ontbreken niet in het "
            "totaal — maar het bedrag kan bij nafacturatie nog licht bewegen."
        )

st.subheader("Per categorie, genormaliseerd op werkdagen")
kandidaten = [c for c in df.columns
              if df[c].dtype == object and 1 < df[c].nunique() <= 500]
if not kandidaten:
    st.info("Geen geschikte categoriekolommen gevonden.")
else:
    voorkeur = [c for c in ["Tak van dienst", "Afvalstroom", "Debiteur"] if c in kandidaten]
    gekozen = st.multiselect("Dimensies", kandidaten, default=voorkeur or kandidaten[:1])
    top = st.slider("Aantal regels per dimensie", 5, 30, 8)
    export = {}
    for dim in gekozen:
        res = per_dimensie(df, datum, kosten, t, a, b, dim)
        if res is None or res.empty:
            continue
        export[dim[:31]] = res
        st.markdown(f"**{dim}** — grootste dalers per werkdag")
        st.dataframe(
            res.head(top).style.format(
                {c: "€ {:,.0f}" for c in res.columns if c != "%"} | {"%": "{:.0f}%"}
            ),
            use_container_width=True,
        )
    if export:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            t.round(2).to_excel(writer, sheet_name="Per maand")
            pd.DataFrame({"Effect": list(dec), "Bedrag": list(dec.values())}).to_excel(
                writer, sheet_name="Decompositie", index=False)
            for naam, res in export.items():
                res.round(2).to_excel(writer, sheet_name=naam)
        st.download_button(
            "⬇️ Analyse als Excel", buffer.getvalue(),
            file_name=f"kostenafwijking_{b}_vs_{a}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with st.expander("Alle maanden"):
    st.dataframe(t.round(2), use_container_width=True)
