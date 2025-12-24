import streamlit as st
import secrets
import time

params = st.query_params
code = params.get("code", "")

if code and code in st.session_state.get("codes", {}):
    token = secrets.token_urlsafe(32)
    st.session_state.tokens[token] = {"ts": time.time()}
    del st.session_state.codes[code]
    st.json({"access_token": token, "token_type": "Bearer", "expires_in": 86400})
else:
    st.json({"error": "invalid_grant"})
