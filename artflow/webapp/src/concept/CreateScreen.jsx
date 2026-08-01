import React, { useEffect, useMemo, useRef, useState } from "react";
import Icon from "./icons.jsx";
import {
  api,
  formatCredits,
  generationResultUrls,
  isVideoMedia,
  publicPrompt,
  uploadReference,
} from "./api.js";
import { EmptyState, MediaViewer, ProgressiveMedia } from "./components.jsx";

const STYLES = [
  { key: "cinematic", label: "Кинематик", hint: "cinematic lighting, premium color grading, detailed", art: "cinematic" },
  { key: "neon", label: "Неон", hint: "neon light, glossy reflections, night atmosphere", art: "neon" },
  { key: "realism", label: "Реализм", hint: "photorealistic, natural skin, realistic light", art: "realism" },
  { key: "art", label: "Арт", hint: "concept art, expressive composition, museum quality", art: "art" },
];

function normalizeOptions(values, fallback = []) {
  const source = Array.isArray(values) && values.length ? values : fallback;
  return source.map((value) => typeof value === "object" ? value : { value, label: String(value) });
}

function modelCost(model, kind, settings) {
  if (!model) return 0;
  if (kind === "image") {
    return Number(model.quality_prices?.[settings.quality] ?? model.credits ?? 0) * Number(settings.count || 1);
  }
  if (model.is_per_second) return Number(model.credits_per_sec || model.credits || 0) * Number(settings.duration || 0);
  if (model.key === "gemini-omni-video") {
    const resolution = settings.resolution === "2160p" ? "4k" : settings.resolution;
    return Number(model.price_table?.[resolution]?.[settings.duration] ?? model.credits ?? 0);
  }
  return Number(model.credits || 0);
}

function ResultPanel({ generation, onOpen, onRepeat, onNotice, onFeedReload }) {
  const [publishing, setPublishing] = useState(false);
  const [saving, setSaving] = useState(false);
  if (!generation) return null;

  const urls = generationResultUrls(generation);
  const pending = generation.status === "pending" || generation.status === "processing";
  const done = generation.status === "done";
  const prompt = publicPrompt(generation);

  async function publish() {
    if (!generation.id || publishing) return;
    setPublishing(true);
    try {
      await api(`/generations/${generation.id}/share`, { method: "POST" });
      onFeedReload?.();
      onNotice({ type: "success", message: "Работа опубликована в ленте" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось опубликовать" });
    } finally {
      setPublishing(false);
    }
  }

  async function save() {
    if (!generation.id || saving) return;
    setSaving(true);
    try {
      await api(`/generations/${generation.id}/share-library`, { method: "POST" });
      onNotice({ type: "success", message: "Промпт сохранён" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось сохранить промпт" });
    } finally {
      setSaving(false);
    }
  }

  if (pending) {
    return (
      <section className="cxResult cxResult--pending">
        <span className="cxResult__orb"><Icon name="sparkle" size={28}/></span>
        <h2>Создаём магию</h2>
        <p>Можно продолжать пользоваться приложением — результат появится здесь.</p>
        <div><i/><i/><i/></div>
      </section>
    );
  }

  if (generation.status === "failed") {
    return (
      <EmptyState
        icon="close"
        title="Не получилось"
        text={generation.error || "Провайдер временно недоступен."}
        action={<button className="cxSecondaryButton" type="button" onClick={onRepeat}><Icon name="reload" size={17}/>Повторить</button>}
      />
    );
  }

  if (!done || !urls.length) return null;

  return (
    <section className="cxResult cxResult--done">
      <header className="cxResult__header">
        <div><span><Icon name="check" size={18}/></span><div><small>Результат</small><h2>Готово</h2></div></div>
        <b>#{generation.id}</b>
      </header>

      <div className={`cxResult__media ${urls.length > 1 ? "multi" : ""}`}>
        {urls.map((url, index) => (
          <ProgressiveMedia
            key={`${url}-${index}`}
            item={generation}
            index={index}
            sources={[url]}
            onClick={() => onOpen({ item: generation, index })}
          />
        ))}
      </div>

      <article className="cxResult__details">
        <div><Icon name="sparkle" size={19}/><span><small>Модель</small><b>{generation.model || "APIX"}</b></span></div>
        {prompt && <div><Icon name="prompt" size={19}/><span><small>Промпт</small><p>{prompt}</p></span></div>}
      </article>

      <div className="cxResult__quick">
        <button type="button" onClick={onRepeat}><Icon name="sparkle" size={18}/>Ещё вариант</button>
        <button type="button" onClick={save} disabled={saving}><Icon name="bookmark" size={18}/>{saving ? "..." : "Сохранить"}</button>
      </div>

      {generation.gen_type !== "video" && (
        <button className="cxPrimaryButton cxPrimaryButton--wide" type="button" onClick={publish} disabled={publishing}>
          <Icon name="home" size={20}/>{publishing ? "Публикуем..." : "В ленту"}
        </button>
      )}
    </section>
  );
}

export default function CreateScreen({ user, imageModels, videoModels, preset, generation, onGenerate, onClearPreset, onTopup, onNotice, onFeedReload }) {
  const [kind, setKind] = useState("image");
  const [prompt, setPrompt] = useState("");
  const [style, setStyle] = useState("cinematic");
  const [modelKey, setModelKey] = useState("");
  const [mode, setMode] = useState("text");
  const [ratio, setRatio] = useState("9:16");
  const [quality, setQuality] = useState("basic");
  const [count, setCount] = useState(1);
  const [duration, setDuration] = useState(5);
  const [resolution, setResolution] = useState("720p");
  const [modeOption, setModeOption] = useState("normal");
  const [referenceUrls, setReferenceUrls] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [improving, setImproving] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [viewer, setViewer] = useState(null);
  const fileRef = useRef(null);

  const models = useMemo(() => kind === "video"
    ? videoModels.filter((model) => (model.modes || []).some((value) => value === "text" || value === "image"))
    : imageModels,
  [kind, imageModels, videoModels]);

  const current = models.find((model) => model.key === modelKey) || models[0] || null;
  const modes = current?.modes || ["text"];
  const ratios = normalizeOptions(current?.aspect_ratios, ["9:16", "3:4", "1:1", "4:5", "16:9"]);
  const qualities = normalizeOptions(current?.quality_options, ["basic"]);
  const counts = normalizeOptions(current?.counts, [1]);
  const durations = normalizeOptions(current?.durations || current?.duration_options, [5]);
  const resolutions = normalizeOptions(current?.resolutions, ["720p"]);
  const modeOptions = normalizeOptions(current?.mode_options, ["normal"]);
  const maxRefs = Math.max(1, Number(current?.max_refs || 1));
  const estimatedCost = modelCost(current, kind, { quality, count, duration, resolution });

  useEffect(() => {
    if (!models.length) {
      setModelKey("");
      return;
    }
    if (!models.some((model) => model.key === modelKey)) setModelKey(models[0].key);
  }, [models, modelKey]);

  useEffect(() => {
    if (!current) return;
    const nextModes = current.modes || ["text"];
    setMode(nextModes.includes("text") ? "text" : nextModes[0]);
    setRatio((current.aspect_ratios || ["9:16"])[0]);
    setQuality(normalizeOptions(current.quality_options, ["basic"])[0]?.value || "basic");
    setCount(Number((current.counts || [1])[0]));
    setDuration(Number((current.durations || current.duration_options || [5])[0]));
    setResolution((current.resolutions || ["720p"])[0]);
    setModeOption((current.mode_options || ["normal"])[0]);
    setReferenceUrls((urls) => urls.slice(0, Math.max(1, Number(current.max_refs || 1))));
  }, [current?.key]);

  useEffect(() => {
    if (!preset) return;
    setKind(preset.kind === "video" ? "video" : "image");
    if (!preset.hiddenPrompt) setPrompt(preset.prompt || "");
    if (preset.modelKey) setModelKey(preset.modelKey);
    if (preset.remix) {
      setReferenceUrls(generationResultUrls(preset.remix).slice(0, 4));
      setMode("image");
    }
  }, [preset]);

  async function improvePrompt() {
    if (!prompt.trim() || improving) return;
    setImproving(true);
    try {
      const result = await api("/prompt/improve", {
        method: "POST",
        body: JSON.stringify({ prompt, kind }),
      });
      setPrompt(result.prompt || prompt);
      onNotice({ type: "success", message: "Промпт улучшен" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось улучшить промпт" });
    } finally {
      setImproving(false);
    }
  }

  async function addReferences(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (!files.length || uploading) return;
    setUploading(true);
    try {
      const available = Math.max(0, maxRefs - referenceUrls.length);
      const next = [];
      for (const file of files.slice(0, available)) next.push(await uploadReference(file));
      setReferenceUrls((currentUrls) => [...currentUrls, ...next].slice(0, maxRefs));
      onNotice({ type: "success", message: `Загружено: ${next.length}` });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось загрузить референс" });
    } finally {
      setUploading(false);
    }
  }

  function submit() {
    if (!current) return;
    if (!prompt.trim() && current.key !== "midjourney-blend" && !preset?.remix) {
      onNotice({ type: "warning", message: "Опиши, что нужно создать" });
      return;
    }
    if (mode === "image" && !referenceUrls.length) {
      onNotice({ type: "warning", message: "Добавь референс" });
      return;
    }
    if (Number(user.credits || 0) < estimatedCost) {
      onTopup();
      return;
    }

    const stylePreset = STYLES.find((item) => item.key === style);
    const finalPrompt = prompt.trim()
      ? `${prompt.trim()}${stylePreset ? `, ${stylePreset.hint}` : ""}`
      : "";

    onGenerate({
      kind,
      remix: preset?.remix || null,
      payload: {
        model: current.key,
        prompt: finalPrompt,
        prompt_id: preset?.promptId || null,
        mode,
        aspect_ratio: ratio,
        quality,
        count,
        duration,
        resolution,
        grok_mode: modeOptions.length > 1 ? modeOption : undefined,
        image_url: referenceUrls[0] || null,
        reference_url: referenceUrls[0] || null,
        reference_urls: referenceUrls.slice(1),
      },
    });
  }

  return (
    <section className="cxScreen cxCreateScreen">
      {preset && (
        <div className="cxPresetNotice">
          <Icon name="sparkle" size={17}/>
          <span>{preset.remix ? "Повтор публикации" : "Промпт подставлен"}</span>
          <button type="button" onClick={() => { onClearPreset(); setReferenceUrls([]); }}><Icon name="close" size={16}/></button>
        </div>
      )}

      <div className="cxCreateTabs">
        <button type="button" className={kind === "image" && style !== "art" ? "active" : ""} onClick={() => { setKind("image"); if (style === "art") setStyle("cinematic"); }}><Icon name="image" size={18}/>Фото</button>
        <button type="button" className={kind === "video" ? "active" : ""} onClick={() => setKind("video")}><Icon name="video" size={18}/>Видео</button>
        <button type="button" className={kind === "image" && style === "art" ? "active" : ""} onClick={() => { setKind("image"); setStyle("art"); }}><Icon name="sparkle" size={18}/>Арт</button>
      </div>

      <section className="cxPromptComposer">
        <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Опишите, что хотите создать..." maxLength={8000}/>
        <footer>
          <span>{prompt.length}/8000</span>
          <button type="button" onClick={improvePrompt} disabled={!prompt.trim() || improving} aria-label="Улучшить промпт"><Icon name="sparkle" size={21}/></button>
        </footer>
      </section>

      <section className="cxOptionSection">
        <header><h2>Стиль</h2></header>
        <div className="cxStyleGrid">
          {STYLES.map((item) => (
            <button key={item.key} type="button" className={style === item.key ? "active" : ""} onClick={() => setStyle(item.key)}>
              <span className={`cxStyleArt cxStyleArt--${item.art}`}><i/><b>{item.label.slice(0, 1)}</b></span>
              <small>{item.label}</small>
              {style === item.key && <i className="cxStyleCheck"><Icon name="check" size={14}/></i>}
            </button>
          ))}
        </div>
      </section>

      <section className="cxOptionSection">
        <header><h2>Модель</h2><span>{models.length}</span></header>
        <div className="cxModelRail">
          {models.map((model) => (
            <button key={model.key} type="button" className={current?.key === model.key ? "active" : ""} onClick={() => setModelKey(model.key)}>
              <span><Icon name={kind === "video" ? "video" : "sparkle"} size={18}/></span>
              <div><b>{model.display_name || model.key}</b><small>{formatCredits(model.credits)} токенов</small></div>
            </button>
          ))}
        </div>
      </section>

      {modes.length > 1 && (
        <section className="cxOptionSection cxOptionSection--compact">
          <header><h2>Источник</h2></header>
          <div className="cxSegmented">
            {modes.filter((item) => item === "text" || item === "image").map((item) => (
              <button key={item} type="button" className={mode === item ? "active" : ""} onClick={() => setMode(item)}>{item === "text" ? "По тексту" : "По фото"}</button>
            ))}
          </div>
        </section>
      )}

      {mode === "image" && (
        <section className="cxReferences">
          <header><h2>Референс <span>(необязательно)</span></h2><small>{referenceUrls.length}/{maxRefs}</small></header>
          <div className="cxReferenceGrid">
            {referenceUrls.map((url, index) => (
              <div key={`${url}-${index}`}>
                <img src={url} alt="Референс"/>
                <button type="button" onClick={() => setReferenceUrls((items) => items.filter((_, itemIndex) => itemIndex !== index))}><Icon name="close" size={14}/></button>
              </div>
            ))}
            {referenceUrls.length < maxRefs && (
              <button type="button" onClick={() => fileRef.current?.click()} disabled={uploading}>
                <span><Icon name="image" size={24}/><Icon name="plus" size={13}/></span>
                <b>{uploading ? "Загрузка" : "Загрузить изображение"}</b>
                <small>PNG, JPG или WebP</small>
              </button>
            )}
          </div>
          <input ref={fileRef} type="file" accept="image/*" multiple={maxRefs > 1} hidden onChange={addReferences}/>
        </section>
      )}

      <section className="cxOptionSection cxOptionSection--compact">
        <header><h2>Соотношение сторон</h2></header>
        <div className="cxRatioRail">
          {ratios.map((option) => (
            <button key={option.value} type="button" className={ratio === option.value ? "active" : ""} onClick={() => setRatio(option.value)}>
              <span className={`cxRatioShape cxRatioShape--${String(option.value).replace(":", "x")}`}/>
              <small>{option.label}</small>
            </button>
          ))}
        </div>
      </section>

      <button className="cxAdvancedToggle" type="button" onClick={() => setAdvanced((value) => !value)}>
        <span>Дополнительные параметры</span><Icon name="chevron" size={18}/>
      </button>

      {advanced && (
        <div className="cxAdvancedPanel">
          {kind === "image" && qualities.length > 1 && <SelectField label="Качество" options={qualities} value={quality} onChange={setQuality}/>} 
          {kind === "image" && counts.length > 1 && <SelectField label="Количество" options={counts} value={count} onChange={(value) => setCount(Number(value))}/>} 
          {kind === "video" && durations.length > 0 && <SelectField label="Длительность" options={durations.map((item) => ({ ...item, label: `${item.label} сек` }))} value={duration} onChange={(value) => setDuration(Number(value))}/>} 
          {kind === "video" && resolutions.length > 1 && <SelectField label="Разрешение" options={resolutions} value={resolution} onChange={setResolution}/>} 
          {kind === "video" && modeOptions.length > 1 && <SelectField label="Режим" options={modeOptions} value={modeOption} onChange={setModeOption}/>} 
        </div>
      )}

      <button className="cxGenerateButton" type="button" onClick={submit} disabled={!current || generation?.status === "pending" || generation?.status === "processing"}>
        <span>Создать</span><i><Icon name="sparkle" size={19}/>{formatCredits(estimatedCost)}</i>
      </button>
      <p className="cxTokenHint">Магия стоит токенов</p>

      <ResultPanel generation={generation} onOpen={setViewer} onRepeat={submit} onNotice={onNotice} onFeedReload={onFeedReload}/>

      {viewer && (
        <MediaViewer
          entry={viewer}
          onClose={() => setViewer(null)}
          onLike={() => {}}
          onRemix={() => {}}
          onShare={() => {}}
        />
      )}
    </section>
  );
}

function SelectField({ label, options, value, onChange }) {
  return (
    <label className="cxSelectField">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}
