import asyncio

from sqlalchemy import select

from db.models import ModelCost
from db.session import AsyncSessionLocal

FRIENDLY = {
    'grok-imagine/text-to-image': '⚡ Grok Imagine',
    'grok-imagine/image-to-image': '⚡ Grok Imagine Edit',
    'wan/2-7-image-pro': '🌊 WAN Pro',
    'qwen/text-to-image': '🟣 Qwen',
    'qwen/image-to-image': '🟣 Qwen Edit',
    'qwen/image-edit': '🟣 Qwen Edit Pro',
    'qwen2/text-to-image': '🟣 Qwen 2',
    'qwen2/image-edit': '🟣 Qwen 2 Edit',
    'gpt-image-2-text-to-image': '🤖 GPT Image 2',
    'gpt-image-2-image-to-image': '🤖 GPT Image 2 Edit',
    'kling-2.6/text-to-video': '⚙️ Kling 2.6',
    'kling-2.6/image-to-video': '⚙️ Kling 2.6 Animate',
    'kling-2.6/motion-control': '🕺 Kling Motion',
    'kling-3.0/video': '⚡ Kling 3.0',
    'kling-3.0/motion-control': '🕺 Kling 3.0 Motion',
    'wan/2-7-text-to-video': '🌊 WAN Video',
    'wan/2-7-image-to-video': '🌊 WAN Animate',
    'bytedance/seedance-2': '🌱 Seedance 2',
    'bytedance/seedance-2-fast': '🌱 Seedance 2 Fast',
    'grok-imagine/text-to-video': '⚡ Grok Video',
    'grok-imagine/image-to-video': '⚡ Grok Animate',
    'happyhorse/text-to-video': '🐎 HappyHorse Video',
    'happyhorse/image-to-video': '🐎 HappyHorse Animate',
    'veo3_fast': '🎬 Veo Fast',
    'veo3': '🎬 Veo',
    'veo3_lite': '🎬 Veo Lite',
    'suno/v4.5': '🎵 Suno',
    'midjourney-imagine': '🖌️ Midjourney Imagine',
    'midjourney-action': '🖌️ Midjourney Action',
    'midjourney-blend': '🖼️ Midjourney Blend',
    'midjourney-describe': '🔍 Midjourney Describe',
    'midjourney-video': '🎞️ Midjourney Video',
}

async def main():
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(ModelCost))).scalars().all()
        changed = []
        for row in rows:
            new_name = FRIENDLY.get(row.model_key)
            if new_name and row.display_name != new_name:
                changed.append((row.model_key, row.display_name, new_name))
                row.display_name = new_name
        await session.commit()
        print('changed', len(changed))
        for key, _old, new in changed:
            print(key, '=>', new)

asyncio.run(main())
