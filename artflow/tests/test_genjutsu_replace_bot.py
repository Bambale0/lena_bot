"""Exercise the installed Telegram router with real FSM and external I/O mocked."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import video_gen
from core.config import settings
from tests.factories import make_callback, make_message
from tests.test_genjutsu_face_clothing import provider  # noqa: F401


@pytest.fixture
def state():
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=2, user_id=2))


@pytest.fixture
def io(monkeypatch):
    monkeypatch.setattr(settings, 'KIE_AI_KEY', 'test-key')
    cost = SimpleNamespace(model_key='bytedance/seedance-2-5', credits=3, is_active=True, display_name='Seedance 2.5')
    monkeypatch.setattr(video_gen.repo, 'get_all_model_costs', AsyncMock(return_value=[cost]))
    monkeypatch.setattr(video_gen.repo, 'get_model_cost', AsyncMock(return_value=cost))
    monkeypatch.setattr(video_gen.repo, 'resolve_video_model_cost', AsyncMock(return_value=cost))
    monkeypatch.setattr(video_gen, 'mirror_telegram_file', AsyncMock(side_effect=lambda bot, file_id, **kw: f'https://example.test/{file_id}'))
    monkeypatch.setattr(video_gen, 'seedance25_edit_billing_duration', AsyncMock(return_value=7))
    return SimpleNamespace(user=SimpleNamespace(id=2, credits=1000, tg_id=2), session=AsyncMock(), bot=AsyncMock())


async def callback(data, state, io):
    call = make_callback(data=data)
    await video_gen.router.propagate_event('callback_query', call, state=state,
        raw_state=await state.get_state(), session=io.session, db_user=io.user, bot=io.bot)
    return call


async def action(name, state, io):
    return await callback(f'gjreplace:{name}:{(await state.get_data()).get("gj_token", "missing")}', state, io)


async def message(state, io, *, photo=None, video=False, text=None, caption=None):
    msg = make_message(text=text)
    msg.photo = [SimpleNamespace(file_id=photo)] if photo else None
    msg.video = SimpleNamespace(file_id='source.mp4', duration=7, width=720, height=1280) if video else None
    msg.document = None
    msg.caption = caption
    await video_gen.router.propagate_event('message', msg, state=state,
        raw_state=await state.get_state(), session=io.session, db_user=io.user, bot=io.bot)
    return msg


@pytest.mark.asyncio
async def test_entry_starts_isolated_source_first_flow(state, io):
    await state.set_data({'seedance_identity_transfer': True, 'old_task': 'discard'})
    await callback('gjreplace:start', state, io)
    assert await state.get_state() == 'GenjutsuReplaceFSM:source_video'
    assert 'old_task' not in await state.get_data()


@pytest.mark.asyncio
@pytest.mark.parametrize('faces', [0, 1, 3])
@pytest.mark.parametrize('outfit', ['photo', 'text', 'caption'])
async def test_full_flow_restores_back_and_shows_duration_price(state, io, faces, outfit):
    await callback('gjreplace:start', state, io)
    await message(state, io, video=True)
    for i in range(faces):
        await message(state, io, photo=f'face{i}.jpg')
    await action('next' if faces else 'skip', state, io)
    await message(state, io, photo='shirt.jpg' if outfit != 'text' else None,
        text='red jacket' if outfit == 'text' else None, caption='red jacket' if outfit == 'caption' else None)
    await action('next', state, io)
    await message(state, io, text='25')
    call = await action('res:480p', state, io)
    data = await state.get_data()
    assert await state.get_state() == 'GenjutsuReplaceFSM:confirm'
    assert data['seedance_content_edit']['number'] == '25'
    assert data['seedance_reference_roles'] == (['identity_primary'] + ['identity_support']*(faces-1) if faces else []) + (['clothing'] if outfit != 'text' else [])
    assert data['reference_video_url'] == 'https://example.test/source.mp4'
    assert data['duration'] == 7
    assert '21' in call.message.edit_text.await_args.args[0]
    await action('back', state, io)
    assert await state.get_state() == 'GenjutsuReplaceFSM:resolution'
    assert (await state.get_data())['image_url'] == data['image_url']
    await action('cancel', state, io)
    assert await state.get_state() == 'VideoGenFSM:model_select'
    assert 'seedance_content_edit' not in await state.get_data()


@pytest.mark.asyncio
async def test_too_many_identity_refs_leave_first_three_intact(state, io):
    await callback('gjreplace:start', state, io)
    await message(state, io, video=True)
    for i in range(4):
        await message(state, io, photo=f'face{i}.jpg')
    assert len((await state.get_data())['gj_identity_urls']) == 3


@pytest.mark.asyncio
async def test_old_confirmation_cannot_launch_a_new_draft(state, io, monkeypatch):
    await callback('gjreplace:start', state, io)
    old = (await state.get_data())['gj_token']
    await callback('gjreplace:start', state, io)
    launch = AsyncMock()
    monkeypatch.setattr(video_gen, '_launch_video_generation_from_state', launch)
    await callback(f'gjreplace:launch:{old}', state, io)
    launch.assert_not_awaited()
    assert await state.get_state() == 'GenjutsuReplaceFSM:source_video'


async def ready(state, io):
    await callback('gjreplace:start', state, io)
    await message(state, io, video=True)
    await message(state, io, photo='face.jpg')
    await action('next', state, io)
    await message(state, io, photo='shirt.jpg', caption='red jacket')
    await action('next', state, io)
    await message(state, io, text='25')
    await action('res:720p', state, io)


@pytest.fixture
def billing(monkeypatch):
    spend = AsyncMock(return_value=True)
    create = AsyncMock(return_value=SimpleNamespace(id=42))
    refund = AsyncMock(return_value=(None, True))
    monkeypatch.setattr(video_gen.repo, 'spend_credits', spend)
    monkeypatch.setattr(video_gen.repo, 'create_generation', create)
    monkeypatch.setattr(video_gen.repo, 'update_generation_task', AsyncMock())
    monkeypatch.setattr(video_gen.repo, 'fail_generation_and_refund', refund)
    return SimpleNamespace(spend=spend, create=create, refund=refund)


@pytest.mark.asyncio
async def test_confirm_reaches_real_provider_and_persists_full_repeat_snapshot(state, io, billing, provider):
    await ready(state, io)
    token = (await state.get_data())['gj_token']
    await action('launch', state, io)
    params = billing.create.await_args.kwargs['input_params']
    assert params['flow_id'] == 'genjutsu_face_clothing'
    assert params['seedance_content_edit'] == {'number': '25', 'clothing': 'red jacket'}
    assert params['seedance_reference_roles'] == ['identity_primary', 'clothing']
    assert params['image_url'] == ['https://example.test/face.jpg', 'https://example.test/shirt.jpg']
    assert params['reference_video_url'] == 'https://example.test/source.mp4'
    assert billing.spend.await_args.args[2] == 21
    payload = provider.await_args.args[0]['input']
    assert payload['reference_video_urls'] == [params['reference_video_url']]
    assert payload['reference_image_urls'] == params['image_url']
    assert '@Image2 is the clothing' in payload['prompt']
    assert 'must read exactly "25"' in payload['prompt']
    await callback(f'gjreplace:launch:{token}', state, io)
    assert billing.spend.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('prefix', ['regen', 'reparams', 'reprompt'])
async def test_history_restores_exact_content_edit_before_charging(state, io, billing, provider, monkeypatch, prefix):
    from db.models import GenerationType
    await ready(state, io)
    saved = await state.get_data()
    snapshot = {k: v for k, v in saved.items() if not k.startswith('gj_')}
    previous = SimpleNamespace(id=19, user_id=2, prompt='Замена лица', model=saved['model_key'],
        gen_type=GenerationType.video, input_params=snapshot, result_url='https://example.test/result.mp4', task_id=None)
    monkeypatch.setattr(video_gen.repo, 'get_generation_by_id', AsyncMock(return_value=previous))
    monkeypatch.setattr(video_gen, '_video_repeat_params_for_generation', AsyncMock(return_value=snapshot))
    await state.clear()
    await callback(f'{prefix}:video:19', state, io)
    data = await state.get_data()
    assert await state.get_state() == 'GenjutsuReplaceFSM:confirm'
    assert data['seedance_content_edit'] == {'number': '25', 'clothing': 'red jacket'}
    assert data['gj_clothing_url'] == 'https://example.test/shirt.jpg'
    assert data['reference_video_url'] == 'https://example.test/source.mp4'
    billing.spend.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_rejection_refunds_once_and_keeps_editable_draft(state, io, billing, provider):
    provider.side_effect = RuntimeError('provider rejected')
    await ready(state, io)
    token = (await state.get_data())['gj_token']
    await action('launch', state, io)
    assert await state.get_state() == 'GenjutsuReplaceFSM:confirm'
    assert (await state.get_data())['seedance_content_edit']['number'] == '25'
    billing.refund.assert_awaited_once()
    await callback(f'gjreplace:launch:{token}', state, io)
    assert billing.spend.await_count == billing.refund.await_count == 1
