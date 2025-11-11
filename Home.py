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

st.title("🧰 KNAP Apps Hub")
st.markdown("Kies een app via de tegels hieronder of via de sidebar links.")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("### 📧 Email Inkoop"):
        st.switch_page("pages/Email_Inkoop.py")
    st.markdown("</div>", unsafe_allow_html=True)

with col2:
    if st.button("### 🚛 Extra Kuub"):
        st.switch_page("pages/Extra_Kuub.py")
    st.markdown("</div>", unsafe_allow_html=True)

with col3:
    if st.button("### 🧾 Gratis service"):
        st.switch_page("pages/gratis_service_app.py")
    st.markdown("</div>", unsafe_allow_html=True)

col4, col5, _ = st.columns(3)

with col4:
    if st.button("### ⚖️ RVKO Gewichten"):
        st.switch_page("pages/RVKO_Gewichten.py")
    st.markdown("</div>", unsafe_allow_html=True)

with col5:
    if st.button("### 💸 Selfbilling"):
        st.switch_page("pages/Selfbilling.py")
    st.markdown("</div>", unsafe_allow_html=True)