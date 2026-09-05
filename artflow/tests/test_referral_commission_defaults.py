from core.config import Settings


def test_referral_commission_defaults_are_40_7_3(monkeypatch) -> None:
    for name in ("REFERRAL_COMMISSION_L1", "REFERRAL_COMMISSION_L2", "REFERRAL_COMMISSION_L3"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.REFERRAL_COMMISSION_L1 == 0.40
    assert settings.REFERRAL_COMMISSION_L2 == 0.07
    assert settings.REFERRAL_COMMISSION_L3 == 0.03
