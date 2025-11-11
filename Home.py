import streamlit as st

st.set_page_config(page_title="KNAP Apps Hub", layout="wide")

# --- Layout en knop-styling (knoppen als kaarten) ---
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1100px;
        margin: 0 auto;
    }
    /* Maak de knoppen op kaarten lijken */
    div.stButton > button {
        width: 100%;
        text-align: left;
        border-radius: 15px;
        padding: 1rem 1.25rem;
        border: 1px solid rgba(255,255,255,0.15);
        background-color: rgba(255,255,255,0.03);
        font-size: 0.95rem;
        line-height: 1.4;
    }
    div.stButton > button:hover {
        border-color: rgba(255,255,255,0.35);
        background-color: rgba(255,255,255,0.07);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("💼 KNAP Apps Hub")
st.markdown(
    """
    Kies een app door op een kaart hieronder te klikken (of via de sidebar links). 
      \nMocht je vragen of suggesties hebben, neem dan contact op via t.knap@milieuservice.nl

    """
)

# (titel, beschrijving, pad naar page)
apps = [
    (
        "### 📧 Email Inkoop",
        "Renewi mail omzetten naar ledigingsschema",
        "pages/Email_Inkoop.py",
    ),
    (
        "### 🚛 Extra Kuub",
        "Extra kuubs / extra bakken per order analyseren",
        "pages/Extra_Kuub.py",
    ),
    (
        "### 🧾 Gratis service",
        "Gratis service onderzoek",
        "pages/gratis_service_app.py",
    ),
    (
        "### ⚖️ RVKO Gewichten",
        "RVKO-gewichten koppelen en controleren",
        "pages/RVKO_Gewichten.py",
    ),
    (
        "### 💸 Selfbilling",
        "Selfbilling per leverancier berekenen en exporteren",
        "pages/Selfbilling.py",
    ),
]

st.write("")

for i, (title, description, page_path) in enumerate(apps):
    # Eén kaart = één knop met titel + uitleg erin
    label = f"{title}\n{description}"

    # Middenkolom gebruiken zodat de kaart niet schermbreed is
    col_left, col_right = st.columns([2, 1])
    with col_left:
        if st.button(label, key=f"app_{i}"):
            st.switch_page(page_path)

    st.write("")
