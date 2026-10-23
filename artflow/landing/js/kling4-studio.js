/* Kling 4 materials extend the existing authenticated Studio checkout. */
(() => {
  'use strict';
  const REFERENCE = 'kling-4.0/reference-to-video';
  const KEYFRAME = 'kling-4.0/keyframe-to-video';
  const originalFetch = window.fetch.bind(window);
  const drafts = new Map();
  let uploading = false;
  let uploadController = null;
  let draftOwner = null;
  const currentOwner = () => typeof state !== 'undefined' ? String(state.user?.id || 'anonymous') : 'harness';
  let panel;
  let renderedModel = '';
  let restoredRecipe = null;
  let recipeApplied = false;
  let recipeError = '';
  const repeatId=new URLSearchParams(location.search).get('kling4_repeat');
  if(repeatId && /^\d+$/.test(repeatId)) {
    void originalFetch('/api/web/kling4/recipe/'+repeatId,{credentials:'same-origin'}).then(async response=>{const payload=await response.json();if(!response.ok||payload.ok===false)throw new Error(payload.error||payload.detail||'Повтор недоступен');restoredRecipe=payload.data||payload;sync();}).catch(error=>{recipeError=error.message;render();});
  }
  const currentKey = () => document.querySelector('[data-account-model-select]')?.value || '';
  const isKling = key => key === REFERENCE || key === KEYFRAME;
  const currentDraft = () => {
    const key = currentKey();
    if (!drafts.has(key)) drafts.set(key, {});
    return drafts.get(key);
  };
  const element = (tag, text) => { const node = document.createElement(tag); if (text) node.textContent = text; return node; };
  function button(parent, title, action) {
    const node = element('button', title); node.type = 'button'; node.className = 'button ghost';
    node.addEventListener('click', action); parent.append(node); return node;
  }
  function input(parent, label, value, action, maxLength = 20) {
    const wrapper = element('label'); wrapper.append(element('span', label));
    const node = element('input'); node.value = value || ''; node.maxLength = maxLength; node.setAttribute('aria-label', label);
    node.addEventListener(label.startsWith('Имя') ? 'change' : 'input', () => action(node.value)); wrapper.append(node); parent.append(wrapper);
  }
  function nextName(data, prefix) {
    const used=new Set([...(data.elements||[]),...(data.voices||[])].map(item=>item.name.toLowerCase()));
    let index=1;while(used.has(`${prefix}_${index}`.toLowerCase()))index++;return `${prefix}_${index}`;
  }
  function renamePrompt(oldName, newName) {
    if (!/^[\u4E00-\u9FA5A-Za-z0-9_]{1,20}$/.test(newName)) return;
    const prompt=document.querySelector('.account-composer [name=prompt]'); if(!prompt)return;
    const escaped=oldName.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    prompt.value=prompt.value.replace(new RegExp('@'+escaped+'(?![\\p{L}\\p{N}_])','gu'),'@'+newName);
    prompt.dispatchEvent(new Event('input',{bubbles:true}));
  }
  // Caps mirror the existing provider contract; checkout remains authoritative.
  const referenceCollections = {image:['image_urls',10],video:['video_urls',5],audio:['voices',3]};
  const referenceKind = file => {
    const ext=file.name.split('.').pop().toLowerCase();
    if(['png','jpg','jpeg','webp'].includes(ext))return 'image';
    if(['mp4','mov','webm'].includes(ext))return 'video';
    if(['wav','mp3','m4a','aac','flac','ogg','oga','opus'].includes(ext))return 'audio';
    throw new Error('Поддерживаются фото, видео и аудио');
  };
  function checkCapacity(data,kind) {
    const [field,limit]=referenceCollections[kind];
    if((data[field]||[]).length>=limit)throw new Error(`Не больше ${limit} материалов этого типа`);
    if(['image_urls','video_urls','elements','voices'].reduce((sum,key)=>sum+(data[key]||[]).length,0)>=15)throw new Error('Не больше 15 материалов');
  }
  function addReference(data,asset) {
    if(typeof asset.url!=='string' || !asset.url || !Object.hasOwn(referenceCollections,asset.kind))throw new Error('Сервер не подтвердил тип материала. Повторите загрузку.');
    checkCapacity(data,asset.kind);
    if(asset.kind==='audio')data.voices=[...(data.voices||[]),{name:nextName(data,'Voice'),audio_url:asset.url}];
    else {const field=referenceCollections[asset.kind][0];data[field]=[...(data[field]||[]),asset.url];}
  }
  function files(parent, label, accept, multiple, action, automatic=false) {
    const wrapper = element('label'); wrapper.className = 'reference-upload'; wrapper.append(element('span', label));
    const node = element('input'); node.type = 'file'; node.accept = accept; node.multiple = multiple; node.setAttribute('aria-label', label);
    node.addEventListener('change', async () => {
      const key = currentKey(); const owner = currentOwner(); const values = Array.from(node.files || []); if (!values.length || uploading) return;
      uploading = true; uploadController = new AbortController(); const controller = uploadController;
      const assertOwner = () => { if (currentOwner() !== owner || currentKey() !== key) throw new Error('Аккаунт или модель изменились. Добавьте материалы заново.'); };
      const status = panel.querySelector('[role=status]'); status.textContent = 'Загружаем материалы…';
      panel.querySelectorAll('input,button,select').forEach(control => { control.disabled = true; });
      try {
        const urls = [];
        for (const file of values) {
          assertOwner();
          if(automatic)checkCapacity(currentDraft(),referenceKind(file));
          const form = new FormData(); form.append('file', file); form.append('owner_id', owner);
          const response = await originalFetch('/api/web/kling4/assets', { method: 'POST', body: form, credentials: 'same-origin', signal: controller.signal });
          assertOwner();
          const payload = await response.json();
          assertOwner();
          if (!response.ok || payload.ok === false) throw new Error(payload.error || payload.detail || 'Материал не загружен');
          const asset=payload.data || payload;
          if(automatic)addReference(currentDraft(),asset);else urls.push(asset.url);
        }
        if (currentKey() !== key || currentOwner() !== owner) throw new Error('Аккаунт или модель изменились. Добавьте материалы заново.');
        if(!automatic)action(urls); render();
      } catch (error) { if(currentOwner()===owner && currentKey()===key){render();panel.querySelector('[role=status]').textContent=error.message||'Ошибка загрузки';} }
      finally { uploading = false; if(uploadController===controller)uploadController=null; panel?.querySelectorAll('input,button,select').forEach(control => { control.disabled = false; }); node.value = ''; }
    });
    wrapper.append(node); parent.append(wrapper);
  }
  function list(parent, values, remove) {
    values.forEach((url,index) => {
      const row = element('div'); row.className = 'composer-row';
      row.append(element('span', `${index+1}. ${url.split('/').pop()}`));
      button(row,'Убрать',() => { remove(index); render(); }); parent.append(row);
    });
  }
  function render() {
    const form = document.querySelector('.account-composer'); if (!form) return;
    const key = currentKey(); if (!panel || !panel.isConnected) { panel = element('section'); panel.dataset.kling4Materials = ''; panel.setAttribute('aria-label', 'Материалы Kling 4'); form.querySelector('[data-reference-section]')?.after(panel); if (!panel.isConnected) form.append(panel); }
    panel.hidden = !isKling(key); renderedModel = key;
    if (!isKling(key)) return;
    const advancedOpen=panel.querySelector('details')?.open || false;
    panel.replaceChildren(); const data = currentDraft();
    panel.append(element('h3', key === KEYFRAME ? 'Kling 4 · заказ из истории' : 'Референсы Kling 4'));
    panel.append(element('p', key === KEYFRAME ? 'Первый → промежуточные → последний. До min(10, секунды + 1) кадров. @first_frame, @keyframe_1, @last_frame.' : 'Добавьте фото, видео и аудио в любом порядке — тип референса определится автоматически. Ссылки в промпте: @image_1, @video_1, @Voice_1. Цена появится перед запуском.'));
    if (key === KEYFRAME) {
      for (const [field,title,multiple] of [['first_frame_url','Первый кадр',false],['keyframe_urls','Промежуточные кадры',true],['last_frame_url','Последний кадр',false]]) {
        files(panel,title,'image/png,image/jpeg,image/webp',multiple,urls => { data[field] = multiple ? [...(data[field] || []),...urls] : urls[0]; });
        list(panel, multiple ? data[field] || [] : data[field] ? [data[field]] : [], index => { if (multiple) data[field].splice(index,1); else delete data[field]; });
      }
    } else {
      files(panel,'Референсы · фото, видео, аудио','image/png,image/jpeg,image/webp,video/mp4,video/webm,video/quicktime,audio/*',true,null,true);
      for(const field of ['image_urls','video_urls'])list(panel,data[field]||[],index=>data[field].splice(index,1));
      for(const voice of data.voices||[])if(voice.audio_url)panel.append(element('p',`Голос @${voice.name}: ${voice.audio_url.split('/').pop()}`));
      const label = element('label', 'Сохранить исходный звук видео'); const sound = element('input'); sound.type = 'checkbox'; sound.checked = data.keep_original_sound === true; sound.addEventListener('change', () => { data.keep_original_sound = sound.checked; }); label.prepend(sound); panel.append(label);
      const advanced=element('details');advanced.open=advancedOpen;advanced.append(element('summary','Персонажи и голоса'));panel.append(advanced);
      const elements = data.elements || (data.elements = []);
      elements.forEach((item,index) => {
        const block = element('fieldset'); block.append(element('legend', `Элемент ${index+1}`));
        input(block,'Имя для @ссылки',item.name,value => { renamePrompt(item.name,value); item.name = value; });
        input(block,'Описание элемента',item.description,value => { item.description = value; },100);
        const tag = element('select'); tag.setAttribute('aria-label','Тип элемента');
        ['character','animal','prop','costume','scene','effect','others'].forEach((value,i) => { const option = element('option',['Персонаж','Животное','Предмет','Костюм','Сцена','Эффект','Другое'][i]); option.value=value; tag.append(option); }); tag.value=item.tag || 'character'; tag.addEventListener('change',()=>{item.tag=tag.value;}); block.append(tag);
        files(block,`Ракурсы ${item.name} · 2–4 фото`,'image/png,image/jpeg,image/webp',true,urls => { item.image_urls=[...(item.image_urls||[]),...urls]; delete item.video_url; });
        list(block,item.image_urls||[],i => item.image_urls.splice(i,1));
        files(block,`Видео ${item.name} · 3–8 сек, от 700 px`,'video/mp4,video/webm,video/quicktime',false,urls => { item.video_url=urls[0]; delete item.image_urls; item.tag='character'; });
        if (item.video_url) list(block,[item.video_url],()=>{delete item.video_url;});
        files(block,`Голос ${item.name} · 5–30 сек`,'audio/*',false,urls => {item.voice_url=urls[0];item.tag='character';});
        if(item.voice_url) list(block,[item.voice_url],()=>{delete item.voice_url;});
        button(block,'Удалить элемент',()=>{elements.splice(index,1);render();}); advanced.append(block);
      });
      if(elements.length<7) button(advanced,'Добавить элемент',()=>{elements.push({name:nextName(data,"Hero"),tag:'character'});render();});
      const voices=data.voices||(data.voices=[]);
      voices.forEach((item,index)=>{
        const block=element('fieldset'); block.append(element('legend',`Голос ${index+1}`));
        input(block,'Имя голоса для @ссылки',item.name,value=>{renamePrompt(item.name,value);item.name=value;});
        files(block,`Аудио ${item.name} · 5–30 сек`,'audio/*',false,urls=>{item.audio_url=urls[0];});
        if(item.audio_url) list(block,[item.audio_url],()=>{delete item.audio_url;});
        button(block,'Удалить голос',()=>{voices.splice(index,1);render();});advanced.append(block);
      });
      if(voices.length<3)button(advanced,'Добавить голос',()=>{voices.push({name:nextName(data,"Voice"),audio_url:''});render();});
    }
    const status=element('p');status.setAttribute('role','status');status.textContent=recipeError;panel.append(status);
  }
  async function intentFor(body) {
    const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(body)));
    const key='apix:kling4:studio:'+Array.from(new Uint8Array(digest),value=>value.toString(16).padStart(2,'0')).join('');
    let id=sessionStorage.getItem(key);if(!id){id=crypto.randomUUID();sessionStorage.setItem(key,id);} return {id,key};
  }
  window.fetch=async function(resource,init) {
    const url=typeof resource==='string'?resource:resource?.url||'';
    if(init?.method?.toUpperCase()==='POST' && /\/generate\/video(?:\/quote)?(?:\?|$)/.test(url) && typeof init.body==='string') {
      const body=JSON.parse(init.body);
      if(isKling(body.model)) {
        if(repeatId && !recipeApplied)throw new Error(recipeError||'Подожди восстановления исходного заказа');
        if(uploading)throw new Error('Подожди завершения загрузки материалов');
        body.kling4=structuredClone(drafts.get(body.model)||{});
        body.image_url=null;body.reference_urls=[];body.video_url=null;body.audio_ids=[];body.character_ids=[];body.seed=null;
        body.video_start=0;body.video_end=null;
        const launch=!/\/quote(?:\?|$)/.test(url); const intent=launch?await intentFor(body):null;
        if(intent)body.intent_id=intent.id;
        const response=await originalFetch(resource,{...init,body:JSON.stringify(body)});
        if(intent && response.ok)sessionStorage.removeItem(intent.key);
        return response;
      }
    }
    return originalFetch(resource,init);
  };
  function sync() {
    const select=document.querySelector('[data-account-model-select]');
    if(select)for(const option of Array.from(select.options)) {
      if(option.value===REFERENCE && option.textContent!=='Kling 4')option.textContent='Kling 4';
      if(option.value===KEYFRAME && !repeatId)option.remove();
    }
    const owner = currentOwner();
    if(draftOwner !== null && draftOwner !== owner) {
      uploadController?.abort();
      drafts.clear(); recipeApplied=false; renderedModel='';
      if(restoredRecipe?.owner_id && String(restoredRecipe.owner_id)!==owner)restoredRecipe=null;
      if(panel){panel.remove();panel=null;}
    }
    draftOwner=owner;
    if(restoredRecipe?.owner_id && String(restoredRecipe.owner_id)!==owner) return;
    if(restoredRecipe && !recipeApplied && currentKey()===restoredRecipe.model) {
      const form=document.querySelector('.account-composer');
      if(form?.querySelector('[name=duration]')?.options.length) {
        recipeApplied=true;drafts.set(restoredRecipe.model,structuredClone(restoredRecipe.kling4));
        for(const [field,value] of Object.entries({prompt:restoredRecipe.prompt,duration:restoredRecipe.kling4.duration,resolution:restoredRecipe.kling4.resolution,aspect_ratio:restoredRecipe.kling4.aspect_ratio||'auto'})) {
          const input=form.querySelector(`[name="${field}"]`);if(input){input.value=String(value);input.dispatchEvent(new Event(field==='prompt'?'input':'change',{bubbles:true}));}
        }
        render();
      }
    }
    if(currentKey()!==renderedModel || !panel?.isConnected)render();
    if(!isKling(currentKey())) {
      const prompt=document.querySelector('.account-composer [name=prompt]');
      if(prompt?.dataset.kling4Max!==undefined){const original=prompt.dataset.kling4Max;if(original)prompt.setAttribute('maxlength',original);else prompt.removeAttribute('maxlength');delete prompt.dataset.kling4Max;}
      document.querySelectorAll('[data-kling4-hidden]').forEach(node => { node.style.display=node.dataset.kling4Hidden; delete node.dataset.kling4Hidden; });
      return;
    }
    const form=document.querySelector('.account-composer');
    for(const selector of ['[data-reference-section]','[data-video-trim-row]','[data-video-identity-row]']) {
      const node=form?.querySelector(selector);if(node && node.style.display!=='none'){node.dataset.kling4Hidden=node.style.display;node.style.display='none';}
    }
    const prompt=form?.querySelector('[name=prompt]');if(prompt && prompt.maxLength!==8000){if(prompt.dataset.kling4Max===undefined)prompt.dataset.kling4Max=prompt.getAttribute('maxlength')||'';prompt.maxLength=8000;};
  }
  document.addEventListener('change',()=>queueMicrotask(sync));
  new MutationObserver(()=>queueMicrotask(sync)).observe(document.documentElement,{childList:true,subtree:true});
  sync();
})();
