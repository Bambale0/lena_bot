/** A POST may have been charged even when its response was lost. Never blindly replay it. */
export function trendRunNeedsReadOnlyRecovery(httpStatus?: number): boolean {
  return httpStatus === undefined || httpStatus >= 500 || [408, 409, 429].includes(httpStatus);
}

export const TREND_RUN_UNCERTAIN_MESSAGE =
  "Результат запуска пока не подтверждён. Новую генерацию не запускаем: задача уже могла быть создана. Проверь статус или историю работ.";
