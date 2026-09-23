from db import models


def test_user_image_model_unlimited_model_exists() -> None:
    assert hasattr(models, "UserImageModelUnlimited")
