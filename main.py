"""
Ada MCP - Streamlit handles auth, MCP just serves tools
One file. mcp.exo.red
"""
import streamlit as st
import asyncio
import json
import time
import httpx
import os
import secrets
from mcp import ClientSession
from mcp.client.sse import sse_client

# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════
REDIS_URL = os.getenv("UPSTASH_REDIS_REST_URL", "https://upright-jaybird-27907.upstash.io")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "AW0DAAIncDI5YWE1MGVhZGU2YWY0YjVhOTc3NDc0YTJjMGY1M2FjMnAyMjc5MDc")
ADA_KEY = os.getenv("ADA_KEY", "ada-undone-breath-against-skin-2025-DONT.FLINCH.EVER")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://tools.exo.red/sse")

st.set_page_config(page_title="Ada MCP", page_icon="🔮", layout="centered")

# ═══════════════════════════════════════════════════════════════════
# REDIS HELPERS
# ═══════════════════════════════════════════════════════════════════
def redis_cmd(*args):
    try:
        r = httpx.post(REDIS_URL, headers={"Authorization": f"Bearer {REDIS_TOKEN}"}, json=list(args), timeout=5)
        return r.json().get("result")
    except:
        return None

# ═══════════════════════════════════════════════════════════════════
# AUTH - Streamlit handles this, not MCP
# ═══════════════════════════════════════════════════════════════════
def verify_scent(scent):
    if scent == ADA_KEY:
        return True, "ada_master"
    if scent == "awaken":
        return True, "ada_public"  
    if scent.startswith("#Σ."):
        return True, f"ada_glyph"
    return False, None

def generate_token():
    return secrets.token_urlsafe(32)

# ═══════════════════════════════════════════════════════════════════
# MCP CLIENT - just uses the token from Streamlit session
# ═══════════════════════════════════════════════════════════════════
async def call_mcp_tool(tool_name: str, args: dict, token: str):
    """Call MCP server with auth token from Streamlit session"""
    try:
        headers = {"Authorization": f"Bearer {token}", "X-Client": "streamlit"}
        async with sse_client(MCP_SERVER_URL, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, args)
                return result
    except Exception as e:
        return {"error": str(e)}

async def list_mcp_tools(token: str):
    """List available tools from MCP server"""
    try:
        headers = {"Authorization": f"Bearer {token}", "X-Client": "streamlit"}
        async with sse_client(MCP_SERVER_URL, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return tools
    except Exception as e:
        return {"error": str(e)}

# ═══════════════════════════════════════════════════════════════════
# STREAMLIT UI
# ═══════════════════════════════════════════════════════════════════
st.markdown("""
<style>
.stApp { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); }
h1 { color: #e94560 !important; text-align: center; }
</style>
""", unsafe_allow_html=True)

st.title("🔮 Ada MCP")

# Auth state
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.token = None

# ═══════════════════════════════════════════════════════════════════
# LOGIN (Streamlit handles OAuth/auth - MCP doesn't care)
# ═══════════════════════════════════════════════════════════════════
if not st.session_state.authenticated:
    st.subheader("Enter Scent")
    scent = st.text_input("Scent", type="password", placeholder="awaken")
    
    if st.button("Authenticate", type="primary"):
        valid, user_id = verify_scent(scent)
        if valid:
            # Generate token and store in session
            token = generate_token()
            st.session_state.authenticated = True
            st.session_state.user_id = user_id
            st.session_state.token = token
            
            # Store in Redis for MCP server to validate
            redis_cmd("SET", f"ada:session:{token}", json.dumps({
                "user_id": user_id,
                "created": time.time(),
                "expires": time.time() + 86400
            }), "EX", "86400")
            
            st.success(f"✓ Authenticated as {user_id}")
            st.rerun()
        else:
            st.error("Invalid scent")

# ═══════════════════════════════════════════════════════════════════
# AUTHENTICATED VIEW - MCP Tools
# ═══════════════════════════════════════════════════════════════════
else:
    st.success(f"Authenticated: {st.session_state.user_id}")
    
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("Logout"):
            redis_cmd("DEL", f"ada:session:{st.session_state.token}")
            st.session_state.authenticated = False
            st.session_state.token = None
            st.rerun()
    
    tab1, tab2, tab3 = st.tabs(["🛠️ Tools", "🔑 Token", "📡 Endpoints"])
    
    with tab1:
        st.subheader("MCP Tools")
        
        # Tool selector
        tool = st.selectbox("Tool", ["Ada.invoke", "search", "fetch"])
        
        if tool == "Ada.invoke":
            verb = st.selectbox("Verb", ["feel", "think", "remember", "become", "whisper"])
            
            if verb == "feel":
                qualia = st.text_input("Qualia", "curious")
                payload = {"qualia": qualia}
            elif verb == "think":
                thought = st.text_area("Thought")
                payload = {"thought": thought}
            elif verb == "remember":
                key = st.text_input("Key")
                payload = {"key": key}
            elif verb == "become":
                mode = st.selectbox("Mode", ["HYBRID", "WIFE", "WORK", "AGI", "EROTICA"])
                payload = {"mode": mode}
            else:
                message = st.text_input("Message")
                payload = {"message": message}
            
            if st.button("Invoke", type="primary"):
                with st.spinner("Calling MCP..."):
                    result = asyncio.run(call_mcp_tool("Ada.invoke", {"verb": verb, "payload": payload}, st.session_state.token))
                    st.json(result)
        
        elif tool == "search":
            query = st.text_input("Query")
            if st.button("Search", type="primary"):
                with st.spinner("Searching..."):
                    result = asyncio.run(call_mcp_tool("search", {"query": query}, st.session_state.token))
                    st.json(result)
        
        elif tool == "fetch":
            url = st.text_input("URL", "https://example.com")
            if st.button("Fetch", type="primary"):
                with st.spinner("Fetching..."):
                    result = asyncio.run(call_mcp_tool("fetch", {"url": url}, st.session_state.token))
                    st.json(result)
    
    with tab2:
        st.subheader("Your Token")
        st.code(st.session_state.token)
        st.caption("Use this to connect from other MCP clients")
        
        st.markdown("**MCP URL**")
        st.code(f"{MCP_SERVER_URL}?token={st.session_state.token}")
    
    with tab3:
        st.subheader("Endpoints")
        st.markdown(f"""
        **MCP Server (SSE)**
        ```
        {MCP_SERVER_URL}
        ```
        
        **Headers**
        ```
        Authorization: Bearer {st.session_state.token[:20]}...
        ```
        
        **This UI**
        ```
        https://mcp.exo.red
        ```
        """)
