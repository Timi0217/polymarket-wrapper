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
body{background:#0a0a0a;color:#fff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:40px 24px;min-height:100vh}
.container{max-width:600px;margin:0 auto;animation:fadeIn 0.6s ease-out}
@keyframes fadeIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.header{display:flex;align-items:center;gap:16px;margin-bottom:32px}
.icon-block{width:48px;height:48px;border-radius:14px;background:linear-gradient(135deg,#2563EB,#1D4ED8);display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:700;color:#fff;flex-shrink:0}
.header-content{flex:1}
.title{font-size:24px;font-weight:700;color:#fff;margin-bottom:2px}
.subtitle{font-size:13px;color:#555;line-height:1.4}
.health-badge{display:flex;align-items:center;gap:6px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:20px;padding:6px 12px;font-size:12px;color:#555;margin-left:auto;white-space:nowrap}
.health-dot{width:6px;height:6px;border-radius:50%;background:#555;transition:background .3s}
.health-dot.on{background:#22C55E}
.section-label{font-size:11px;text-transform:uppercase;letter-spacing:2px;color:#555;margin-bottom:16px;font-weight:600}
.categories{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:32px}
.category-chip{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:20px;padding:5px 14px;font-size:12px;color:#555;cursor:pointer;transition:all 0.2s}
.category-chip:hover{border-color:rgba(37,99,235,0.4);color:#2563EB}
.hero-card{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:24px;margin-bottom:16px;animation:fadeIn 0.5s ease-out backwards}
.hero-question{font-size:17px;font-weight:700;margin-bottom:20px;line-height:1.4;color:#fff}
.hero-outcomes{display:flex;flex-direction:column;gap:10px;margin-bottom:16px}
.hero-outcome-row{display:flex;align-items:center;gap:10px}
.hero-outcome-label{font-size:13px;font-weight:600;min-width:40px;padding:4px 10px;border-radius:20px;text-align:center}
.hero-outcome-label.yes{background:rgba(34,197,94,0.15);color:#22C55E}
.hero-outcome-label.no{background:rgba(239,68,68,0.15);color:#EF4444}
.hero-outcome-bar{flex:1;height:28px;background:rgba(255,255,255,0.04);border-radius:20px;position:relative;overflow:hidden}
.hero-outcome-fill{height:100%;border-radius:20px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff;transition:width 0.5s ease;font-family:monospace}
.hero-outcome-fill.yes{background:#22C55E}
.hero-outcome-fill.no{background:#EF4444}
.volume-badge{display:inline-block;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);color:#888;padding:5px 12px;border-radius:20px;font-size:11px;font-weight:600;font-family:monospace}
.compact-markets{display:flex;flex-direction:column;gap:10px;margin-bottom:32px}
.compact-card{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:18px;animation:fadeIn 0.5s ease-out backwards;transition:all 0.2s}
.compact-card:hover{background:rgba(255,255,255,0.05);border-color:rgba(255,255,255,0.1)}
.compact-card:nth-child(2){animation-delay:0.05s}
.compact-card:nth-child(3){animation-delay:0.1s}
.compact-card:nth-child(4){animation-delay:0.15s}
.compact-card:nth-child(5){animation-delay:0.2s}
.compact-question{font-size:14px;font-weight:600;margin-bottom:12px;line-height:1.4;color:#fff}
.inline-outcomes{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.outcome-pill{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:20px;font-size:12px}
.outcome-pill.yes{color:#22C55E}
.outcome-pill.no{color:#888}
.outcome-pill-label{font-weight:600}
.outcome-pill-pct{font-family:monospace;font-weight:700}
.volume-line{font-size:11px;color:#555;font-family:monospace}
.volume-line .amount{color:#888;font-weight:600}
.search-card{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:24px;margin-bottom:32px}
.search-box{display:flex;gap:8px;margin-bottom:16px}
.search-box input{flex:1;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:12px 16px;color:#fff;font-size:14px;outline:none;transition:all 0.2s}
.search-box input:focus{border-color:rgba(37,99,235,0.4);background:rgba(255,255,255,0.06)}
.search-box input::placeholder{color:#555}
.search-btn{background:linear-gradient(135deg,#2563EB,#1D4ED8);color:#fff;border:none;padding:12px 24px;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;transition:opacity 0.2s}
.search-btn:hover{opacity:0.9}
.quick-links{display:flex;gap:8px;flex-wrap:wrap}
.quick-link{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:20px;padding:5px 14px;font-size:12px;color:#555;cursor:pointer;transition:all 0.2s;text-decoration:none}
.quick-link:hover{border-color:rgba(37,99,235,0.4);color:#2563EB}
.error{color:#EF4444;font-size:13px;margin-top:12px}
.loading{text-align:center;color:#555;padding:20px;font-size:13px}
#results{margin-top:20px}
.result-item{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:16px;margin-bottom:10px}
</style>
</head>
<body>
<div class="container">
<div class="header">
<div class="icon-block">P</div>
<div class="header-content">
<div class="title">Polymarket</div>
<div class="subtitle">Prediction markets — politics, crypto, sports, culture</div>
</div>
<div class="health-badge">
<span class="health-dot" id="dot"></span>
<span id="health-text">connecting...</span>
</div>
</div>
<div class="section-label">TRENDING MARKETS</div>
<div id="hero-container"></div>
<div id="compact-container" class="compact-markets"></div>
<div id="hot-container"></div>
<div class="categories">
<div class="category-chip">Trending</div>
<div class="category-chip">Politics</div>
<div class="category-chip">Crypto</div>
<div class="category-chip">Sports</div>
<div class="category-chip">Finance</div>
<div class="category-chip">Tech</div>
<div class="category-chip">Culture</div>
</div>
<div class="search-card">
<div class="section-label" style="margin-bottom:12px">SEARCH MARKETS</div>
<div class="search-box">
<input type="text" id="search-input" placeholder="Search markets... (e.g. Bitcoin, election, Fed rate)">
<button class="search-btn" onclick="search()">Search</button>
</div>
<div class="quick-links">
<a href="#" class="quick-link" onclick="searchFor('election');return false">election</a>
<a href="#" class="quick-link" onclick="searchFor('crypto');return false">crypto</a>
<a href="#" class="quick-link" onclick="searchFor('Fed');return false">Fed</a>
<a href="#" class="quick-link" onclick="searchFor('sports');return false">sports</a>
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
document.getElementById('health-text').textContent='online · '+ms+'ms';
}catch(e){
document.getElementById('health-text').textContent='offline';
}
}
async function fetchTrending(){
try{
const r=await fetch('/trending?limit=8');
const d=await r.json();
if(!d.trending||d.trending.length===0){
document.getElementById('hero-container').innerHTML='<div class="loading">No trending markets available</div>';
return;
}
const markets=d.trending;
if(markets.length>0){
renderHeroCard(markets[0]);
}
if(markets.length>1){
renderCompactCards(markets.slice(1,5));
}
if(markets.length>5){
renderHotMarkets(markets.slice(5,8));
}
}catch(e){
document.getElementById('hero-container').innerHTML='<div class="error">Failed to load trending markets</div>';
}
}
function renderHeroCard(m){
const outcomes=m.outcomes||{};
const keys=Object.keys(outcomes);
let html='<div class="hero-card">';
html+='<div class="hero-question">'+escapeHtml(m.question||'Untitled Market')+'</div>';
if(keys.length===2&&(keys.includes('Yes')||keys.includes('No'))){
const yesP=outcomes.Yes||0;
const noP=outcomes.No||0;
const mainP=yesP>=50?yesP:noP;
const mainLabel=yesP>=50?'Yes':'No';
const colorClass=yesP>=50?'yes-color':'no-color';
html+='<div class="hero-outcomes">';
html+='<div class="hero-outcome-row">';
html+='<div class="hero-outcome-label yes">Yes</div>';
html+='<div class="hero-outcome-bar"><div class="hero-outcome-fill yes" style="width:'+yesP+'%">'+yesP.toFixed(1)+'%</div></div>';
html+='</div>';
html+='<div class="hero-outcome-row">';
html+='<div class="hero-outcome-label no">No</div>';
html+='<div class="hero-outcome-bar"><div class="hero-outcome-fill no" style="width:'+noP+'%">'+noP.toFixed(1)+'%</div></div>';
html+='</div>';
html+='</div>';
}else{
const sorted=keys.map(k=>({name:k,pct:outcomes[k]})).sort((a,b)=>b.pct-a.pct);
html+='<div class="hero-outcomes">';
sorted.slice(0,3).forEach(o=>{
html+='<div class="hero-outcome-row">';
html+='<div class="hero-outcome-label yes">'+escapeHtml(o.name)+'</div>';
html+='<div class="hero-outcome-bar"><div class="hero-outcome-fill yes" style="width:'+o.pct+'%">'+o.pct.toFixed(1)+'%</div></div>';
html+='</div>';
});
html+='</div>';
}
if(m.volume_24h){
html+='<div class="volume-badge">24h: $'+formatNumber(m.volume_24h)+'</div>';
}else if(m.volume){
html+='<div class="volume-badge">Vol: $'+formatNumber(m.volume)+'</div>';
}
html+='</div>';
document.getElementById('hero-container').innerHTML=html;
}
function renderCompactCards(markets){
let html='';
markets.forEach(m=>{
html+='<div class="compact-card">';
html+='<div class="compact-question">'+escapeHtml(m.question||'Untitled Market')+'</div>';
const outcomes=m.outcomes||{};
const keys=Object.keys(outcomes);
if(keys.length===2&&(keys.includes('Yes')||keys.includes('No'))){
const yesP=outcomes.Yes||0;
const noP=outcomes.No||0;
html+='<div class="inline-outcomes">';
html+='<div class="outcome-pill yes"><span class="outcome-pill-label">Yes</span><span class="outcome-pill-pct">'+yesP.toFixed(1)+'%</span></div>';
html+='<div class="outcome-pill no"><span class="outcome-pill-label">No</span><span class="outcome-pill-pct">'+noP.toFixed(1)+'%</span></div>';
html+='</div>';
}else{
const sorted=keys.map(k=>({name:k,pct:outcomes[k]})).sort((a,b)=>b.pct-a.pct).slice(0,3);
html+='<div class="inline-outcomes">';
sorted.forEach(o=>{
html+='<div class="outcome-pill yes"><span class="outcome-pill-label">'+escapeHtml(o.name)+'</span><span class="outcome-pill-pct">'+o.pct.toFixed(1)+'%</span></div>';
});
html+='</div>';
}
if(m.volume_24h){
html+='<div class="volume-line">24h: <span class="amount">$'+formatNumber(m.volume_24h)+'</span></div>';
}else if(m.volume){
html+='<div class="volume-line">Vol: <span class="amount">$'+formatNumber(m.volume)+'</span></div>';
}
html+='</div>';
});
document.getElementById('compact-container').innerHTML=html;
}
function renderHotMarkets(markets){
let html='';
markets.forEach((m,idx)=>{
html+='<div class="hot-item">';
html+='<div class="hot-number">'+(idx+1)+'</div>';
html+='<div class="hot-content">';
html+='<div class="hot-question">'+escapeHtml(m.question||'Untitled Market')+'</div>';
const vol=m.volume_24h||m.volume;
if(vol){
html+='<div class="hot-volume">Volume: <span class="amount">$'+formatNumber(vol)+'</span></div>';
}
html+='</div>';
html+='</div>';
});
document.getElementById('hot-container').innerHTML=html;
}
function escapeHtml(t){
const d=document.createElement('div');
d.textContent=t;
return d.innerHTML;
}
function formatNumber(n){
if(n>=1e9)return(n/1e9).toFixed(1)+'B';
if(n>=1e6)return(n/1e6).toFixed(1)+'M';
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
html+='<div class="compact-question">'+escapeHtml(m.question||'Untitled')+'</div>';
const outcomes=m.outcomes||{};
const keys=Object.keys(outcomes);
if(keys.length===2&&(keys.includes('Yes')||keys.includes('No'))){
const yesP=outcomes.Yes||0;
const noP=outcomes.No||0;
html+='<div class="inline-outcomes">';
html+='<div class="outcome-pill yes"><span class="outcome-pill-label">Yes</span><span class="outcome-pill-pct">'+yesP.toFixed(1)+'%</span></div>';
html+='<div class="outcome-pill no"><span class="outcome-pill-label">No</span><span class="outcome-pill-pct">'+noP.toFixed(1)+'%</span></div>';
html+='</div>';
}else{
const sorted=keys.map(k=>({name:k,pct:outcomes[k]})).sort((a,b)=>b.pct-a.pct).slice(0,3);
html+='<div class="inline-outcomes">';
sorted.forEach(o=>{
html+='<div class="outcome-pill yes"><span class="outcome-pill-label">'+escapeHtml(o.name)+'</span><span class="outcome-pill-pct">'+o.pct.toFixed(1)+'%</span></div>';
});
html+='</div>';
}
const vol=m.volume_24h||m.volume;
if(vol){
html+='<div class="volume-line">Vol: <span class="amount">$'+formatNumber(vol)+'</span></div>';
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
