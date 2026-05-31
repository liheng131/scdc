import asyncio, sys, httpx
sys.path.insert(0, '/app')

async def test():
    from app.core.db import async_session_factory
    from sqlalchemy import select
    from app.models.ai_model_config import AiModelConfig
    from app.core.security import decrypt_api_key
    
    async with async_session_factory() as session:
        result = await session.execute(select(AiModelConfig).where(AiModelConfig.model_type == 'rerank', AiModelConfig.is_default == True))
        config = result.scalar_one_or_none()
        if not config:
            print('No default rerank config found')
            return
        
        api_key = decrypt_api_key(config.api_key) if config.api_key else ''
        base_url = config.base_url.rstrip('/')
        model = config.model_name
        
        print(f'Testing rerank: provider={config.provider}, model={model}')
        print(f'URL: {base_url}/v1/rerank')
        
        headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
        payload = {
            'model': model,
            'query': '人工智能市场发展趋势',
            'documents': [
                '2024年全球人工智能市场规模达到500亿美元',
                '机器学习在医疗诊断中的应用越来越广泛',
                '自动驾驶技术面临法规和伦理挑战'
            ]
        }
        
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            resp = await client.post(f'{base_url}/v1/rerank', json=payload, headers=headers)
            print(f'Status: {resp.status_code}')
            data = resp.json()
            print(f'Response: {data}')
            if resp.status_code == 200:
                results = data.get('results', [])
                print(f'\nRerank results ({len(results)} items):')
                for r in results:
                    idx = r.get('index')
                    score = r.get('relevance_score', r.get('score'))
                    doc = r.get('document', '')[:50]
                    print(f'  index={idx}, score={score}, text={doc}')
                print('\nRerank API test PASSED!')
            else:
                print(f'\nRerank API test FAILED: {resp.text}')

asyncio.run(test())
