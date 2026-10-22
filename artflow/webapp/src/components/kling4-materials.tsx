import { useEffect, useRef, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { KLING4_KEYFRAME, type Kling4Element, type Kling4Options } from '@/lib/kling4';

interface Props {
  model: string;
  value: Kling4Options;
  onChange: (value: Kling4Options) => void;
  onBusyChange: (busy: boolean) => void;
  onUpload: (file: File) => Promise<{ url: string; kind?: string }>;
}

export function Kling4Materials({ model, value, onChange, onUpload, onBusyChange }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; onBusyChange(false); }; }, [onBusyChange]);
  const keyframe = model === KLING4_KEYFRAME;
  const elements = value.elements || [];
  const voices = value.voices || [];
  async function upload(files: FileList | null, apply: (urls: string[]) => void) {
    if (!files?.length || busy) return;
    setError(''); setBusy(true); onBusyChange(true);
    try {
      const urls: string[] = [];
      for (const file of Array.from(files)) urls.push((await onUpload(file)).url);
      if (mounted.current) apply(urls);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось загрузить материал'); }
    finally { setBusy(false); onBusyChange(false); }
  }
  function fileInput(label: string, accept: string, multiple: boolean, apply: (urls: string[]) => void) {
    return <label className="grid cursor-pointer gap-1 rounded-lg border border-dashed border-border p-2 text-xs"><span>{label}</span><span className="text-primary">{busy ? "Загрузка…" : multiple ? "Добавить файлы" : "Добавить файл"}</span><input className="sr-only" aria-label={label} type="file" accept={accept} multiple={multiple} disabled={busy} onChange={event => { const files = event.target.files; void upload(files, apply); event.target.value = ''; }} /></label>;
  }
  function list(urls: string[], remove: (index: number) => void) {
    return <ol className="grid gap-1 text-xs">{urls.map((url,index) => <li key={`${url}:${index}`} className="flex items-center gap-2"><span className="min-w-0 flex-1 truncate">{index+1}. {url.split('/').pop()}</span><button type="button" aria-label={`Удалить материал ${index+1}`} onClick={() => remove(index)}>Убрать</button></li>)}</ol>;
  }
  function changeElement(index: number, patch: Partial<Kling4Element>) {
    onChange({ ...value, elements: elements.map((item,i) => i===index ? {...item,...patch} : item) });
  }
  return <section aria-label="Материалы Kling 4" className="grid gap-3 rounded-xl border border-border p-3">
    <p className="text-sm font-semibold">{keyframe ? 'Ключевые кадры Kling 4' : 'Материалы Kling 4'}</p>
    <p className="text-xs text-muted-foreground">{keyframe ? 'Первый → промежуточные → последний. Для 3 секунд — до 4 кадров, от 9 секунд — до 10. Пропорции задаёт первый кадр.' : 'Упоминайте материалы в промпте: @image_1, @video_1 или @имя персонажа/голоса. Общий лимит — 15 материалов и 30 секунд входных видео.'}</p>
    <fieldset disabled={busy} className="grid min-w-0 gap-3">
    {keyframe ? <>
      {fileInput('Первый кадр','image/png,image/jpeg,image/webp',false, urls => onChange({...value,first_frame_url:urls[0]}))}
      {value.first_frame_url ? list([value.first_frame_url], () => onChange({...value,first_frame_url:null})) : null}
      {fileInput('Промежуточные кадры','image/png,image/jpeg,image/webp',true,urls => onChange({...value,keyframe_urls:[...(value.keyframe_urls||[]),...urls]}))}
      {list(value.keyframe_urls||[], index => onChange({...value,keyframe_urls:value.keyframe_urls?.filter((_,i)=>i!==index)}))}
      {fileInput('Последний кадр','image/png,image/jpeg,image/webp',false,urls => onChange({...value,last_frame_url:urls[0]}))}
      {value.last_frame_url ? list([value.last_frame_url], () => onChange({...value,last_frame_url:null})) : null}
    </> : <>
      {fileInput('Фото-референсы · до 10','image/png,image/jpeg,image/webp',true,urls=>onChange({...value,image_urls:[...(value.image_urls||[]),...urls]}))}
      {list(value.image_urls||[], index=>onChange({...value,image_urls:value.image_urls?.filter((_,i)=>i!==index)}))}
      {fileInput('Видео-референсы · до 5','video/mp4,video/webm,video/quicktime',true,urls=>onChange({...value,video_urls:[...(value.video_urls||[]),...urls]}))}
      {list(value.video_urls||[],index=>onChange({...value,video_urls:value.video_urls?.filter((_,i)=>i!==index)}))}
      <label className="flex gap-2 text-xs"><input type="checkbox" checked={value.keep_original_sound===true} onChange={event=>onChange({...value,keep_original_sound:event.target.checked})}/>Сохранить исходный звук видео</label>
      <details className="grid gap-2"><summary className="cursor-pointer text-sm">Персонажи и другие элементы · {elements.length}/7</summary>
        {elements.map((element,index)=><div key={index} className="my-3 grid gap-2 rounded-lg border border-border p-2">
          <label className="grid gap-1 text-xs">Имя для @{element.name}<Input aria-label={`Имя элемента ${index+1}`} maxLength={20} defaultValue={element.name} onBlur={event=>changeElement(index,{name:event.target.value})}/></label>
          <Select aria-label={`Тип элемента ${index+1}`} value={element.tag||'character'} onChange={event=>changeElement(index,{tag:event.target.value as Kling4Element['tag']})}>{['character','animal','prop','costume','scene','effect','others'].map((tag,i)=><option key={tag} value={tag}>{['Персонаж','Животное','Предмет','Костюм','Сцена','Эффект','Другое'][i]}</option>)}</Select>
          <Textarea aria-label={`Описание элемента ${index+1}`} placeholder="Описание до 100 символов" maxLength={100} value={element.description||''} onChange={event=>changeElement(index,{description:event.target.value})}/>
          {fileInput(`Ракурсы ${element.name} · 2–4 фото`,'image/png,image/jpeg,image/webp',true,urls=>changeElement(index,{image_urls:[...(element.image_urls||[]),...urls],video_url:undefined}))}
          {list(element.image_urls||[],i=>changeElement(index,{image_urls:element.image_urls?.filter((_,j)=>j!==i)}))}
          {fileInput(`Видео ${element.name} · 3–8 сек, от 700 px`,'video/mp4,video/webm,video/quicktime',false,urls=>changeElement(index,{video_url:urls[0],image_urls:[],tag:'character'}))}
          {element.video_url ? list([element.video_url],()=>changeElement(index,{video_url:undefined})) : null}
          {fileInput(`Привязанный голос ${element.name} · 5–30 сек`,'audio/*',false,urls=>changeElement(index,{voice_url:urls[0],tag:'character'}))}
          {element.voice_url ? list([element.voice_url],()=>changeElement(index,{voice_url:undefined})) : null}
          <Button type="button" variant="ghost" onClick={()=>onChange({...value,elements:elements.filter((_,i)=>i!==index)})}>Удалить элемент</Button>
        </div>)}
        <Button type="button" variant="outline" disabled={elements.length>=7||busy} onClick={()=>onChange({...value,elements:[...elements,{name:`Hero_${elements.length+1}`,tag:'character'}]})}>Добавить элемент</Button>
      </details>
      <details><summary className="cursor-pointer text-sm">Голосовые референсы · {voices.length}/3</summary>
        {voices.map((voice,index)=><div key={index} className="my-3 grid gap-2">
          <Input aria-label={`Имя голоса ${index+1}`} maxLength={20} defaultValue={voice.name} onBlur={event=>onChange({...value,voices:voices.map((item,i)=>i===index?{...item,name:event.target.value}:item)})}/>
          {fileInput(`Аудио ${voice.name} · 5–30 сек`,'audio/*',false,urls=>onChange({...value,voices:voices.map((item,i)=>i===index?{...item,audio_url:urls[0]}:item)}))}
          {voice.audio_url ? <p className="text-xs">Аудио загружено</p> : null}
          <Button type="button" variant="ghost" onClick={()=>onChange({...value,voices:voices.filter((_,i)=>i!==index)})}>Удалить голос</Button>
        </div>)}
        <Button type="button" variant="outline" disabled={voices.length>=3||busy} onClick={()=>onChange({...value,voices:[...voices,{name:`Voice_${voices.length+1}`,audio_url:''}]})}>Добавить голос</Button>
      </details>
    </>}
    </fieldset>
    {busy ? <p role="status" className="text-xs">Загружаем материалы…</p> : null}
    {error ? <p role="alert" className="text-xs text-destructive">{error}</p> : null}
  </section>;
}
