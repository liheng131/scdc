import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Need to init the app first
from app.main import app
import asyncio
from httpx import ASGITransport, AsyncClient

async def main():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/api/v1/reports")
        await client.get("/api/v1/metrics")
        await client.get("/api/v1/metrics-json/json")

asyncio.run(main())

from prometheus_client import REGISTRY
print("=== HTTP-related samples in REGISTRY ===")
for metric_family in REGISTRY.collect():
    for s in metric_family.samples:
        if "http" in s.name.lower() or "request" in s.name.lower():
            print(f"  name={s.name!r}, labels={s.labels}, value={s.value}")
