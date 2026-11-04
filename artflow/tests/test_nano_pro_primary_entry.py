from unittest.mock import AsyncMock

from api import image_service, neironych_image_adapter, nexus_image_adapter


async def test_nano_pro_prefers_neironych(monkeypatch):
    monkeypatch.setattr(neironych_image_adapter, '_generate_image', AsyncMock(return_value='https://example.test/result.png'))
    monkeypatch.setattr(nexus_image_adapter, 'create_nexus_image_task', AsyncMock(return_value='nexus:fallback'))
    result = await image_service.generate_image(image_service.ImageModel.NANO_BANANA_PRO, 'A cup',
        aspect_ratio='1:1', quality='2K', primary_provider='neironych',
        request_id='d9307625-cff7-4341-8280-5a778154ccef')
    assert result.provider == 'neironych'
