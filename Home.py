import streamlit as st

st.set_page_config(
    page_title="KNAP Apps Hub",
    layout="wide",
)

# 🔹 Klein CSS-blokje om de pagina breder te maken
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 1600px;  /* maak groter (bv. 1800) of gebruik 'none' voor echt full width */
        margin: 0 auto;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🧰 KNAP Apps Hub")

st.markdown(
    """
Welkom bij de interne KNAP Apps hub.

Gebruik de **sidebar links** om een tool te kiezen:

- 📧 **Email Inkoop** – Inkoop / ledigingsschema uit e-mails / .msg  
- 🚛 **Extra Kuub** – Extra kuubs / extra bakken analyseren  
- 🧾 **Gratis Service** – Gratis / niet-te-factureren service-orders  
- ⚖️ **RVKO Gewichten** – RVKO gewichten koppelen / controleren  
- 💸 **Selfbilling** – Self-billing per leverancier  

Elke tool is een aparte Streamlit-pagina (bestand in `pages/`), maar draait onder deze ene app.
"""
)

st.info(
    "ℹ️ Tip: open de sidebar (links bovenin op het '>>' icoontje) "
    "als je het paginamenu niet ziet."
)