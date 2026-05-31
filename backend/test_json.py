import asyncio, httpx, json, re

async def test():
    client = httpx.AsyncClient(timeout=300)
    prompt = """You are a market analyst. Analyze the following source and output ONLY valid JSON (no markdown code blocks, no extra text).

Source:
- Title: "2025 Global AI Chip Market Report"
- Content: The global AI chip market is projected to reach $92 billion in 2025 with 25% YoY growth. NVIDIA maintains dominant position with approximately 80% market share. AMD and Intel are aggressively competing with MI400 and Gaudi 4 products. China's domestic AI chip market sees rapid growth with Huawei Ascend and Cambricon leading, achieving 15% localization rate.

Output format (valid JSON object, no markdown):
{
  "summary": "comprehensive analysis summary in 2-3 sentences",
  "insights": [
    {
      "conclusion": "one-sentence headline",
      "analysis": "detailed 2-3 sentence analysis",
      "dimension": "one of: industry_trends, competitive_landscape"
    }
  ]
}"""

    payload = {
        'model': 'qwen3-vl-32b-instruct-gguf',
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.5,
        'max_tokens': 2048,
    }
    print('Sending prompt with JSON request...')
    r = await client.post(
        'http://120.79.96.231:6003/v1/chat/completions',
        json=payload,
        headers={'Authorization': 'Bearer gpustack_35d38e92e85f9689_acbc5009938cc7513ae70f7d71eaf7ba', 'Content-Type': 'application/json'}
    )
    print(f'Status: {r.status_code}')
    data = r.json()
    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    print(f'Content length: {len(content)}')
    print(f'Raw content (first 2000 chars): {repr(content[:2000])}')
    
    if content:
        cleaned = content.strip()
        if cleaned.startswith('```json'):
            cleaned = cleaned[7:]
        if cleaned.startswith('```'):
            cleaned = cleaned[3:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        try:
            parsed = json.loads(cleaned)
            print(f'SUCCESS - Parsed JSON keys: {list(parsed.keys())}')
        except json.JSONDecodeError as e:
            print(f'JSON parse failed: {e}')
            print(f'Cleaned content: {cleaned[:500]}')
    else:
        print('ERROR: Empty response!')
    
    await client.aclose()

asyncio.run(test())