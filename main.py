import os
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
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


# ── Endpoints ────────────────────────────────────────────────────────────


@app.get("/")
async def root():
    return {
        "name": "Polymarket Wrapper",
        "description": "Prediction market data from Polymarket — event probabilities, trading volumes, and market outcomes for politics, crypto, sports, culture, and more",
        "endpoints": [
            {"path": "/markets?limit=20", "description": "List active prediction markets"},
            {"path": "/market?id=MARKET_ID", "description": "Get market by ID"},
            {"path": "/search?query=fed rate cut", "description": "Search markets by keyword"},
            {"path": "/events?limit=20", "description": "List events"},
            {"path": "/trending", "description": "Get trending/high-volume markets"},
            {"path": "/health", "description": "Health check"},
        ],
    }


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
