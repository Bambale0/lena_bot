import { AudioLines, Clapperboard, ImagePlus, PersonStanding, ScanFace, TextCursorInput, UserRound } from "lucide-react";

/** A literal frame makes the catalog's aspect ratios readable at a glance. */
export function AspectRatioGlyph({ ratio }: { ratio: string }) {
  const match = /^(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$/.exec(ratio);
  const proportion = match ? Number(match[1]) / Number(match[2]) : 0;
  if (!Number.isFinite(proportion) || proportion <= 0) {
    return <svg viewBox="0 0 36 32" fill="none" aria-hidden="true" focusable="false">
      <path d="M12 5H6v6m18-6h6v6M6 21v6h6m18-6v6h-6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M18 10v12m-6-6h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity=".55" />
    </svg>;
  }
  const width = proportion >= 1 ? 26 : 24 * proportion;
  const height = proportion >= 1 ? 26 / proportion : 24;
  return <svg viewBox="0 0 36 32" fill="none" aria-hidden="true" focusable="false">
    <rect x={(36 - width) / 2} y={(32 - height) / 2} width={width} height={height} rx="2" fill="currentColor" fillOpacity=".09" stroke="currentColor" strokeWidth="1.7" />
    <path d={`M${18 - width / 4} 16h${width / 2}M18 ${16 - height / 4}v${height / 2}`} stroke="currentColor" strokeWidth="1" opacity=".35" />
  </svg>;
}

export function CreationModeGlyph({ mode }: { mode: string }) {
  const Icon = {
    text: TextCursorInput, image: ImagePlus, video: Clapperboard,
    motion: PersonStanding, audio: AudioLines, avatar: UserRound, character: ScanFace,
  }[mode] || TextCursorInput;
  return <Icon aria-hidden="true" strokeWidth={1.7} />;
}

export function creationModeHint(mode: string): string {
  return {
    text: "Из описания", image: "Из ваших фото", video: "Из исходного видео",
    motion: "По движению в видео", audio: "По аудио", avatar: "С вашим героем", character: "С вашим персонажем",
  }[mode] || "Выберите исходные материалы";
}
