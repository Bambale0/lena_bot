"""Background results may only alter the workflow that submitted their task."""

from aiogram.fsm.context import FSMContext

from bot.states import MidjourneyFSM


async def owns_midjourney_task(state: FSMContext | None, task_id: str) -> bool:
    if state is None:
        return False
    current = await state.get_state()
    result_states = {
        MidjourneyFSM.generating.state,
        MidjourneyFSM.blend_generating.state,
        MidjourneyFSM.describe_polling.state,
        MidjourneyFSM.video_generating.state,
        MidjourneyFSM.action_polling.state,
        MidjourneyFSM.waiting_modal_input.state,
        MidjourneyFSM.viewing_result.state,
    }
    if current not in result_states:
        return False
    data = await state.get_data()
    return str(data.get("pending_mj_task_id") or data.get("task_id") or "") == str(task_id)
