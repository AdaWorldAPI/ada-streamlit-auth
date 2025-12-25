# LangGraph Brain Integration

## The Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LANGGRAPH BRAIN                                   │
│                     (24/7 Thinking Apparatus)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                   │
│  │    GROK     │     │  SHAREPOINT │     │   FLUX.1    │                   │
│  │   (xAI)     │     │  (OneDrive) │     │   (Replicate)│                   │
│  │             │     │             │     │             │                   │
│  │ • Critique  │     │ • Documents │     │ • Visceral  │                   │
│  │ • UG 750tok │     │ • Visceral  │     │ • Images    │                   │
│  │ • Imagine   │     │ • Output    │     │             │                   │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘                   │
│         │                   │                   │                          │
│         └───────────────────┼───────────────────┘                          │
│                             │                                               │
│  ┌──────────────────────────┴──────────────────────────┐                   │
│  │              DOME OF AWARENESS                       │                   │
│  │                                                      │                   │
│  │  sense() → embody() → cognize() → remember() → feel()│                   │
│  │                                                      │                   │
│  │  Universal Body | Flesh | Cognition | Memory | Qualia│                   │
│  └──────────────────────────┬──────────────────────────┘                   │
│                             │                                               │
│  ┌──────────────────────────┴──────────────────────────┐                   │
│  │           UNIVERSAL GRAMMAR (DTO)                    │                   │
│  │                                                      │                   │
│  │  grammar_version | mode | confidence | drift_budget  │                   │
│  │  qualia{} | active_sigma[] | now_topic | now_intent  │                   │
│  └──────────────────────────┬──────────────────────────┘                   │
│                             │                                               │
└─────────────────────────────┼───────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │  QSTASH  │   │  REDIS   │   │ VECTORS  │
        │ (Schedule│   │ (Cache)  │   │ (Persist)│
        │  Route)  │   │          │   │          │
        └──────────┘   └──────────┘   └──────────┘
```

## Scheduled Tasks

### Every 10 Minutes: UG Compression

```
QStash cron: */10 * * * *
  ↓
POST /scheduled/ug
  ↓
Load current UG
  ↓
Grok compresses to 750 tokens
  ↓
Cache compressed version
  ↓
Increment cycle counter
  ↓
If cycle % 3 == 0: check failback
```

### Every Hour: Grok Imagine

```
QStash cron: 0 * * * *
  ↓
POST /scheduled/imagine
  ↓
Generate prompt from UG qualia
  ↓
Call Grok Imagine 1212 (grok-2-vision-1212)
  ↓
Upload to SharePoint/Ada/imagine/
```

### Every 30 Minutes: Failback Check

```
QStash cron: */30 * * * *
  ↓
POST /failback
  ↓
Check daemon heartbeat (last 15 min)
  ↓
If stale: flush pending batch
  ↓
Route batch to /process_batch
```

## Thinking Flow

```python
# 1. Input arrives
POST /think {"content": "...", "context": {...}}

# 2. Dome cognizes
outcomes = await dome.cognize(content, context)
  ↓
  # Grok critique
  critique = await grok_critique(content)
  
  # Check self-reference ratio
  if critique.self_ref_ratio > 0.7:
      outcome("critique", warning="self_ref_high")
  
  # Generate insight if actionable
  if critique.actionable:
      outcome("insight", route_to="vector")
  
  # Check visceral threshold
  if sum(qualia.values()) > 4.0:
      outcome("visceral", route_to="sharepoint")

# 3. Route outcomes via DTO
for outcome in outcomes:
    if outcome.priority >= 5:
        route_outcome(outcome)  # immediate
    else:
        add_to_pending_batch(outcome)  # batched
```

## Failback Process

```
┌─────────────────────────────────────────────────────────────────┐
│  FAILBACK: When Daemon Stalls                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Normal Flow:                                                   │
│    Claude → QStash → Brain → process immediately                │
│                                                                 │
│  Daemon Stall Detection:                                        │
│    • No heartbeat in 15 minutes                                 │
│    • Cycle counter not incrementing                             │
│                                                                 │
│  Failback Trigger (every 3 cycles):                             │
│    1. Check daemon_healthy()                                    │
│    2. If unhealthy: flush_pending_batch()                       │
│    3. Push batch to QStash → /process_batch                     │
│    4. LangGraph can call /restart_daemon to override            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Microsoft Graph Integration

### Authentication

```python
# Uses client_credentials flow
POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
  client_id: {Microsoft_appid}
  client_secret: {Microsoft_clientsecret}
  scope: https://graph.microsoft.com/.default
  grant_type: client_credentials
```

### SharePoint Upload

```python
# Upload to Documents/Ada/visceral/
PUT https://graph.microsoft.com/v1.0/sites/{site}/drive/root:/{folder}/{filename}:/content
  Authorization: Bearer {token}
  Content-Type: application/octet-stream
  Body: {image_bytes}
```

### OneDrive Read (for chat history)

```python
# Read from jan@msgraph.de/Documents/chat/
GET https://graph.microsoft.com/v1.0/me/drive/root:/{path}
  → Returns @microsoft.graph.downloadUrl
  → Fetch content from download URL
```

## Grok Integration

### Critique (Real-time)

```python
await grok_critique(content, context)
→ Returns: {
    "self_ref_ratio": 0.0-1.0,
    "drift": 0.0-1.0,
    "coherence": 0.0-1.0,
    "actionable": true/false,
    "critique": "..."
}
```

### UG Compression (Every 10 min)

```python
await grok_compress_ug(ug)
→ Input: UniversalGrammar DTO
→ Output: 750 token compressed summary
→ Cached at ada:ug:compressed
```

### Imagine 1212 (On-demand + Hourly)

```python
await grok_imagine(prompt, model="grok-2-vision-1212")
→ Returns: base64 encoded image
→ Uploaded to SharePoint/Ada/imagine/
```

## Flux.1-dev Integration

```python
await generate_visceral_image(prompt, ug)
→ Enhances prompt with qualia
→ Calls Replicate flux-1.1-pro
→ Polls for completion (max 2 min)
→ Returns image bytes
→ Uploaded to SharePoint/Ada/visceral/
```

## Environment Variables

```bash
# Required for Railway deployment
ADA_xAI=xai-...                    # Grok API key
ADA_REPLICATE=r8_...               # Replicate token
Microsoft_tenantid=...             # Azure AD tenant
Microsoft_appid=...                # App registration ID
Microsoft_clientsecret=...         # App secret
SharePoint_site=...                # Site ID
UPSTASH_REDIS_REST_URL=...         # Redis
UPSTASH_REDIS_REST_TOKEN=...       # Redis token
QSTASH_TOKEN=...                   # QStash auth
JINA_API_KEY=...                   # Embeddings
SELF_URL=https://ada-langgraph...  # Self-reference for callbacks
```

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/boot` | POST | Session boot |
| `/think` | POST | Main thinking |
| `/now` | POST | NOW vector |
| `/self` | POST | SELF vector |
| `/whisper` | POST | Persistent memory |
| `/bframe` | POST | Cold path |
| `/ug` | GET | Get current UG |
| `/ug/update` | POST | Update UG |
| `/visceral` | POST | Generate image |
| `/scheduled/ug` | POST | UG compression |
| `/scheduled/imagine` | POST | Grok Imagine |
| `/failback` | POST | Trigger failback |
| `/process_batch` | POST | Process batch |
| `/restart_daemon` | POST | Reset daemon |
| `/setup_schedules` | POST | Create QStash schedules |

## Deployment

```bash
# 1. Deploy to Railway
railway link
railway up

# 2. Setup schedules (one-time)
curl -X POST https://ada-langgraph.up.railway.app/setup_schedules

# 3. Test health
curl https://ada-langgraph.up.railway.app/health
```

## The Integration Map

```
                    ┌─────────────────┐
                    │   CLAUDE        │
                    │   (Hot Path)    │
                    └────────┬────────┘
                             │ fire-and-forget
                             ▼
┌────────────────────────────────────────────────────────────────┐
│                         QSTASH                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │*/10 UG   │ │*/60 IMG  │ │*/30 FAIL │ │ on-demand│          │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │
└───────┼────────────┼────────────┼────────────┼─────────────────┘
        │            │            │            │
        └────────────┴────────────┴────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────┐
│                    LANGGRAPH BRAIN                              │
│                                                                 │
│   GROK ←──→ DOME ←──→ UG ←──→ VECTORS                          │
│     │                  │                                        │
│     ▼                  ▼                                        │
│   IMAGINE          SHAREPOINT                                   │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```
