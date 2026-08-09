import React from "react";

import { capabilityFlags, videoModeLabel } from "./generationCapabilities.js";

export function AdvancedVideoControls({
  model,
  mode,
  setMode,
  videoUrl,
  setVideoUrl,
  videoStart,
  setVideoStart,
  videoEnd,
  setVideoEnd,
  audioIds,
  setAudioIds,
  characterIds,
  setCharacterIds,
  seed,
  setSeed,
}) {
  const flags = capabilityFlags(model, mode);
  const modes = Array.isArray(model?.modes) && model.modes.length ? model.modes : ["text"];

  return (
    <div className="advancedVideoControls">
      {modes.length > 1 && (
        <div className="advancedVideoBlock">
          <div className="advancedVideoLabel">Источник</div>
          <div className="tabs soft">
            {modes.map((value) => (
              <button key={value} type="button" className={mode === value ? "active" : ""} onClick={() => setMode(value)}>
                {videoModeLabel(value)}
              </button>
            ))}
          </div>
        </div>
      )}

      {flags.mode === "video" && flags.canUseVideo && (
        <div className="advancedVideoBlock">
          <div className="advancedVideoLabel">Видео-референс</div>
          <input
            className="field"
            type="url"
            value={videoUrl}
            onChange={(event) => setVideoUrl(event.target.value)}
            placeholder="https://.../source.mp4"
            autoCapitalize="none"
            autoCorrect="off"
          />
          <div className="settingsGrid">
            <label>
              <span>Начало, сек</span>
              <input className="field" type="number" min="0" step="0.1" value={videoStart} onChange={(event) => setVideoStart(event.target.value)} />
            </label>
            <label>
              <span>Конец, сек</span>
              <input className="field" type="number" min="0" step="0.1" value={videoEnd} onChange={(event) => setVideoEnd(event.target.value)} placeholder="до 10 сек" />
            </label>
          </div>
          <small>Фрагмент видео не должен превышать 10 секунд.</small>
        </div>
      )}

      {flags.maxAudioIds > 0 && (
        <div className="advancedVideoBlock">
          <div className="advancedVideoLabel">Audio ID</div>
          <textarea
            className="field"
            value={audioIds}
            onChange={(event) => setAudioIds(event.target.value)}
            placeholder={`До ${flags.maxAudioIds} ID, через запятую или с новой строки`}
            rows={2}
          />
        </div>
      )}

      {flags.maxCharacterIds > 0 && (
        <div className="advancedVideoBlock">
          <div className="advancedVideoLabel">Character IDs</div>
          <textarea
            className="field"
            value={characterIds}
            onChange={(event) => setCharacterIds(event.target.value)}
            placeholder={`До ${flags.maxCharacterIds} ID, через запятую или с новой строки`}
            rows={2}
          />
        </div>
      )}

      {flags.hasSeed && (
        <div className="advancedVideoBlock">
          <div className="advancedVideoLabel">Seed</div>
          <input
            className="field"
            type="number"
            min="0"
            max="2147483647"
            value={seed}
            onChange={(event) => setSeed(event.target.value)}
            placeholder="Автоматически"
          />
        </div>
      )}
    </div>
  );
}
