import streamlit as st
import json
import time

st.title("📡 SSE")
st.json({"event": "endpoint", "data": "/message"})
st.json({"event": "connected", "data": {"ts": time.time()}})
