import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
from io import BytesIO
import re

DB_PATH = "mop_app.db"

MONTHS_NL = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "september": 9, "oktober": 10, "november": 11, "december": 12
}
MONTH_KEYS = list(MONTHS_NL.keys())

# --- MOP types (fixed set, per Excel) ---
MOP_FIXED = [
    "Karton Nederland & België (gemiddelde)",
    "Karton Nederland & België – laag",
    "Karton Nederland & België – hoog",
    "Bont Nederland & België (gemiddelde)",
    "Bont Nederland & België – laag",
    "Bont Nederland & België – hoog",
    "Karton Verre Oosten (gemiddelde)",
    "Karton Verre Oosten – laag",
    "Karton Verre Oosten – hoog",
    "Karton Verre Oosten & Nederland (gemiddelde)",
]

GROUPS = {
    "Karton NL/BE": {
        "low": "Karton Nederland & België – laag",
        "high": "Karton Nederland & België – hoog",
        "avg": "Karton Nederland & België (gemiddelde)"
    },
    "Bont NL/BE": {
        "low": "Bont Nederland & België – laag",
        "high": "Bont Nederland & België – hoog",
        "avg": "Bont Nederland & België (gemiddelde)"
    },
    "Karton Verre Oosten": {
        "low": "Karton Verre Oosten – laag",
        "high": "Karton Verre Oosten – hoog",
        "avg": "Karton Verre Oosten (gemiddelde)"
    }
}
COMBINED_AVG = {
    "left_avg": "Karton Nederland & België (gemiddelde)",
    "right_avg": "Karton Verre Oosten (gemiddelde)",
    "target": "Karton Verre Oosten & Nederland (gemiddelde)"
}

# ---------------- Core helpers ----------------
def now_ts() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")

def first_day_of_month(year: int, month: int) -> str:
    return date(year, month, 1).isoformat()

def ym_str(d: str) -> str:
    return d[:7]

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def qdf(conn, q, params=()):
    return pd.read_sql_query(q, conn, params=params)

def exec_sql(conn, q, params=()):
    cur = conn.cursor()
    cur.execute(q, params)
    conn.commit()
    return cur

def export_excel(df: pd.DataFrame, sheet_name: str = "Ton opbrengst") -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()

def period_picker(label: str, key_prefix: str) -> str:
    c1, c2 = st.columns([1, 1])
    today = date.today()
    with c1:
        year = st.number_input(
            f"{label} - Jaar",
            min_value=2020,
            max_value=2035,
            value=int(st.session_state.get(f"{key_prefix}_year", today.year)),
            step=1,
            key=f"{key_prefix}_year",
        )
    with c2:
        default_idx = int(st.session_state.get(f"{key_prefix}_month_idx", max(0, today.month - 1)))
        month = st.selectbox(
            f"{label} - Maand",
            MONTH_KEYS,
            index=default_idx,
            key=f"{key_prefix}_month",
        )
        st.session_state[f"{key_prefix}_month_idx"] = MONTH_KEYS.index(month)
    period = first_day_of_month(int(year), MONTHS_NL[month])
    st.caption(f"Gekozen periode: {ym_str(period)}")
    return period

# ---------------- DB init ----------------
def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS mop_type (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS mop_rate (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mop_type_id INTEGER NOT NULL,
        period TEXT NOT NULL,
        rate_eur_per_ton REAL NOT NULL,
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL,
        comment TEXT,
        FOREIGN KEY(mop_type_id) REFERENCES mop_type(id) ON DELETE RESTRICT,
        UNIQUE(mop_type_id, period)
    );

    CREATE TABLE IF NOT EXISTS customer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        debtor_no TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS customer_agreement (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        mop_type_id INTEGER NOT NULL,
        discount_eur_per_ton REAL NOT NULL,
        valid_from TEXT NOT NULL,
        valid_to TEXT,
        comment TEXT,
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL,
        FOREIGN KEY(customer_id) REFERENCES customer(id) ON DELETE CASCADE,
        FOREIGN KEY(mop_type_id) REFERENCES mop_type(id) ON DELETE RESTRICT
    );

    CREATE TABLE IF NOT EXISTS price_run (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT NOT NULL,
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL,
        note TEXT
    );

    CREATE TABLE IF NOT EXISTS price_run_line (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        customer_id INTEGER NOT NULL,
        mop_type_id INTEGER NOT NULL,
        mop_rate_used REAL NOT NULL,
        discount_used REAL NOT NULL,
        ton_yield REAL NOT NULL,
        comment TEXT,
        FOREIGN KEY(run_id) REFERENCES price_run(id) ON DELETE CASCADE,
        FOREIGN KEY(customer_id) REFERENCES customer(id) ON DELETE RESTRICT,
        FOREIGN KEY(mop_type_id) REFERENCES mop_type(id) ON DELETE RESTRICT,
        UNIQUE(run_id, customer_id)
    );
    """)
    conn.commit()
    conn.close()

def ensure_fixed_mop_types(conn, user: str):
    for name in MOP_FIXED:
        try:
            exec_sql(conn, "INSERT INTO mop_type (name, active, created_at, created_by) VALUES (?, 1, ?, ?)",
                     (name, now_ts(), user))
        except sqlite3.IntegrityError:
            pass

# ---------------- Data access ----------------
def get_mop_types(conn) -> pd.DataFrame:
    return qdf(conn, "SELECT id, name, active FROM mop_type ORDER BY name")

def get_customers(conn) -> pd.DataFrame:
    return qdf(conn, "SELECT id, debtor_no, name, active FROM customer ORDER BY debtor_no")

def upsert_mop_rate(conn, mop_type_id: int, period: str, rate: float, user: str, comment: str | None = None):
    exists = qdf(conn, "SELECT id FROM mop_rate WHERE mop_type_id=? AND period=?", (int(mop_type_id), period))
    if len(exists) == 0:
        exec_sql(conn, """
            INSERT INTO mop_rate (mop_type_id, period, rate_eur_per_ton, created_at, created_by, comment)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (int(mop_type_id), period, float(rate), now_ts(), user, comment))
    else:
        exec_sql(conn, """
            UPDATE mop_rate
            SET rate_eur_per_ton=?, comment=?
            WHERE mop_type_id=? AND period=?
        """, (float(rate), comment, int(mop_type_id), period))

def get_rates_map(conn, period: str):
    df = qdf(conn, """
        SELECT mt.name AS mop_type, mr.mop_type_id, mr.rate_eur_per_ton, mr.comment
        FROM mop_rate mr
        JOIN mop_type mt ON mt.id = mr.mop_type_id
        WHERE mr.period = ?
    """, (period,))
    rate_by_name = {str(r["mop_type"]): float(r["rate_eur_per_ton"]) for _, r in df.iterrows()}
    id_by_name = {str(r["mop_type"]): int(r["mop_type_id"]) for _, r in df.iterrows()}
    return rate_by_name, id_by_name

def get_mop_name_to_id(conn):
    df = get_mop_types(conn)
    return {str(r["name"]): int(r["id"]) for _, r in df.iterrows()}

def get_current_agreement(conn, customer_id: int):
    # "actueel" = meest recente valid_from (zoals Excel praktijk)
    df = qdf(conn, """
        SELECT ca.id AS agreement_id, ca.mop_type_id, mt.name AS mop_type, ca.discount_eur_per_ton AS afslag,
               ca.valid_from, ca.valid_to, ca.comment
        FROM customer_agreement ca
        JOIN mop_type mt ON mt.id = ca.mop_type_id
        WHERE ca.customer_id = ?
        ORDER BY ca.valid_from DESC, ca.created_at DESC
        LIMIT 1
    """, (int(customer_id),))
    if len(df) == 0:
        return None
    r = df.iloc[0].to_dict()
    return r

def update_customer(conn, customer_id: int, debtor_no: str, name: str, active: int):
    exec_sql(conn, """
        UPDATE customer
        SET debtor_no=?, name=?, active=?
        WHERE id=?
    """, (debtor_no, name, int(active), int(customer_id)))

def deactivate_customer(conn, customer_id: int):
    exec_sql(conn, "UPDATE customer SET active=0 WHERE id=?", (int(customer_id),))

def delete_customer_hard(conn, customer_id: int):
    a = qdf(conn, "SELECT COUNT(1) AS n FROM customer_agreement WHERE customer_id=?", (int(customer_id),))
    r = qdf(conn, "SELECT COUNT(1) AS n FROM price_run_line WHERE customer_id=?", (int(customer_id),))
    if int(a.iloc[0]["n"]) > 0 or int(r.iloc[0]["n"]) > 0:
        raise ValueError("Hard verwijderen kan niet: er zijn afspraken en/of runs gekoppeld. Gebruik deactiveren.")
    exec_sql(conn, "DELETE FROM customer WHERE id=?", (int(customer_id),))

def upsert_current_agreement(conn, customer_id: int, mop_type_id: int, afslag: float, valid_from: str, valid_to: str | None, comment: str | None, user: str, existing_agreement_id: int | None):
    if existing_agreement_id is None:
        exec_sql(conn, """
            INSERT INTO customer_agreement
            (customer_id, mop_type_id, discount_eur_per_ton, valid_from, valid_to, comment, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (int(customer_id), int(mop_type_id), float(afslag), valid_from, valid_to, comment, now_ts(), user))
    else:
        exec_sql(conn, """
            UPDATE customer_agreement
            SET mop_type_id=?, discount_eur_per_ton=?, valid_from=?, valid_to=?, comment=?
            WHERE id=?
        """, (int(mop_type_id), float(afslag), valid_from, valid_to, comment, int(existing_agreement_id)))

def delete_agreement(conn, agreement_id: int):
    exec_sql(conn, "DELETE FROM customer_agreement WHERE id=?", (int(agreement_id),))

def find_agreement_for_period(conn, customer_id: int, period: str):
    df = qdf(conn, """
        SELECT ca.*, mt.name AS mop_type_name
        FROM customer_agreement ca
        JOIN mop_type mt ON mt.id = ca.mop_type_id
        WHERE ca.customer_id = ?
          AND ca.valid_from <= ?
          AND (ca.valid_to IS NULL OR ca.valid_to >= ?)
        ORDER BY ca.valid_from DESC, ca.created_at DESC
        LIMIT 1
    """, (int(customer_id), period, period))
    if len(df) == 0:
        return None
    return df.iloc[0].to_dict()

def create_run(conn, period: str, user: str, note: str | None, lines_df: pd.DataFrame) -> int:
    cur = exec_sql(conn, """
        INSERT INTO price_run (period, created_at, created_by, note)
        VALUES (?, ?, ?, ?)
    """, (period, now_ts(), user, note))
    run_id = int(cur.lastrowid)
    for _, r in lines_df.iterrows():
        exec_sql(conn, """
            INSERT INTO price_run_line (run_id, customer_id, mop_type_id, mop_rate_used, discount_used, ton_yield, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            int(r["customer_id"]),
            int(r["mop_type_id"]),
            float(r["mop_rate_used"]),
            float(r["discount_used"]),
            float(r["ton_yield"]),
            str(r.get("comment") or "").strip() or None
        ))
    return run_id

# ---------------- Import helpers ----------------
def normalize_cols(cols):
    out = []
    for c in cols:
        c = str(c).strip()
        c = re.sub(r"\s+", " ", c)
        out.append(c)
    return out

def base_month_col(colname: str):
    c = str(colname).strip().lower()
    c = c.split(".")[0]
    c = c.replace(" ", "")
    return c

def safe_float(x):
    if pd.isna(x):
        return None
    try:
        return float(x)
    except Exception:
        return None
    
def safe_int(x):
    if x is None:
        return None
    if isinstance(x, str):
        x = x.strip()
        if x == "":
            return None
    try:
        # catches pandas NaN
        if pd.isna(x):
            return None
    except Exception:
        pass
    try:
        return int(x)
    except Exception:
        return None
    
def mop_import_preview(excel_file, sheet_name="MOP"):
    df = pd.read_excel(excel_file, sheet_name=sheet_name)
    df.columns = normalize_cols(df.columns)
    first_col = df.columns[0]
    df = df.rename(columns={first_col: "Periode"})
    df = df[df["Periode"].notna()].copy()
    month_cols = [c for c in df.columns if base_month_col(c) in MONTHS_NL.keys()]
    df = df[["Periode"] + month_cols].copy()
    return df, month_cols

# ---------------- UI ----------------
st.set_page_config(page_title="MOP Pricing", layout="wide")
init_db()

st.title("MOP Pricing App")
st.caption("Overzichtelijk beheer van MOP-maandprijzen, klantafspraken (afslag), runs en Excel-export.")

with st.sidebar:
    st.subheader("Gebruiker")
    user = st.text_input("Naam (audit trail)", value="onbekend")

conn = get_conn()
ensure_fixed_mop_types(conn, user=user)
mop_name_to_id = get_mop_name_to_id(conn)
mop_names_active = [n for n in MOP_FIXED if n in mop_name_to_id]  # fixed order

tab_import, tab_mop, tab_customers, tab_run, tab_history = st.tabs(
    ["Import", "MOP", "Klanten", "Run & export", "Historie"]
)

# ---------------- TAB: Import ----------------
with tab_import:
    st.subheader("Import uit Excel")
    st.write("Gebruik dit om de bestaande Excel te importeren. Dubbele maandkolommen (April, April.1, …) kun je hier netjes normaliseren.")
    up = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])

    if up is not None:
        try:
            xls = pd.ExcelFile(up)
            st.write("Sheets:", ", ".join(xls.sheet_names))
        except Exception as e:
            st.error(f"Kan Excel niet lezen: {e}")
            xls = None

        if xls is not None and "MOP" in xls.sheet_names:
            st.markdown("### 1) MOP maandprijzen importeren")
            df_mop, month_cols = mop_import_preview(up, sheet_name="MOP")

            bases = {}
            for c in month_cols:
                bases.setdefault(base_month_col(c), []).append(c)

            dup = {b: cols for b, cols in bases.items() if len(cols) > 1}
            if dup:
                st.warning("Dubbele maandkolommen gedetecteerd. Kies per maand welke kolom gebruikt moet worden.")
            else:
                st.info("Geen dubbele maandkolommen gevonden.")

            imp_year = st.number_input("Import-jaar (voor maandkolommen)", min_value=2020, max_value=2035, value=date.today().year, step=1, key="imp_year")

            colpick = {}
            cols = st.columns(3)
            i = 0
            for b in [m for m in MONTH_KEYS if m in bases]:
                with cols[i % 3]:
                    colpick[b] = st.selectbox(f"Kolom voor {b.capitalize()}", bases[b], index=0, key=f"pick_{b}")
                i += 1

            # Build normalized rows, but only for known fixed mop types
            rows = []
            for _, r in df_mop.iterrows():
                mop_name_raw = str(r["Periode"]).strip()
                mop_name = mop_name_raw.replace("–", "–").strip()
                mop_name = mop_name.replace("  ", " ").strip()
                mop_name = mop_name.rstrip()
                # normalize trailing spaces and common variations
                mop_name = mop_name.replace("– laag ", "– laag").replace("– hoog ", "– hoog")
                mop_name = mop_name.replace("(gemiddelde) ", "(gemiddelde)")
                if mop_name not in mop_name_to_id:
                    # skip unknown types; user stated no new types
                    continue
                for b, month_num in MONTHS_NL.items():
                    if b not in colpick:
                        continue
                    val = safe_float(r.get(colpick[b]))
                    if val is None:
                        continue
                    per = first_day_of_month(int(imp_year), int(month_num))
                    rows.append({
                        "MOP type": mop_name,
                        "Periode": ym_str(per),
                        "Tarief (EUR/ton)": val,
                        "Bron kolom": colpick[b]
                    })
            norm = pd.DataFrame(rows)
            st.dataframe(norm.head(50), use_container_width=True, hide_index=True)

            if st.button("Importeer MOP prijzen", type="primary"):
                created_rates = 0
                for _, rr in norm.iterrows():
                    mop_id = mop_name_to_id.get(rr["MOP type"])
                    per = str(rr["Periode"]) + "-01"
                    before = qdf(conn, "SELECT id FROM mop_rate WHERE mop_type_id=? AND period=?", (mop_id, per))
                    upsert_mop_rate(conn, mop_id, per, float(rr["Tarief (EUR/ton)"]), user, f"Import: {rr['Bron kolom']}")
                    after = qdf(conn, "SELECT id FROM mop_rate WHERE mop_type_id=? AND period=?", (mop_id, per))
                    if len(before) == 0 and len(after) == 1:
                        created_rates += 1
                st.success(f"Klaar. Nieuwe maandtarieven toegevoegd: {created_rates}. (Bestaande zijn geüpdatet)")

        st.divider()

        st.markdown("### 2) Klanten importeren")
        calc_sheet = None
        if xls is not None:
            for s in xls.sheet_names:
                if s.strip().lower().startswith("berekening ton opbrengst"):
                    calc_sheet = s
                    break

        if xls is None or calc_sheet is None:
            st.info("Geen sheet 'Berekening Ton opbrengst' gevonden.")
        else:
            df_calc = pd.read_excel(up, sheet_name=calc_sheet)
            df_calc.columns = normalize_cols(df_calc.columns)

            colmap = {}
            for c in df_calc.columns:
                lc = c.lower()
                if lc == "debiteur":
                    colmap[c] = "Locatienummer"
                elif lc == "bedrijfsnaam":
                    colmap[c] = "Klantnaam"
                elif lc == "mop tarief":
                    colmap[c] = "MOP Tarief"
                elif lc == "afslag":
                    colmap[c] = "Afslag"
            df_calc = df_calc.rename(columns=colmap)

            required = ["Locatienummer", "Klantnaam", "MOP Tarief", "Afslag"]
            missing = [c for c in required if c not in df_calc.columns]
            if missing:
                st.error(f"Ontbrekende kolommen: {', '.join(missing)}")
            else:
                df_calc = df_calc[["Locatienummer", "Klantnaam", "MOP Tarief", "Afslag"]].copy()
                df_calc = df_calc[df_calc["Locatienummer"].notna() & df_calc["Klantnaam"].notna()].copy()

                if st.button("Importeer klanten (locatienummer + naam)", type="secondary"):
                    inserted = 0
                    for _, r in df_calc.iterrows():
                        try:
                            exec_sql(conn, """
                                INSERT INTO customer (debtor_no, name, active, created_at, created_by)
                                VALUES (?, ?, 1, ?, ?)
                            """, (str(r["Locatienummer"]).strip(), str(r["Klantnaam"]).strip(), now_ts(), user))
                            inserted += 1
                        except sqlite3.IntegrityError:
                            pass
                    st.success(f"Klanten geïmporteerd: {inserted} (bestaande overgeslagen).")

                st.markdown("#### Afspraken importeren via mapping naar MOP-type")
                st.caption("Excel heeft alleen een MOP tarief (getal). Koppel dit éénmalig aan het juiste MOP-type voor een gekozen maand.")
                map_period = period_picker("Mapping-periode", "map")

                rates = qdf(conn, """
                    SELECT mr.mop_type_id, mr.rate_eur_per_ton, mt.name AS mop_type
                    FROM mop_rate mr
                    JOIN mop_type mt ON mt.id = mr.mop_type_id
                    WHERE mr.period = ?
                """, (map_period,))

                if len(rates) == 0:
                    st.warning("Geen MOP-tarieven in database voor deze mapping-periode. Importeer eerst de MOP sheet.")
                else:
                    rate_to_types = {}
                    for _, rr in rates.iterrows():
                        rate_to_types.setdefault(round(float(rr["rate_eur_per_ton"]), 2), []).append(str(rr["mop_type"]))

                    customers = get_customers(conn)
                    debtor_to_id = {str(r["debtor_no"]): int(r["id"]) for _, r in customers.iterrows()}

                    rows = []
                    for _, r in df_calc.iterrows():
                        deb = str(r["Locatienummer"]).strip()
                        cid = debtor_to_id.get(deb)
                        if cid is None:
                            continue
                        mop_rate = safe_float(r["MOP Tarief"])
                        disc = safe_float(r["Afslag"])
                        if mop_rate is None or disc is None:
                            continue
                        candidates = rate_to_types.get(round(mop_rate, 2), [])
                        suggestion = candidates[0] if len(candidates) >= 1 else ""
                        rows.append({
                            "customer_id": cid,
                            "Locatienummer": deb,
                            "Klantnaam": str(r["Klantnaam"]).strip(),
                            "MOP Tarief (Excel)": mop_rate,
                            "Afslag (EUR/ton)": disc,
                            "MOP type": suggestion,
                            "Geldig vanaf": pd.to_datetime(map_period).date(),
                            "Geldig tot": None,
                            "Opmerking": "Geïmporteerd uit Excel"
                        })

                    map_df = pd.DataFrame(rows)
                    if len(map_df) == 0:
                        st.info("Geen regels om te mappen.")
                    else:
                        edited = st.data_editor(
                            map_df,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "customer_id": st.column_config.NumberColumn("customer_id", disabled=True),
                                "MOP Tarief (Excel)": st.column_config.NumberColumn("MOP Tarief (Excel)", disabled=True),
                                "MOP type": st.column_config.SelectboxColumn("MOP type", options=[""] + mop_names_active),
                                "Geldig vanaf": st.column_config.DateColumn("Geldig vanaf"),
                                "Geldig tot": st.column_config.DateColumn("Geldig tot"),
                                "Afslag (EUR/ton)": st.column_config.NumberColumn("Afslag (EUR/ton)", step=1.0),
                            }
                        )

                        if st.button("Sla afspraken op", type="primary"):
                            inserted = 0
                            skipped = 0
                            for _, rr in edited.iterrows():
                                mop_name = str(rr["MOP type"]).strip()
                                if not mop_name:
                                    skipped += 1
                                    continue
                                mop_id = mop_name_to_id.get(mop_name)
                                if mop_id is None:
                                    skipped += 1
                                    continue
                                vf = rr["Geldig vanaf"]
                                vt = rr["Geldig tot"]
                                exec_sql(conn, """
                                    INSERT INTO customer_agreement
                                    (customer_id, mop_type_id, discount_eur_per_ton, valid_from, valid_to, comment, created_at, created_by)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    int(rr["customer_id"]),
                                    int(mop_id),
                                    float(rr["Afslag (EUR/ton)"]),
                                    vf.isoformat() if hasattr(vf, "isoformat") else str(vf),
                                    vt.isoformat() if (vt is not None and hasattr(vt, "isoformat")) else None,
                                    str(rr.get("Opmerking") or "").strip() or None,
                                    now_ts(), user
                                ))
                                inserted += 1
                            st.success(f"Afspraken opgeslagen: {inserted}. Overgeslagen: {skipped}.")

# ---------------- TAB: MOP ----------------
with tab_mop:
    st.subheader("MOP maandprijzen")
    st.caption("Je vult alleen **laag** en **hoog** in. De app berekent automatisch de gemiddelden zoals in je Excel.")
    period_mop = period_picker("MOP-periode", "mop")

    # Pull existing rates for period
    rate_by_name, _ = get_rates_map(conn, period_mop)

    # Build editor: only low/high editable
    rows = []
    for group_name, g in GROUPS.items():
        low_name = g["low"]
        high_name = g["high"]
        rows.append({"Categorie": group_name, "Type": "laag", "MOP type": low_name, "Tarief (EUR/ton)": rate_by_name.get(low_name, 0.0)})
        rows.append({"Categorie": group_name, "Type": "hoog", "MOP type": high_name, "Tarief (EUR/ton)": rate_by_name.get(high_name, 0.0)})

    edit_df = pd.DataFrame(rows)

    edited = st.data_editor(
        edit_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Categorie": st.column_config.TextColumn("Categorie", disabled=True),
            "Type": st.column_config.TextColumn("Type", disabled=True),
            "MOP type": st.column_config.TextColumn("MOP type", disabled=True),
            "Tarief (EUR/ton)": st.column_config.NumberColumn("Tarief (EUR/ton)", step=0.5),
        }
    )

    def compute_all_averages(edited_df: pd.DataFrame):
        # build lookup from edited low/high
        rates = {str(r["MOP type"]): float(r["Tarief (EUR/ton)"]) for _, r in edited_df.iterrows()}
        # group averages
        for g in GROUPS.values():
            rates[g["avg"]] = (rates[g["low"]] + rates[g["high"]]) / 2.0
        # combined average
        rates[COMBINED_AVG["target"]] = (rates[COMBINED_AVG["left_avg"]] + rates[COMBINED_AVG["right_avg"]]) / 2.0
        return rates

    calc_rates = compute_all_averages(edited)

    with st.expander("Preview berekende gemiddelden", expanded=True):
        preview = pd.DataFrame([
            {"MOP type": name, "Tarief (EUR/ton)": calc_rates.get(name, None)}
            for name in [
                GROUPS["Karton NL/BE"]["avg"],
                GROUPS["Bont NL/BE"]["avg"],
                GROUPS["Karton Verre Oosten"]["avg"],
                COMBINED_AVG["target"]
            ]
        ])
        st.dataframe(preview, use_container_width=True, hide_index=True)

    if st.button("Opslaan maandprijzen (incl. gemiddelden)", type="primary"):
        # Save low/high + calculated averages (no new types)
        for mop_name, rate in calc_rates.items():
            mop_id = mop_name_to_id.get(mop_name)
            if mop_id is None:
                st.error(f"MOP type ontbreekt in database: {mop_name}")
                st.stop()
            comment = "Berekend (gemiddelde)" if "(gemiddelde)" in mop_name and "Verre Oosten & Nederland" not in mop_name else None
            if mop_name == COMBINED_AVG["target"]:
                comment = "Berekend: (Karton NL/BE gem + Karton Verre Oosten gem)/2"
            if mop_name in [g["low"] for g in GROUPS.values()] + [g["high"] for g in GROUPS.values()]:
                comment = "Handmatige input"
            upsert_mop_rate(conn, mop_id, period_mop, float(rate), user, comment)
        st.success("MOP maandprijzen opgeslagen.")

# ---------------- TAB: Klanten ----------------
with tab_customers:
    st.subheader("Klanten")
    st.write("Overzicht + klant aanpassen. Historie is bewust verborgen voor overzicht.")

    # --- New customer at top ---
    with st.expander("Nieuwe klant aanmaken", expanded=True):
        c1, c2 = st.columns([1, 1])
        with c1:
            n_loc = st.text_input("Locatienummer", key="new_loc")
            n_name = st.text_input("Klantnaam", key="new_name")
            n_active = st.checkbox("Actief", value=True, key="new_active")
        with c2:
            n_mop = st.selectbox("Type MOP", [""] + mop_names_active, index=0, key="new_mop")
            n_disc = st.number_input("Afslag (EUR/ton)", value=0.0, step=1.0, key="new_disc")
            n_vf = st.date_input("Geldig vanaf", value=date.today().replace(day=1), key="new_vf")
            n_vt_on = st.checkbox("Geldig tot", value=False, key="new_vt_on")
            n_vt = st.date_input("Geldig tot", value=date.today(), key="new_vt") if n_vt_on else None
            n_comm = st.text_input("Opmerking", value="", key="new_comm")

        if st.button("Nieuwe klant opslaan", type="primary"):
            if not n_loc.strip() or not n_name.strip():
                st.error("Locatienummer en klantnaam zijn verplicht.")
            elif not n_mop.strip():
                st.error("Type MOP is verplicht voor nieuwe klant (je kunt later wijzigen).")
            else:
                try:
                    cur = exec_sql(conn, """
                        INSERT INTO customer (debtor_no, name, active, created_at, created_by)
                        VALUES (?, ?, ?, ?, ?)
                    """, (n_loc.strip(), n_name.strip(), 1 if n_active else 0, now_ts(), user))
                    new_cid = int(cur.lastrowid)
                    mop_id = mop_name_to_id[n_mop]
                    upsert_current_agreement(
                        conn, new_cid, mop_id, float(n_disc),
                        n_vf.isoformat(),
                        n_vt.isoformat() if n_vt else None,
                        n_comm.strip() or None,
                        user=user,
                        existing_agreement_id=None
                    )
                    st.success("Nieuwe klant + afspraak aangemaakt.")
                except sqlite3.IntegrityError:
                    st.error("Locatienummer bestaat al.")

    st.divider()

    # --- Overview table ---
    customers = get_customers(conn)
    search = st.text_input("Zoek klant (locatienummer of naam)", value="", key="cust_search_main")
    if search.strip():
        s = search.strip().lower()
        customers_view = customers[
            customers["debtor_no"].astype(str).str.lower().str.contains(s) |
            customers["name"].astype(str).str.lower().str.contains(s)
        ].copy()
    else:
        customers_view = customers.copy()

    rows = []
    for _, c in customers_view.iterrows():
        agr = get_current_agreement(conn, int(c["id"]))
        rows.append({
            "customer_id": int(c["id"]),
            "Locatienummer": str(c["debtor_no"]),
            "Klantnaam": str(c["name"]),
            "Actief": bool(int(c["active"])),
            "Type MOP": (str(agr["mop_type"]) if agr else ""),
            "Afslag (EUR/ton)": (float(agr["afslag"]) if agr else None),
            "Geldig vanaf": (agr["valid_from"] if agr else ""),
            "Geldig tot": (agr["valid_to"] if agr and agr["valid_to"] else ""),
            "Opmerking": (str(agr["comment"]) if agr and agr["comment"] else ""),
            "Afspraak ID": (int(agr["agreement_id"]) if agr else None)
        })
    overview = pd.DataFrame(rows)

    st.markdown("#### Overzicht")
    show_cols = ["Locatienummer", "Klantnaam", "Actief", "Type MOP", "Afslag (EUR/ton)", "Geldig vanaf", "Geldig tot", "Opmerking"]
    st.dataframe(overview[show_cols], use_container_width=True, hide_index=True)

    st.divider()

    # --- Edit selected customer (moves with selection) ---
    if len(overview) == 0:
        st.info("Geen klanten gevonden.")
    else:
        options = overview["customer_id"].tolist()
        def fmt(cid):
            r = overview[overview["customer_id"] == cid].iloc[0]
            return f"{r['Locatienummer']} — {r['Klantnaam']}"

        def load_selected():
            cid = st.session_state["edit_cust_id"]
            r = overview[overview["customer_id"] == cid].iloc[0]
            st.session_state["e_loc"] = r["Locatienummer"]
            st.session_state["e_name"] = r["Klantnaam"]
            st.session_state["e_active"] = bool(r["Actief"])
            st.session_state["e_mop"] = r["Type MOP"] if r["Type MOP"] else ""
            st.session_state["e_disc"] = float(r["Afslag (EUR/ton)"]) if pd.notna(r["Afslag (EUR/ton)"]) else 0.0
            st.session_state["e_vf"] = pd.to_datetime(r["Geldig vanaf"]).date() if str(r["Geldig vanaf"]).strip() else date.today().replace(day=1)
            vt_val = str(r["Geldig tot"]).strip() if pd.notna(r["Geldig tot"]) else ""
            st.session_state["e_vt_on"] = bool(vt_val)
            st.session_state["e_vt"] = pd.to_datetime(vt_val).date() if vt_val else date.today()
            st.session_state["e_comm"] = r["Opmerking"] if r["Opmerking"] else ""
            st.session_state["e_agr_id"] = r["Afspraak ID"]

        # Initialize selection
        if "edit_cust_id" not in st.session_state:
            st.session_state["edit_cust_id"] = options[0]
            load_selected()

        st.markdown("### Klant aanpassen")
        st.selectbox("Selecteer klant", options, format_func=fmt, key="edit_cust_id", on_change=load_selected)

        c1, c2 = st.columns([1, 1])
        with c1:
            st.text_input("Locatienummer", key="e_loc")
            st.text_input("Klantnaam", key="e_name")
            st.checkbox("Actief", key="e_active")
        with c2:
            st.selectbox("Type MOP", [""] + mop_names_active, key="e_mop")
            st.number_input("Afslag (EUR/ton)", step=1.0, key="e_disc")
            st.date_input("Geldig vanaf", key="e_vf")
            st.checkbox("Geldig tot", key="e_vt_on")
            if st.session_state.get("e_vt_on"):
                st.date_input("Geldig tot", key="e_vt")
            st.text_input("Opmerking", key="e_comm")

        b1, b2, b3 = st.columns([1, 1, 1])
        with b1:
            if st.button("Opslaan wijziging", type="primary"):
                cid = int(st.session_state["edit_cust_id"])
                # update customer
                try:
                    update_customer(conn, cid, str(st.session_state["e_loc"]).strip(), str(st.session_state["e_name"]).strip(), 1 if st.session_state["e_active"] else 0)
                except sqlite3.IntegrityError:
                    st.error("Locatienummer bestaat al.")
                    st.stop()

                # update/create agreement
                mop_name = str(st.session_state["e_mop"]).strip()
                if not mop_name:
                    st.error("Type MOP is verplicht.")
                    st.stop()
                mop_id = mop_name_to_id[mop_name]
                vf = st.session_state["e_vf"].isoformat()
                vt = st.session_state["e_vt"].isoformat() if st.session_state.get("e_vt_on") else None
                comm = str(st.session_state.get("e_comm") or "").strip() or None
                agr_id = st.session_state.get("e_agr_id")
                upsert_current_agreement(
                    conn, cid, mop_id, float(st.session_state["e_disc"]), vf, vt, comm,
                    user=user,
                    existing_agreement_id=safe_int(agr_id)
                )
                st.success("Opgeslagen.")
        with b2:
            if st.button("Deactiveren klant"):
                deactivate_customer(conn, int(st.session_state["edit_cust_id"]))
                st.success("Klant gedeactiveerd.")
        with b3:
            if st.button("Hard verwijderen"):
                try:
                    delete_customer_hard(conn, int(st.session_state["edit_cust_id"]))
                    st.success("Klant hard verwijderd.")
                except Exception as e:
                    st.error(str(e))

# ---------------- TAB: Run & export ----------------
with tab_run:
    st.subheader("Run & export")
    period_run = period_picker("Run-periode", "run")

    customers = get_customers(conn)
    customers_active = customers[customers["active"] == 1].copy()
    if len(customers_active) == 0:
        st.info("Geen actieve klanten.")
    else:
        rates = qdf(conn, """
            SELECT mr.mop_type_id, mr.rate_eur_per_ton, mt.name AS mop_type_name
            FROM mop_rate mr
            JOIN mop_type mt ON mt.id = mr.mop_type_id
            WHERE mr.period = ?
        """, (period_run,))
        rate_map = {int(r["mop_type_id"]): float(r["rate_eur_per_ton"]) for _, r in rates.iterrows()}
        type_name_map = {int(r["mop_type_id"]): str(r["mop_type_name"]) for _, r in rates.iterrows()}

        preview_rows = []
        missing = []
        for _, c in customers_active.iterrows():
            cid = int(c["id"])
            agr = find_agreement_for_period(conn, cid, period_run)
            if not agr:
                missing.append(f"{c['debtor_no']} — {c['name']}: geen afspraak geldig voor {ym_str(period_run)}")
                continue
            mop_type_id = int(agr["mop_type_id"])
            if mop_type_id not in rate_map:
                missing.append(f"{c['debtor_no']} — {c['name']}: geen MOP tarief voor type '{agr['mop_type_name']}' in {ym_str(period_run)}")
                continue
            mop_rate_used = rate_map[mop_type_id]
            discount_used = float(agr["discount_eur_per_ton"])
            ton_yield = mop_rate_used + discount_used
            preview_rows.append({
                "periode": ym_str(period_run),
                "customer_id": cid,
                "locatienummer": c["debtor_no"],
                "klantnaam": c["name"],
                "mop_type_id": mop_type_id,
                "mop_type": type_name_map.get(mop_type_id, str(agr["mop_type_name"])),
                "mop_rate_used": mop_rate_used,
                "discount_used": discount_used,
                "ton_yield": ton_yield,
                "comment": ""
            })

        if missing:
            st.warning("Niet alles kan berekend worden:")
            for m in missing:
                st.write(f"- {m}")

        if len(preview_rows) == 0:
            st.info("Geen berekenbare regels (controleer maandprijzen/afspraken).")
        else:
            preview_df = pd.DataFrame(preview_rows)
            edited = st.data_editor(
                preview_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "periode": st.column_config.TextColumn("Periode", disabled=True),
                    "customer_id": st.column_config.NumberColumn("customer_id", disabled=True),
                    "mop_type_id": st.column_config.NumberColumn("mop_type_id", disabled=True),
                    "mop_rate_used": st.column_config.NumberColumn("MOP tarief (EUR/ton)", disabled=True),
                    "discount_used": st.column_config.NumberColumn("Afslag (EUR/ton)", disabled=True),
                    "ton_yield": st.column_config.NumberColumn("Ton opbrengst (EUR/ton)", disabled=True),
                    "comment": st.column_config.TextColumn("Opmerking")
                }
            )

            note = st.text_input("Run-notitie (optioneel)", value="", key="run_note")
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("Run opslaan", type="primary", key="btn_save_run"):
                    run_id = create_run(conn, period_run, user, note.strip() or None, edited)
                    st.success(f"Run opgeslagen (ID: {run_id}).")
            with c2:
                export_cols = ["periode", "locatienummer", "klantnaam", "mop_type", "mop_rate_used", "discount_used", "ton_yield", "comment"]
                export_df = edited[export_cols].rename(columns={
                    "periode": "Periode",
                    "locatienummer": "Locatienummer",
                    "klantnaam": "Klantnaam",
                    "mop_type": "Type MOP",
                    "mop_rate_used": "MOP tarief (EUR/ton)",
                    "discount_used": "Afslag (EUR/ton)",
                    "ton_yield": "Ton opbrengst papier/karton (EUR/ton)",
                    "comment": "Opmerking"
                })
                st.download_button(
                    "Export naar Excel",
                    data=export_excel(export_df),
                    file_name=f"ton_opbrengst_{ym_str(period_run)}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# ---------------- TAB: Historie ----------------
with tab_history:
    st.subheader("Historie (runs)")
    runs = qdf(conn, """
        SELECT id, period, created_at, created_by, note
        FROM price_run
        ORDER BY period DESC, created_at DESC
    """)
    if len(runs) == 0:
        st.info("Nog geen runs opgeslagen.")
    else:
        st.dataframe(runs, use_container_width=True, hide_index=True)
        run_id = st.selectbox("Bekijk run", runs["id"].tolist(), key="hist_run_pick")
        lines = qdf(conn, """
            SELECT
                pr.period,
                c.debtor_no AS locatienummer,
                c.name AS klantnaam,
                mt.name AS mop_type,
                prl.mop_rate_used AS mop_rate_used,
                prl.discount_used AS afslag_used,
                prl.ton_yield AS ton_opbrengst,
                prl.comment AS opmerking
            FROM price_run_line prl
            JOIN price_run pr ON pr.id = prl.run_id
            JOIN customer c ON c.id = prl.customer_id
            JOIN mop_type mt ON mt.id = prl.mop_type_id
            WHERE prl.run_id = ?
            ORDER BY c.debtor_no
        """, (int(run_id),))
        st.dataframe(lines, use_container_width=True, hide_index=True)
        export_df = lines.rename(columns={
            "period": "Periode",
            "locatienummer": "Locatienummer",
            "klantnaam": "Klantnaam",
            "mop_type": "Type MOP",
            "mop_rate_used": "MOP tarief (EUR/ton)",
            "afslag_used": "Afslag (EUR/ton)",
            "ton_opbrengst": "Ton opbrengst papier/karton (EUR/ton)",
            "opmerking": "Opmerking"
        })
        st.download_button(
            "Export deze run naar Excel",
            data=export_excel(export_df),
            file_name=f"ton_opbrengst_run_{run_id}_{ym_str(runs.loc[runs['id']==run_id,'period'].values[0])}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

conn.close()
