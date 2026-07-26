from types import SimpleNamespace

from bot.handlers.video_wizard import SCENARIOS, _home_kb, _review_kb


def callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_video_entry_is_task_first_not_model_first():
    markup = _home_kb()
    cb = callbacks(markup)

    assert cb[:4] == [
        "vid_wizard:scenario:text",
        "vid_wizard:scenario:image",
        "vid_wizard:scenario:video",
        "vid_wizard:scenario:motion",
    ]
    assert "vid_wizard:advanced" in cb
    assert all(not item.startswith("vid_model:") for item in cb)


def test_video_scenarios_have_human_goal_and_recommendations():
    assert set(SCENARIOS) == {"text", "image", "video", "motion"}
    for scenario in SCENARIOS.values():
        assert scenario["title"]
        assert scenario["description"]
        assert scenario["mode"] in {"text", "image", "video", "motion"}
        assert scenario["recommended"]


def test_review_has_explicit_price_and_safe_escape_routes():
    markup = _review_kb(42)
    assert labels(markup)[0] == "🚀 Запустить за 42 💋"
    assert callbacks(markup) == [
        "vid_review:launch",
        "vid_review:prompt",
        "vid_review:params",
        "menu:video",
        "menu:main",
    ]
