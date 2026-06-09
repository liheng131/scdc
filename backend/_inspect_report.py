"""查最新一份"2025年AI芯片"报告，看看实际乱码长什么样"""
import asyncio
from sqlalchemy import select
from app.core.db import async_session_factory
from app.models.report import Report
from app.models.task import Task

async def main():
    async with async_session_factory() as session:
        stmt = select(Report).where(Report.title.like('%AI芯片%')).order_by(Report.created_at.desc()).limit(1)
        r = (await session.execute(stmt)).scalars().first()
        if not r:
            print("no report found")
            return
        content = r.content_markdown or ''
        print(f"Report id={r.id} length={len(content)}")
        # 1) 提取两张图片之间的非图片内容，看是否有 LLM 输出的 base64 噪音
        import re
        img_positions = [m.start() for m in re.finditer(r'!\[[^\]]*\]\(data:image/png;base64,', content)]
        if len(img_positions) >= 2:
            seg_start = img_positions[0]
            # 找第一张图片的结尾
            first_img_end = content.find(')', seg_start)
            seg_end = img_positions[1] - 1
            segment = content[first_img_end+1:seg_end]
            print(f"\n[1] 第一张图片之后到第二张图片之前 ({first_img_end+1}-{seg_end}, len={len(segment)}):")
            print(segment[:3000])
            print(f"\n... 后续 {len(segment)-3000} 字符 ...")
            print(segment[-500:])
        # 2) 看 LLM 输出的"裸" base64 段（不在 data: URI 中）
        # 把所有 data:image/... 块先剔除
        clean = re.sub(r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+', '', content)
        b64_in_clean = list(re.finditer(r'[A-Za-z0-9+/=]{120,}', clean))
        print(f"\n[2] 图片之外的长 base64-like 段: {len(b64_in_clean)} 个")
        for m in b64_in_clean[:5]:
            s, e = m.start(), m.end()
            ctx = clean[max(0, s-50):e+50].replace('\n', '↵')
            print(f"    pos={s:5d} len={e-s:5d} ctx={ctx[:200]!r}")

asyncio.run(main())
