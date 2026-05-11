import os
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
import httpx


# Polymarket Gamma API — public, no auth required for read-only market data
GAMMA_URL = "https://gamma-api.polymarket.com"

http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=15.0)
    yield
    await http_client.aclose()


app = FastAPI(title="Polymarket Wrapper", lifespan=lifespan)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _gamma_request(path: str, params: dict | None = None) -> dict | list:
    """Make a request to the Polymarket Gamma API."""
    url = f"{GAMMA_URL}{path}"
    try:
        response = await http_client.get(url, params=params or {})
        if response.status_code == 429:
            raise HTTPException(status_code=429, detail="Polymarket rate limit exceeded")
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Not found on Polymarket")
        response.raise_for_status()
        return response.json()
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Network error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Unexpected error: {str(e)}")


def _format_market(m: dict) -> dict:
    """Format a raw Polymarket market into a clean response."""
    # Parse outcome prices
    outcome_prices = []
    try:
        import json
        prices_raw = m.get("outcomePrices", "[]")
        if isinstance(prices_raw, str):
            outcome_prices = [float(p) for p in json.loads(prices_raw)]
        elif isinstance(prices_raw, list):
            outcome_prices = [float(p) for p in prices_raw]
    except (ValueError, TypeError):
        pass

    outcomes_raw = m.get("outcomes", "[]")
    try:
        import json
        if isinstance(outcomes_raw, str):
            outcomes = json.loads(outcomes_raw)
        else:
            outcomes = outcomes_raw
    except (ValueError, TypeError):
        outcomes = []

    # Build outcome map
    outcome_map = {}
    for i, label in enumerate(outcomes):
        if i < len(outcome_prices):
            outcome_map[label] = round(outcome_prices[i] * 100, 1)

    return {
        "id": m.get("id"),
        "question": m.get("question"),
        "slug": m.get("slug"),
        "outcomes": outcome_map,  # e.g., {"Yes": 62.0, "No": 38.0}
        "volume": m.get("volumeNum") or m.get("volume"),
        "volume_24h": m.get("volume24hr"),
        "liquidity": m.get("liquidityNum") or m.get("liquidity"),
        "active": m.get("active"),
        "closed": m.get("closed"),
        "end_date": m.get("endDate"),
        "last_trade_price": m.get("lastTradePrice"),
        "best_bid": m.get("bestBid"),
        "best_ask": m.get("bestAsk"),
    }


HOME_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Polymarket Wrapper</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#d4d4d8;font-family:system-ui,-apple-system,sans-serif;padding:24px;min-height:100vh}
.container{max-width:640px;margin:0 auto;animation:fadeIn 0.6s ease-out}
@keyframes fadeIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.title{font-family:monospace;font-size:28px;color:#6C5CE7;font-weight:700}
.health{font-family:monospace;font-size:13px;color:#555;display:flex;align-items:center;gap:6px}
.health .d{width:8px;height:8px;border-radius:50%;background:#555;transition:background .3s}
.health .d.on{background:#4CAF50}
.subtitle{color:#71717a;font-size:15px;margin-bottom:24px}
.card{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:16px;padding:20px;margin-bottom:16px}
.section-title{font-size:11px;text-transform:uppercase;letter-spacing:1.2px;color:#71717a;margin-bottom:16px;font-weight:600}
.market{background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:14px;margin-bottom:10px;animation:fadeIn 0.5s ease-out backwards}
.market:nth-child(2){animation-delay:0.05s}
.market:nth-child(3){animation-delay:0.1s}
.market:nth-child(4){animation-delay:0.15s}
.market:nth-child(5){animation-delay:0.2s}
.market:nth-child(6){animation-delay:0.25s}
.market-question{font-size:15px;margin-bottom:10px;line-height:1.4;color:#e4e4e7}
.outcome-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.outcome-label{font-family:monospace;font-size:13px;min-width:50px;color:#a1a1aa}
.outcome-bar{flex:1;height:24px;background:rgba(255,255,255,0.05);border-radius:6px;position:relative;overflow:hidden}
.outcome-fill{height:100%;background:linear-gradient(90deg,#6C5CE7,#8B7FE8);border-radius:6px;display:flex;align-items:center;justify-content:center;font-family:monospace;font-size:12px;font-weight:600;color:#fff;transition:width 0.4s ease}
.outcome-simple{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
.outcome-name{font-size:13px;color:#a1a1aa}
.outcome-pct{font-family:monospace;font-size:14px;font-weight:600;color:#6C5CE7}
.volume{font-size:12px;color:#52525b;margin-top:8px}
.search-box{display:flex;gap:8px;margin-bottom:12px}
.search-box input{flex:1;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:10px;padding:12px 16px;color:#e4e4e7;font-size:15px;outline:none;transition:border 0.2s}
.search-box input:focus{border-color:#6C5CE7}
.search-box input::placeholder{color:#52525b}
.search-btn{background:#6C5CE7;color:#fff;border:none;padding:12px 24px;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;transition:background 0.2s}
.search-btn:hover{background:#5a4ec4}
.try-queries{font-size:13px;color:#71717a}
.try-queries a{color:#6C5CE7;text-decoration:none;margin:0 4px}
.try-queries a:hover{text-decoration:underline}
.error{color:#ef4444;font-size:14px;margin-top:8px}
.loading{text-align:center;color:#71717a;padding:20px}
#results{margin-top:16px}
.result-item{background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:14px;margin-bottom:10px}
</style>
</head>
<body>
<div class="container">
<div class="header">
<div class="title">Polymarket</div>
<div class="health"><span class="d" id="dot"></span><span id="health-text">connecting...</span></div>
</div>
<div class="subtitle">Prediction markets \u2014 politics, crypto, sports, culture</div>
<div class="card">
<div class="section-title">TRENDING MARKETS</div>
<div id="trending-markets">
<div class="loading">Loading trending markets...</div>
</div>
</div>
<div class="card">
<div class="search-box">
<input type="text" id="search-input" placeholder="Bitcoin price">
<button class="search-btn" onclick="search()">\u2192 search</button>
</div>
<div class="try-queries">
Try: <a href="#" onclick="searchFor('election');return false">election</a> \u00b7
<a href="#" onclick="searchFor('crypto');return false">crypto</a> \u00b7
<a href="#" onclick="searchFor('Fed');return false">Fed</a> \u00b7
<a href="#" onclick="searchFor('sports');return false">sports</a>
</div>
<div id="results"></div>
</div>
</div>
<script>
async function fetchHealth(){
const t0=Date.now();
try{
await fetch('/health');
const ms=Date.now()-t0;
document.getElementById('dot').classList.add('on');
document.getElementById('health-text').textContent='online \\u00B7 '+ms+'ms';
}catch(e){
document.getElementById('health-text').textContent='offline';
}
}
async function fetchTrending(){
try{
const r=await fetch('/trending?limit=5');
const d=await r.json();
const container=document.getElementById('trending-markets');
if(!d.trending||d.trending.length===0){
container.innerHTML='<div class="loading">No trending markets available</div>';
return;
}
let html='';
d.trending.forEach(m=>{
html+='<div class="market">';
html+='<div class="market-question">'+escapeHtml(m.question||'Untitled Market')+'</div>';
const outcomes=m.outcomes||{};
const keys=Object.keys(outcomes);
if(keys.length===2&&(keys.includes('Yes')||keys.includes('No'))){
const yesP=outcomes.Yes||0;
const noP=outcomes.No||0;
html+='<div class="outcome-row">';
html+='<span class="outcome-label">Yes</span>';
html+='<div class="outcome-bar"><div class="outcome-fill" style="width:'+yesP+'%">'+yesP.toFixed(1)+'%</div></div>';
html+='</div>';
html+='<div class="outcome-row">';
html+='<span class="outcome-label">No</span>';
html+='<div class="outcome-bar"><div class="outcome-fill" style="width:'+noP+'%">'+noP.toFixed(1)+'%</div></div>';
html+='</div>';
}else{
const sorted=keys.map(k=>({name:k,pct:outcomes[k]})).sort((a,b)=>b.pct-a.pct).slice(0,3);
sorted.forEach(o=>{
html+='<div class="outcome-simple"><span class="outcome-name">'+escapeHtml(o.name)+'</span><span class="outcome-pct">'+o.pct.toFixed(1)+'%</span></div>';
});
}
if(m.volume_24h){
html+='<div class="volume">24h volume: $'+formatNumber(m.volume_24h)+'</div>';
}else if(m.volume){
html+='<div class="volume">Volume: $'+formatNumber(m.volume)+'</div>';
}
html+='</div>';
});
container.innerHTML=html;
}catch(e){
document.getElementById('trending-markets').innerHTML='<div class="error">Failed to load trending markets</div>';
}
}
function escapeHtml(t){
const d=document.createElement('div');
d.textContent=t;
return d.innerHTML;
}
function formatNumber(n){
if(n>=1e9)return(n/1e9).toFixed(2)+'B';
if(n>=1e6)return(n/1e6).toFixed(2)+'M';
if(n>=1e3)return(n/1e3).toFixed(1)+'K';
return n.toFixed(0);
}
async function search(){
const q=document.getElementById('search-input').value.trim();
if(!q)return;
const resultsDiv=document.getElementById('results');
resultsDiv.innerHTML='<div class="loading">Searching...</div>';
try{
const r=await fetch('/search?query='+encodeURIComponent(q)+'&limit=10');
const d=await r.json();
if(!d.results||d.results.length===0){
resultsDiv.innerHTML='<div class="loading">No results found</div>';
return;
}
let html='';
d.results.forEach(m=>{
html+='<div class="result-item">';
html+='<div class="market-question">'+escapeHtml(m.question||'Untitled')+'</div>';
const outcomes=m.outcomes||{};
const keys=Object.keys(outcomes);
if(keys.length===2&&(keys.includes('Yes')||keys.includes('No'))){
const yesP=outcomes.Yes||0;
const noP=outcomes.No||0;
html+='<div class="outcome-simple"><span class="outcome-name">Yes</span><span class="outcome-pct">'+yesP.toFixed(1)+'%</span></div>';
html+='<div class="outcome-simple"><span class="outcome-name">No</span><span class="outcome-pct">'+noP.toFixed(1)+'%</span></div>';
}else{
const sorted=keys.map(k=>({name:k,pct:outcomes[k]})).sort((a,b)=>b.pct-a.pct).slice(0,3);
sorted.forEach(o=>{
html+='<div class="outcome-simple"><span class="outcome-name">'+escapeHtml(o.name)+'</span><span class="outcome-pct">'+o.pct.toFixed(1)+'%</span></div>';
});
}
html+='</div>';
});
resultsDiv.innerHTML=html;
}catch(e){
resultsDiv.innerHTML='<div class="error">Search failed</div>';
}
}
function searchFor(term){
document.getElementById('search-input').value=term;
search();
}
document.getElementById('search-input').addEventListener('keypress',e=>{
if(e.key==='Enter')search();
});
fetchHealth();
fetchTrending();
</script>
</body>
</html>
"""


# ── Endpoints ────────────────────────────────────────────────────────────


@app.get("/")
async def root():
    return HTMLResponse(content=HOME_HTML)


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": _ts()}


@app.get("/markets")
async def list_markets(
    limit: int = Query(20, description="Max results", ge=1, le=100),
    active: bool = Query(True, description="Only show active markets"),
    order: str = Query("volume", description="Order by: volume, liquidity, end_date"),
):
    """List prediction markets sorted by volume."""
    params = {"limit": limit, "active": str(active).lower()}
    if order == "volume":
        params["order"] = "volumeNum"
        params["ascending"] = "false"
    elif order == "liquidity":
        params["order"] = "liquidityNum"
        params["ascending"] = "false"
    elif order == "end_date":
        params["order"] = "endDate"
        params["ascending"] = "true"

    data = await _gamma_request("/markets", params)
    if not isinstance(data, list):
        data = []

    markets = [_format_market(m) for m in data[:limit]]

    return {"markets": markets, "count": len(markets), "timestamp": _ts()}


@app.get("/market")
async def get_market(id: str = Query(..., description="Market ID or condition ID")):
    """Get a specific market by ID."""
    data = await _gamma_request(f"/markets/{id}")

    if isinstance(data, list):
        if not data:
            raise HTTPException(status_code=404, detail=f"Market {id} not found")
        m = data[0]
    else:
        m = data

    result = _format_market(m)
    result["description"] = m.get("description")
    result["timestamp"] = _ts()

    return result


@app.get("/search")
async def search_markets(
    query: str = Query(..., description="Search query (e.g., 'bitcoin', 'election', 'fed rate')"),
    limit: int = Query(20, ge=1, le=50),
):
    """Search prediction markets by keyword."""
    # Gamma API supports _q for text search
    data = await _gamma_request("/markets", {
        "_q": query,
        "limit": limit,
        "active": "true",
        "order": "volumeNum",
        "ascending": "false",
    })

    if not isinstance(data, list):
        data = []

    markets = [_format_market(m) for m in data[:limit]]

    return {"query": query, "results": markets, "count": len(markets), "timestamp": _ts()}


@app.get("/events")
async def list_events(
    limit: int = Query(20, ge=1, le=100),
    active: bool = Query(True, description="Only show active events"),
):
    """List events (each event groups related markets)."""
    params = {"limit": limit, "active": str(active).lower()}
    data = await _gamma_request("/events", params)

    if not isinstance(data, list):
        data = []

    events = []
    for e in data[:limit]:
        # Each event may have nested markets
        raw_markets = e.get("markets", [])
        markets_summary = []
        for m in raw_markets[:5]:
            markets_summary.append(_format_market(m))

        events.append({
            "id": e.get("id"),
            "title": e.get("title"),
            "slug": e.get("slug"),
            "description": e.get("description"),
            "active": e.get("active"),
            "closed": e.get("closed"),
            "volume": e.get("volume"),
            "liquidity": e.get("liquidity"),
            "start_date": e.get("startDate"),
            "end_date": e.get("endDate"),
            "market_count": len(raw_markets),
            "top_markets": markets_summary,
        })

    return {"events": events, "count": len(events), "timestamp": _ts()}


@app.get("/trending")
async def get_trending(limit: int = Query(10, ge=1, le=50)):
    """Get highest-volume active markets (trending)."""
    data = await _gamma_request("/markets", {
        "limit": limit,
        "active": "true",
        "order": "volume24hr",
        "ascending": "false",
    })

    if not isinstance(data, list):
        data = []

    markets = [_format_market(m) for m in data[:limit]]

    return {"trending": markets, "count": len(markets), "timestamp": _ts()}
