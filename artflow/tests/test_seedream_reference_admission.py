import asyncio
from unittest.mock import AsyncMock

import pytest

from api import image_service, public_files


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["seedream/5-pro-image-to-image", "seedream/4.5-edit"])
async def test_unreachable_external_reference_never_submits_paid_task(monkeypatch, model):
    upload = AsyncMock(side_effect=ValueError("remote upload rejected"))
    create = AsyncMock(return_value={"data": {"taskId": "should-not-submit"}})
    monkeypatch.setattr(image_service.kieai_client, "upload_reference_image_url", upload)
    monkeypatch.setattr(image_service.kieai_client, "create_task", create)

    with pytest.raises(ValueError, match="[Зз]агруз"):
        await image_service.generate_image(
            image_service.ImageModel(model), "edit the image", image_url="https://old-media.test/static/upload/missing.jpg",
        )

    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_local_reference_never_submits_paid_task(monkeypatch, tmp_path):
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    create = AsyncMock(return_value={"data": {"taskId": "should-not-submit"}})
    monkeypatch.setattr(image_service.kieai_client, "create_task", create)

    with pytest.raises(ValueError, match="[Зз]агруз"):
        await image_service.generate_image(
            image_service.ImageModel.SEEDREAM_5_PRO_I2I, "edit the image",
            image_url="https://example.test/static/upload/missing.jpg",
        )

    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_accessible_external_seedream_references_are_staged_in_order(monkeypatch):
    upload = AsyncMock(side_effect=["https://kie-files.test/first.png", "https://kie-files.test/second.png"])
    create = AsyncMock(return_value={"data": {"taskId": "staged-task"}})
    monkeypatch.setattr(image_service.kieai_client, "upload_reference_image_url", upload)
    monkeypatch.setattr(public_files, "download_public_url", AsyncMock(side_effect=AssertionError("APIX must not fetch remote references")))
    monkeypatch.setattr(image_service.kieai_client, "create_task", create)

    result = await image_service.generate_image(
        image_service.ImageModel.SEEDREAM_5_PRO_T2I, "edit both images",
        image_url=["https://external.test/one", "https://external.test/two"],
    )

    assert result.task_id == "staged-task"
    assert create.await_args.args[0]["input"]["image_urls"] == [
        "https://kie-files.test/first.png", "https://kie-files.test/second.png",
    ]
    assert [call.args[0] for call in upload.await_args_list] == [
        "https://external.test/one", "https://external.test/two",
    ]


@pytest.mark.asyncio
async def test_corrupt_local_image_never_reaches_upload_or_paid_task(monkeypatch, tmp_path):
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    (tmp_path / "bad.png").write_bytes(b"<html>gone</html>")
    upload, create = AsyncMock(), AsyncMock()
    monkeypatch.setattr(image_service.kieai_client, "upload_file_stream", upload)
    monkeypatch.setattr(image_service.kieai_client, "create_task", create)
    with pytest.raises(ValueError, match="загруз"):
        await image_service.generate_image(
            image_service.ImageModel.SEEDREAM_5_PRO_I2I, "edit",
            image_url="https://example.test/static/upload/bad.png",
        )
    upload.assert_not_awaited()
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_reference_staging_deadline_cancels_before_paid_submission(monkeypatch):
    canceled = asyncio.Event()

    async def stalled_upload(_url):
        try:
            await asyncio.Event().wait()
        finally:
            canceled.set()

    monkeypatch.setattr(image_service.kieai_client, "upload_reference_image_url", stalled_upload)
    # Test the real deadline while keeping the regression fast.
    monkeypatch.setattr(image_service, "settings", image_service.settings.model_copy(
        update={"SEEDREAM_REFERENCE_TIMEOUT_SECONDS": 0.01},
    ))
    create = AsyncMock()
    monkeypatch.setattr(image_service.kieai_client, "create_task", create)
    with pytest.raises(ValueError, match="загруз"):
        await asyncio.wait_for(image_service.generate_image(
            image_service.ImageModel.SEEDREAM_5_PRO_I2I, "edit",
            image_url="https://remote.test/stalled.jpg",
        ), timeout=0.5)
    assert canceled.is_set()
    create.assert_not_awaited()
