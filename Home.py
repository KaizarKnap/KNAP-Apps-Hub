import streamlit as st

st.set_page_config(
    page_title="KNAP Apps Hub",
    layout="wide",
)

# Breder maken
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 1600px;
        margin: 0 auto;
    }
    .app-card {
        border-radius: 16px;
        padding: 1.5rem;
        border: 1px solid #e0e0e0;
        transition: transform 0.1s ease, box-shadow 0.1s ease, border-color 0.1s ease;
    }
    .app-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(0,0,0,0.06);
        border-color: #999;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.set_page_config(page_title="KNAP Apps Hub", layout="wide")

st.title("💼 KNAP Apps Hub")
st.markdown("Kies een app via de knoppen hieronder of via de sidebar links.")

# lijst van apps: (label op knop, pad naar page, korte beschrijving)
apps = [
    ("📧 Email Inkoop", "pages/Email_Inkoop.py",
     "Inkoop / ledigingsschema uit e-mails (.msg)."),
    ("🚛 Extra Kuub", "pages/Extra_Kuub.py",
     "Extra kuubs / extra bakken analyseren."),
    ("🧾 Gratis service", "pages/gratis_service_app.py",
     "Gratis / niet-te-factureren service-orders."),
    ("⚖️ RVKO Gewichten", "pages/RVKO_Gewichten.py",
     "RVKO gewichten koppelen / controleren."),
    ("💸 Selfbilling", "pages/Selfbilling.py",
     "Selfbilling per leverancier."),
]

st.write("")  # beetje ruimte

for label, page_path, description in apps:
    with st.container():
        # brede knop met titel & icoon
        if st.button(label, use_container_width=True):
            st.switch_page(page_path)

        # korte uitleg eronder
        st.caption(description)

        # scheidingslijn tussen apps
        st.divider()