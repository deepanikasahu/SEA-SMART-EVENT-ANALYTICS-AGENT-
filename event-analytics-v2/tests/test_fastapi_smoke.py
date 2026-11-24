"""
FastAPI Server Live Smoke Test
Tests POST /analyze-events and GET /explain-club/{club_name} and prints formatted JSON.
"""

import sys
import os
import json

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _V2_ROOT not in sys.path:
    sys.path.insert(0, _V2_ROOT)

from fastapi.testclient import TestClient
from api.server import app

client = TestClient(app)

def run_smoke_test():
    print("=" * 80)
    print("  FASTAPI LIVE SMOKE TEST")
    print("=" * 80)

    # 1. Health check
    print("\n1. GET /health")
    res = client.get("/health")
    print(f"Status: {res.status_code}")
    print(json.dumps(res.json(), indent=2))
    assert res.status_code == 200

    # 2. POST /analyze-events
    print("\n2. POST /analyze-events")
    payload = {
        "query": "Analyze all technical events conducted last semester and tell me which clubs performed the best.",
        "provider": "mock"
    }
    res = client.post("/analyze-events", json=payload)
    print(f"Status: {res.status_code}")
    data = res.json()
    print("Response Summary:")
    print(f"  - Status: {data.get('status')}")
    print(f"  - Events Count: {data.get('in_scope_events_count')}")
    print(f"  - Total Clubs Ranked: {len(data.get('ranked_clubs', []))}")
    print(f"  - Top Club: {data.get('ranked_clubs', [{}])[0].get('club_name')} (#{data.get('ranked_clubs', [{}])[0].get('rank')})")
    print(f"  - Duration: {data.get('total_duration_seconds')}s")
    print(f"  - Version: {data.get('version')}")
    assert res.status_code == 200
    assert len(data.get("ranked_clubs", [])) > 0

    # 3. GET /explain-club/{name}
    top_club = data["ranked_clubs"][0]["club_name"]
    print(f"\n3. GET /explain-club/{top_club}")
    res = client.get(f"/explain-club/{top_club}?provider=mock")
    print(f"Status: {res.status_code}")
    exp_data = res.json()
    print(json.dumps(exp_data, indent=2))
    assert res.status_code == 200
    assert exp_data.get("club_name") == top_club

    print("\n[OK] All FastAPI endpoints passed live smoke test successfully!")

if __name__ == "__main__":
    run_smoke_test()
