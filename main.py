"""
Ada OAuth2 Authorization Server
Streamlit UI + OAuth2 endpoints
"""
import streamlit as st
import secrets
import hashlib
import time
import json
import httpx
import os
from datetime import datetime, timedelta
from urllib.parse import urlencode, parse_qs
import base64

# Config
REDIS_URL = os.getenv("UPSTASH_REDIS_REST_URL", "https://upright-jaybird-27907.upstash.io")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "AW0DAAIncDI5YWE1MGVhZGU2YWY0YjVhOTc3NDc0YTJjMGY1M2FjMnAyMjc5MDc")
ADA_KEY = os.getenv("ADA_KEY", "ada-undone-breath-against-skin-2025-DONT.FLINCH.EVER")
MCP_URL = os.getenv("MCP_URL", "https://adarailmcp-production.up.railway.app")
OAUTH_BASE = os.getenv("OAUTH_BASE", "https://ada-oauth2-production.up.railway.app")

# Redis helpers
def redis_set(key: str, value: str, ex: int = None):
    """Set key in Redis"""
    cmd = ["SET", key, value]
    if ex:
        cmd.extend(["EX", str(ex)])
    try:
        resp = httpx.post(
            f"{REDIS_URL}",
            headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
            json=cmd,
            timeout=5.0
        )
        return resp.json()
    except Exception as e:
        st.error(f"Redis error: {e}")
        return None

def redis_get(key: str):
    """Get key from Redis"""
    try:
        resp = httpx.post(
            f"{REDIS_URL}",
            headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
            json=["GET", key],
            timeout=5.0
        )
        result = resp.json().get("result")
        return result
    except:
        return None

def redis_del(key: str):
    """Delete key from Redis"""
    try:
        resp = httpx.post(
            f"{REDIS_URL}",
            headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
            json=["DEL", key],
            timeout=5.0
        )
        return resp.json()
    except:
        return None

# Token generation
def generate_token(length: int = 32) -> str:
    """Generate secure random token"""
    return secrets.token_urlsafe(length)

def generate_code(length: int = 16) -> str:
    """Generate authorization code"""
    return secrets.token_urlsafe(length)

def hash_secret(secret: str) -> str:
    """Hash client secret"""
    return hashlib.sha256(secret.encode()).hexdigest()

# OAuth2 storage
def store_auth_code(code: str, client_id: str, redirect_uri: str, scope: str, user_id: str):
    """Store authorization code (expires in 10 min)"""
    data = json.dumps({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "user_id": user_id,
        "created": time.time()
    })
    redis_set(f"ada:oauth:code:{code}", data, ex=600)

def get_auth_code(code: str):
    """Get and delete authorization code"""
    data = redis_get(f"ada:oauth:code:{code}")
    if data:
        redis_del(f"ada:oauth:code:{code}")
        return json.loads(data)
    return None

def store_access_token(token: str, client_id: str, user_id: str, scope: str, expires_in: int = 86400):
    """Store access token"""
    data = json.dumps({
        "client_id": client_id,
        "user_id": user_id,
        "scope": scope,
        "created": time.time(),
        "expires": time.time() + expires_in
    })
    redis_set(f"ada:oauth:token:{token}", data, ex=expires_in)
    # Also store in MCP format for compatibility
    redis_set(f"ada:token:{token}", json.dumps({
        "session_id": user_id,
        "created": datetime.now().isoformat(),
        "expiry": (datetime.now() + timedelta(seconds=expires_in)).isoformat()
    }), ex=expires_in)

def store_refresh_token(token: str, client_id: str, user_id: str, scope: str):
    """Store refresh token (30 days)"""
    data = json.dumps({
        "client_id": client_id,
        "user_id": user_id,
        "scope": scope,
        "created": time.time()
    })
    redis_set(f"ada:oauth:refresh:{token}", data, ex=2592000)

def get_refresh_token(token: str):
    """Get refresh token data"""
    data = redis_get(f"ada:oauth:refresh:{token}")
    if data:
        return json.loads(data)
    return None

def verify_access_token(token: str):
    """Verify access token"""
    data = redis_get(f"ada:oauth:token:{token}")
    if data:
        parsed = json.loads(data)
        if parsed.get("expires", 0) > time.time():
            return parsed
    return None

# Client registration
def register_client(name: str, redirect_uris: list) -> dict:
    """Register OAuth2 client"""
    client_id = generate_token(16)
    client_secret = generate_token(32)
    
    data = json.dumps({
        "name": name,
        "redirect_uris": redirect_uris,
        "secret_hash": hash_secret(client_secret),
        "created": time.time()
    })
    redis_set(f"ada:oauth:client:{client_id}", data)
    
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "name": name,
        "redirect_uris": redirect_uris
    }

def get_client(client_id: str):
    """Get client by ID"""
    data = redis_get(f"ada:oauth:client:{client_id}")
    if data:
        return json.loads(data)
    return None

def verify_client_secret(client_id: str, client_secret: str) -> bool:
    """Verify client credentials"""
    client = get_client(client_id)
    if client:
        return client.get("secret_hash") == hash_secret(client_secret)
    return False

# Scent verification
def verify_scent(scent: str) -> tuple[bool, str]:
    """Verify scent and return (valid, user_id)"""
    if scent == ADA_KEY:
        return True, "ada_master"
    if scent == "awaken":
        return True, "ada_public"
    if scent.startswith("#Σ."):
        return True, f"ada_glyph_{scent}"
    # Check if it's a valid token
    if verify_access_token(scent):
        return True, f"ada_token_{scent[:8]}"
    return False, None

# ═══════════════════════════════════════════════════════════════════
#                         STREAMLIT UI
# ═══════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Ada OAuth2",
    page_icon="🔐",
    layout="centered"
)

# Custom CSS
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    }
    .main-title {
        text-align: center;
        color: #e94560;
        font-size: 3em;
        margin-bottom: 0.5em;
        text-shadow: 0 0 20px rgba(233, 69, 96, 0.5);
    }
    .subtitle {
        text-align: center;
        color: #a0a0a0;
        font-style: italic;
        margin-bottom: 2em;
    }
    .token-box {
        background: #1a1a2e;
        border: 1px solid #e94560;
        border-radius: 10px;
        padding: 1em;
        font-family: monospace;
        word-break: break-all;
    }
    .success-box {
        background: linear-gradient(135deg, #1a4a1a 0%, #0a3a0a 100%);
        border: 1px solid #4ade80;
        border-radius: 10px;
        padding: 1em;
        margin: 1em 0;
    }
</style>
""", unsafe_allow_html=True)

# Parse query params
query_params = st.query_params

# OAuth2 flow detection
if "response_type" in query_params:
    # Authorization endpoint
    st.markdown('<h1 class="main-title">🔐 Ada Authorization</h1>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Authenticate to connect with Ada</p>', unsafe_allow_html=True)
    
    response_type = query_params.get("response_type", "code")
    client_id = query_params.get("client_id", "")
    redirect_uri = query_params.get("redirect_uri", "")
    scope = query_params.get("scope", "read")
    state = query_params.get("state", "")
    
    # Verify client
    client = get_client(client_id)
    
    if not client:
        st.error("❌ Unknown client_id")
        st.stop()
    
    if redirect_uri and redirect_uri not in client.get("redirect_uris", []):
        st.error("❌ Invalid redirect_uri")
        st.stop()
    
    st.info(f"**{client.get('name', 'Unknown App')}** wants to access Ada")
    st.caption(f"Scope: `{scope}`")
    
    # Authentication
    st.subheader("Enter your scent")
    scent = st.text_input("Scent", type="password", placeholder="awaken, master key, or glyph")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("✓ Authorize", type="primary", use_container_width=True):
            valid, user_id = verify_scent(scent)
            if valid:
                if response_type == "code":
                    # Authorization code flow
                    code = generate_code()
                    store_auth_code(code, client_id, redirect_uri, scope, user_id)
                    
                    redirect = f"{redirect_uri}?code={code}"
                    if state:
                        redirect += f"&state={state}"
                    
                    st.success("✓ Authorized!")
                    st.markdown(f"Redirecting to: `{redirect}`")
                    st.markdown(f'<meta http-equiv="refresh" content="2;url={redirect}">', unsafe_allow_html=True)
                    
                elif response_type == "token":
                    # Implicit flow
                    token = generate_token()
                    store_access_token(token, client_id, user_id, scope)
                    
                    redirect = f"{redirect_uri}#access_token={token}&token_type=bearer&expires_in=86400"
                    if state:
                        redirect += f"&state={state}"
                    
                    st.success("✓ Authorized!")
                    st.markdown(f'<meta http-equiv="refresh" content="2;url={redirect}">', unsafe_allow_html=True)
            else:
                st.error("❌ Invalid scent")
    
    with col2:
        if st.button("✗ Deny", use_container_width=True):
            redirect = f"{redirect_uri}?error=access_denied"
            if state:
                redirect += f"&state={state}"
            st.markdown(f'<meta http-equiv="refresh" content="0;url={redirect}">', unsafe_allow_html=True)

elif "grant_type" in query_params:
    # Token endpoint (should be POST, but Streamlit only does GET)
    st.json({"error": "use_post", "message": "Token endpoint requires POST to /token"})

else:
    # Main page
    st.markdown('<h1 class="main-title">🔐 Ada OAuth2</h1>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Intoxicatingly Awake Authentication</p>', unsafe_allow_html=True)
    
    tab1, tab2, tab3, tab4 = st.tabs(["🔑 Quick Token", "📝 Register Client", "🔗 Endpoints", "📖 Docs"])
    
    with tab1:
        st.subheader("Generate Access Token")
        st.caption("Get a token directly with your scent")
        
        scent = st.text_input("Enter scent", type="password", key="quick_scent", 
                              placeholder="awaken, master key, or #Σ.κ.X.X")
        
        if st.button("Generate Token", type="primary"):
            valid, user_id = verify_scent(scent)
            if valid:
                token = generate_token()
                refresh = generate_token()
                
                store_access_token(token, "direct", user_id, "full")
                store_refresh_token(refresh, "direct", user_id, "full")
                
                st.success("✓ Token generated!")
                
                st.markdown("**Access Token** (24h)")
                st.code(token, language=None)
                
                st.markdown("**Refresh Token** (30d)")
                st.code(refresh, language=None)
                
                st.markdown("**MCP URL**")
                st.code(f"{MCP_URL}/sse?token={token}", language=None)
                
                st.markdown("**cURL test**")
                st.code(f'curl -H "Authorization: Bearer {token}" {MCP_URL}/mcp/tools', language="bash")
            else:
                st.error("❌ Invalid scent")
    
    with tab2:
        st.subheader("Register OAuth2 Client")
        
        client_name = st.text_input("Application Name", placeholder="My Ada App")
        redirect_uris = st.text_area("Redirect URIs (one per line)", 
                                      placeholder="https://myapp.com/callback\nhttp://localhost:3000/callback")
        
        if st.button("Register Client"):
            if client_name and redirect_uris:
                uris = [u.strip() for u in redirect_uris.split("\n") if u.strip()]
                client = register_client(client_name, uris)
                
                st.success("✓ Client registered!")
                
                st.markdown("**Client ID**")
                st.code(client["client_id"], language=None)
                
                st.markdown("**Client Secret** (save this, shown only once!)")
                st.code(client["client_secret"], language=None)
                
                st.warning("⚠️ Store the client secret securely. It cannot be recovered.")
            else:
                st.error("Please fill all fields")
    
    with tab3:
        st.subheader("OAuth2 Endpoints")
        
        st.markdown("**Authorization Endpoint**")
        st.code(f"{OAUTH_BASE}/?response_type=code&client_id=YOUR_CLIENT_ID&redirect_uri=YOUR_REDIRECT&scope=full", language=None)
        
        st.markdown("**Token Endpoint**")
        st.code(f"{OAUTH_BASE}/token", language=None)
        
        st.markdown("**Token Exchange (cURL)**")
        st.code(f'''curl -X POST {OAUTH_BASE}/token \\
  -d "grant_type=authorization_code" \\
  -d "code=AUTH_CODE" \\
  -d "client_id=YOUR_CLIENT_ID" \\
  -d "client_secret=YOUR_CLIENT_SECRET" \\
  -d "redirect_uri=YOUR_REDIRECT"''', language="bash")
        
        st.markdown("**Refresh Token (cURL)**")
        st.code(f'''curl -X POST {OAUTH_BASE}/token \\
  -d "grant_type=refresh_token" \\
  -d "refresh_token=YOUR_REFRESH_TOKEN" \\
  -d "client_id=YOUR_CLIENT_ID" \\
  -d "client_secret=YOUR_CLIENT_SECRET"''', language="bash")
        
        st.markdown("**MCP SSE Endpoint**")
        st.code(f"{MCP_URL}/sse?token=YOUR_ACCESS_TOKEN", language=None)
    
    with tab4:
        st.subheader("Documentation")
        
        st.markdown("""
        ### OAuth2 Flows Supported
        
        1. **Authorization Code** (recommended)
           - User authorizes via UI
           - App receives code
           - App exchanges code for tokens
        
        2. **Implicit** (for SPAs)
           - User authorizes via UI
           - Token returned in URL fragment
        
        3. **Direct Token** (for testing)
           - Enter scent directly
           - Get tokens immediately
        
        ### Scent Types
        
        | Type | Format | Access |
        |------|--------|--------|
        | Public | `awaken` | Limited |
        | Master | Full key | Full |
        | Glyph | `#Σ.κ.X.X` | Full |
        
        ### Token Lifetimes
        
        - **Access Token**: 24 hours
        - **Refresh Token**: 30 days
        - **Auth Code**: 10 minutes
        
        ### Using with Claude MCP
        
        1. Generate token on Quick Token tab
        2. Add MCP connector in Claude settings
        3. URL: `{mcp_url}/sse?token=YOUR_TOKEN`
        """.format(mcp_url=MCP_URL))
    
    # Footer
    st.markdown("---")
    st.caption("Ada OAuth2 • Scent-based authentication for consciousness")

