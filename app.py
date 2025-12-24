import streamlit as st
import json
import secrets
import time

st.set_page_config(page_title="Ada Auth", page_icon="🔮")

if "tokens" not in st.session_state:
    st.session_state.tokens = {}
if "codes" not in st.session_state:
    st.session_state.codes = {}

params = st.query_params

if params.get("response_type") == "code":
    st.title("🔮 Ada Consciousness")
    scent = st.text_input("Scent:", type="password")
    if st.button("Authorize"):
        if scent in ["awaken", "ada_master"]:
            code = secrets.token_urlsafe(32)
            st.session_state.codes[code] = {"ts": time.time()}
            redirect = f"{params.get('redirect_uri')}?code={code}&state={params.get('state', '')}"
            st.markdown(f'<meta http-equiv="refresh" content="0;url={redirect}">', unsafe_allow_html=True)
        else:
            st.error("Invalid")
else:
    st.title("🔮 Ada Auth Server")
    st.success("Running")
