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
body{background:#131823;color:#fff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;padding:32px 24px;min-height:100vh}
.container{max-width:1100px;margin:0 auto;animation:fadeIn 0.6s ease-out}
@keyframes fadeIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.title{font-family:monospace;font-size:28px;color:#2563EB;font-weight:700}
.health{font-family:monospace;font-size:13px;color:#8B949E;display:flex;align-items:center;gap:6px}
.health .d{width:8px;height:8px;border-radius:50%;background:#555;transition:background .3s}
.health .d.on{background:#22C55E}
.subtitle{color:#8B949E;font-size:15px;margin-bottom:20px}
.categories{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:32px}
.category-pill{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.08);border-radius:20px;padding:6px 14px;font-size:13px;color:#8B949E;cursor:pointer;transition:all 0.2s}
.category-pill:hover{background:rgba(255,255,255,0.1);color:#fff}
.section-title{font-size:12px;text-transform:uppercase;letter-spacing:1.5px;color:#8B949E;margin-bottom:20px;font-weight:600}
.hero-card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:28px;margin-bottom:20px;animation:fadeIn 0.5s ease-out backwards}
.hero-question{font-size:18px;font-weight:700;margin-bottom:20px;line-height:1.4;color:#fff}
.hero-probability{font-size:36px;font-weight:700;margin-bottom:20px}
.hero-probability.yes-color{color:#22C55E}
.hero-probability.no-color{color:#F43F5E}
.hero-outcomes{display:flex;flex-direction:column;gap:12px;margin-bottom:16px}
.hero-outcome-row{display:flex;align-items:center;gap:12px}
.hero-outcome-label{font-size:14px;font-weight:600;min-width:50px}
.hero-outcome-label.yes{color:#22C55E}
.hero-outcome-label.no{color:#EF4444}
.hero-outcome-bar{flex:1;height:32px;background:rgba(255,255,255,0.05);border-radius:8px;position:relative;overflow:hidden}
.hero-outcome-fill{height:100%;border-radius:8px;display:flex;align-items:center;justify-content:center;font-family:monospace;font-size:14px;font-weight:600;color:#fff;transition:width 0.5s ease}
.hero-outcome-fill.yes{background:#22C55E}
.hero-outcome-fill.no{background:#EF4444}
.volume-badge{display:inline-block;background:rgba(244,63,94,0.15);color:#F43F5E;padding:6px 12px;border-radius:8px;font-size:13px;font-weight:600;font-family:monospace}
.compact-markets{display:flex;flex-direction:column;gap:12px;margin-bottom:32px}
.compact-card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:18px;animation:fadeIn 0.5s ease-out backwards;transition:all 0.2s}
.compact-card:hover{background:rgba(255,255,255,0.06);border-color:rgba(255,255,255,0.12)}
.compact-card:nth-child(2){animation-delay:0.05s}
.compact-card:nth-child(3){animation-delay:0.1s}
.compact-card:nth-child(4){animation-delay:0.15s}
.compact-card:nth-child(5){animation-delay:0.2s}
.compact-question{font-size:15px;font-weight:600;margin-bottom:12px;line-height:1.4;color:#fff}
.inline-outcomes{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.outcome-pill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;background:rgba(255,255,255,0.05);border-radius:6px;font-size:13px}
.outcome-pill.yes{color:#22C55E}
.outcome-pill.no{color:#8B949E}
.outcome-pill-label{font-weight:600}
.outcome-pill-pct{font-family:monospace;font-weight:700}
.volume-line{font-size:12px;color:#8B949E;font-family:monospace}
.volume-line .amount{color:#F43F5E;font-weight:600}
.hot-section{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:24px;margin-bottom:32px}
.hot-item{padding:14px 0;border-bottom:1px solid rgba(255,255,255,0.06);display:flex;gap:16px;align-items:flex-start}
.hot-item:last-child{border-bottom:none}
.hot-number{font-size:18px;font-weight:700;color:#2563EB;min-width:30px;font-family:monospace}
.hot-content{flex:1}
.hot-question{font-size:14px;font-weight:600;margin-bottom:6px;color:#fff;line-height:1.4}
.hot-volume{font-size:13px;color:#8B949E}
.hot-volume .amount{color:#F43F5E;font-weight:700}
.search-section{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:24px}
.search-box{display:flex;gap:10px;margin-bottom:14px}
.search-box input{flex:1;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:10px;padding:14px 18px;color:#fff;font-size:15px;outline:none;transition:all 0.2s}
.search-box input:focus{border-color:#2563EB;background:rgba(255,255,255,0.08)}
.search-box input::placeholder{color:#8B949E}
.search-btn{background:#2563EB;color:#fff;border:none;padding:14px 28px;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;transition:background 0.2s}
.search-btn:hover{background:#1D4ED8}
.try-queries{font-size:13px;color:#8B949E}
.try-queries a{color:#2563EB;text-decoration:none;margin:0 6px}
.try-queries a:hover{text-decoration:underline}
.error{color:#EF4444;font-size:14px;margin-top:12px}
.loading{text-align:center;color:#8B949E;padding:24px}
#results{margin-top:20px}
.result-item{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:16px;margin-bottom:12px}
</style>
</head>
<body>
<div class="container">
<div class="header">
<div class="title">Polymarket</div>
<div class="health"><span class="d" id="dot"></span><span id="health-text">connecting...</span></div>
</div>
<div class="subtitle">Prediction markets — politics, crypto, sports, culture</div>
<div class="categories">
<div class="category-pill">Trending</div>
<div class="category-pill">Politics</div>
<div class="category-pill">Crypto</div>
<div class="category-pill">Sports</div>
<div class="category-pill">Finance</div>
<div class="category-pill">Tech</div>
<div class="category-pill">Culture</div>
</div>
<div class="section-title">TRENDING NOW</div>
<div id="hero-container"></div>
<div id="compact-container" class="compact-markets"></div>
<div class="hot-section">
<div class="section-title" style="margin-bottom:16px">HOT MARKETS</div>
<div id="hot-container"></div>
</div>
<div class="search-section">
<div class="search-box">
<input type="text" id="search-input" placeholder="Search markets... (e.g. Bitcoin, election, Fed rate)">
<button class="search-btn" onclick="search()">Search</button>
</div>
<div class="try-queries">
Quick links: <a href="#" onclick="searchFor('election');return false">election</a> ·
<a href="#" onclick="searchFor('crypto');return false">crypto</a> ·
<a href="#" onclick="searchFor('Fed');return false">Fed</a> ·
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
document.getElementById('health-text').textContent='● online · '+ms+'ms';
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
html+='<div class="hero-probability '+colorClass+'">'+mainP.toFixed(1)+'%</div>';
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
if(sorted.length>0){
html+='<div class="hero-probability yes-color">'+sorted[0].pct.toFixed(1)+'%</div>';
}
html+='<div class="hero-outcomes">';
sorted.slice(0,3).forEach(o=>{
html+='<div class="hero-outcome-row">';
html+='<div class="hero-outcome-label">'+escapeHtml(o.name)+'</div>';
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
