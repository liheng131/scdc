import asyncio
import httpx
import json

async def test():
    client = httpx.AsyncClient(timeout=180)
    payload = {
        'model': 'qwen3-vl-32b-instruct-gguf',
        'messages': [{'role': 'user', 'content': 'Return exactly this JSON: {"summary": "test analysis", "insights": [{"conclusion": "Market is growing", "analysis": "The AI chip market shows significant growth.", "evidence": ["uri1"], "confidence": 0.85, "dimension": "test"}]}'}],
        'temperature': 0.5,
        'response_format': {'type': 'json_object'},
    }
    
    print("Sending request...")
    r = await client.post(
        'http://120.79.96.231:6003/v1/chat/completions',
        json=payload,
        headers={
            'Authorization': 'Bearer gpustack_35d38e92e85f9689_acbc5009938cc7513ae70f7d71eaf7ba',
            'Content-Type': 'application/json',
        }
    )
    print(f"Status: {r.status_code}")
    text = r.text
    print(f"Response length: {len(text)}")
    print(f"Response: {text[:2000]}")
    
    data = r.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    print(f"\nParsed content: {content}")
    parsed = json.loads(content)
    print(f"Parsed JSON keys: {list(parsed.keys())}")
    await client.aclose()

asyncio.run(test())