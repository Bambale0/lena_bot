const demoScenarios = {
  image: {
    command: "Изображение",
    bubbles: [
      { type: "user", text: "Киберпанк-портрет в неоновом свете, детальная кожа, cinematic lighting." },
      { type: "bot", text: "Готовлю изображение. Выберите стиль, формат и модель. Результат появится в истории." },
      { type: "result", text: "Готово: можно сохранить, улучшить промпт, повторить генерацию или отправить работу в ленту." },
    ],
  },
  video: {
    command: "Видео",
    bubbles: [
      { type: "user", text: "Короткий ролик: неоновый логотип раскрывается из частиц, камера плавно приближается." },
      { type: "bot", text: "Запускаю генерацию видео. После обработки файл будет доступен в чате и истории." },
      { type: "result", text: "Видео готово. Можно вернуться к нему позже, повторить сценарий или сделать новую версию." },
    ],
  },
  music: {
    command: "Музыка",
    bubbles: [
      { type: "user", text: "Энергичный synthwave-трек для презентации AI-продукта, 30 секунд." },
      { type: "bot", text: "Создаю музыкальный вариант. Можно использовать как основу для Reels, Shorts и промо." },
      { type: "result", text: "Трек готов. Сохранён в истории, чтобы быстро вернуться к нему в следующем проекте." },
    ],
  },
  assistant: {
    command: "/assistant",
    bubbles: [
      { type: "user", text: "Улучши промпт для фэшн-кадра в неоновом свете." },
      { type: "bot", text: "Добавь объект, камеру, материал, свет и запреты. Например: editorial fashion portrait, wet asphalt reflections, cyan-magenta rim light, 85mm, clean skin texture." },
      { type: "result", text: "Промпт готов к запуску в Фото или Midjourney. При необходимости проверю модерационные риски." },
    ],
  },
}

const navToggle = document.querySelector(".nav-toggle")
const siteNav = document.querySelector(".site-nav")

function closeNav() {
  if (!navToggle || !siteNav) return
  siteNav.classList.remove("is-open")
  navToggle.setAttribute("aria-expanded", "false")
}

if (navToggle && siteNav) {
  navToggle.addEventListener("click", () => {
    const isOpen = siteNav.classList.toggle("is-open")
    navToggle.setAttribute("aria-expanded", String(isOpen))
  })

  siteNav.addEventListener("click", (event) => {
    if (event.target instanceof HTMLAnchorElement) closeNav()
  })

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeNav()
  })

  document.addEventListener("click", (event) => {
    if (!siteNav.classList.contains("is-open")) return
    if (event.target instanceof Node && !siteNav.contains(event.target) && !navToggle.contains(event.target)) {
      closeNav()
    }
  })
}

const chatStream = document.getElementById("chat-stream")
const demoCommand = document.getElementById("demo-command")
const demoButtons = Array.from(document.querySelectorAll("[data-demo]"))
const rerunDemo = document.querySelector("[data-rerun-demo]")
let activeDemo = "image"

function renderDemo(key = activeDemo) {
  if (!chatStream || !demoScenarios[key]) return
  activeDemo = key
  const scenario = demoScenarios[key]
  chatStream.innerHTML = ""
  if (demoCommand) demoCommand.textContent = scenario.command
  demoButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.demo === key))

  scenario.bubbles.forEach((bubble, index) => {
    window.setTimeout(() => {
      const node = document.createElement("div")
      node.className = `bubble ${bubble.type}`
      node.textContent = bubble.text
      chatStream.appendChild(node)
    }, index * 240)
  })
}

demoButtons.forEach((button) => {
  button.addEventListener("click", () => renderDemo(button.dataset.demo))
})

if (rerunDemo) {
  rerunDemo.addEventListener("click", () => renderDemo(activeDemo))
}

renderDemo("image")

const commandCards = Array.from(document.querySelectorAll(".command-card"))
const commandResponse = document.getElementById("command-response")
const copyToast = document.getElementById("copy-toast")
let copyToastTimer

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text)
    return
  }
  const textarea = document.createElement("textarea")
  textarea.value = text
  textarea.style.position = "fixed"
  textarea.style.opacity = "0"
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand("copy")
  textarea.remove()
}

function showToast(message) {
  if (!copyToast) return
  copyToast.textContent = message
  copyToast.classList.add("is-visible")
  window.clearTimeout(copyToastTimer)
  copyToastTimer = window.setTimeout(() => copyToast.classList.remove("is-visible"), 1500)
}

commandCards.forEach((card) => {
  card.addEventListener("click", async () => {
    const command = card.dataset.command || ""
    const response = card.dataset.response || "{}"
    commandCards.forEach((item) => item.classList.toggle("is-active", item === card))
    if (commandResponse) {
      try {
        commandResponse.textContent = JSON.stringify({ command, ...JSON.parse(response) }, null, 2)
      } catch {
        commandResponse.textContent = response
      }
    }
    try {
      if (command) await copyText(command)
      showToast(command ? "Команда скопирована" : "Сценарий открыт")
    } catch {
      showToast("Не удалось скопировать")
    }
  })
})

const accordionItems = Array.from(document.querySelectorAll(".faq-item"))

accordionItems.forEach((item, index) => {
  const button = item.querySelector("button")
  item.classList.toggle("is-open", index === 0)
  if (!button) return
  button.addEventListener("click", () => {
    const nextState = !item.classList.contains("is-open")
    accordionItems.forEach((entry) => {
      entry.classList.remove("is-open")
      const entryButton = entry.querySelector("button")
      if (entryButton) entryButton.setAttribute("aria-expanded", "false")
    })
    item.classList.toggle("is-open", nextState)
    button.setAttribute("aria-expanded", String(nextState))
  })
})

const contactForm = document.getElementById("contact-form")
const formStatus = document.getElementById("form-status")

function setError(field, message) {
  const wrapper = field.closest("div")
  const error = wrapper ? wrapper.querySelector(".field-error") : null
  if (error) error.textContent = message
}

function validateContactForm(form) {
  let valid = true
  const name = form.elements.name
  const contact = form.elements.contact
  const message = form.elements.message

  setError(name, "")
  setError(contact, "")
  setError(message, "")

  if (!name.value.trim() || name.value.trim().length < 2) {
    setError(name, "Напишите имя хотя бы из двух символов.")
    valid = false
  }

  const contactValue = contact.value.trim()
  const looksLikeTelegram = /^@[a-zA-Z0-9_]{5,}$/.test(contactValue)
  const looksLikeEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contactValue)
  if (!looksLikeTelegram && !looksLikeEmail) {
    setError(contact, "Укажите Telegram в формате @username или email.")
    valid = false
  }

  if (!message.value.trim() || message.value.trim().length < 20) {
    setError(message, "Добавьте детали: модель, время, что ожидали получить.")
    valid = false
  }

  return valid
}

if (contactForm) {
  contactForm.addEventListener("submit", (event) => {
    event.preventDefault()
    if (!validateContactForm(contactForm)) {
      if (formStatus) formStatus.textContent = ""
      return
    }
    if (formStatus) {
      formStatus.textContent = "Спасибо! Сообщение подготовлено. Мы свяжемся с вами через указанные контакты."
    }
    contactForm.reset()
  })
}

(() => {
  const root = document.querySelector("[data-account-app]")
  if (!root) return

  const API_BASE = "/api/v1"
  const TOKEN_KEY = "apix-web-auth-token"
  const state = {
    token: window.localStorage.getItem(TOKEN_KEY) || "",
    user: null,
    models: { image: [], video: [], music: [] },
    history: [],
    plans: [],
    assistantHistory: [],
    activeKind: "image",
    selectedPrompt: null,
    isSubmitting: false,
  }

  const $ = (selector) => document.querySelector(selector)
  const alertBox = $("#web-alert")
  const dashboard = $("#web-dashboard")
  const accountTitle = $("#account-title")
  const userPill = $("#web-user-pill")
  const logoutButtons = Array.from(document.querySelectorAll("[data-logout]"))
  const studioForm = $("#studio-form")
  const promptSubmitForm = $("#prompt-submit-form")
  const withdrawalForm = $("#withdrawal-form")
  const assistantForm = $("#assistant-form")
  const resultBox = $("#generation-result")
  const estimateBox = $("#generation-estimate")
  const selectedPromptNote = $("#selected-prompt-note")
  const startGenerationButton = document.querySelector("[data-start-generation]")

  function telegramInitData() {
    return window.Telegram?.WebApp?.initData || ""
  }

  function headers(json = true) {
    const result = {}
    if (json) result["Content-Type"] = "application/json"
    if (telegramInitData()) result["X-Telegram-Init-Data"] = telegramInitData()
    if (state.token) result["X-Web-Auth-Token"] = state.token
    return result
  }

  async function api(path, options = {}) {
    const json = options.body instanceof FormData ? false : options.json !== false
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        ...headers(json),
        ...(options.headers || {}),
      },
    })
    if (!response.ok) {
      let detail = `Ошибка API ${response.status}`
      try {
        const payload = await response.json()
        detail = payload.detail || detail
      } catch {}
      throw new Error(detail)
    }
    if (response.status === 204) return null
    return response.json()
  }

  function showAlert(message, tone = "info") {
    if (!alertBox) return
    alertBox.hidden = !message
    alertBox.textContent = message || ""
    alertBox.dataset.tone = tone
  }

  function fmt(value) {
    const num = Number(value || 0)
    if (!Number.isFinite(num)) return "0"
    return Number.isInteger(num) ? String(num) : String(Number(num.toFixed(2)))
  }

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    })[char])
  }

  function safeUrl(value) {
    const raw = String(value || "").trim()
    if (!raw) return ""
    try {
      const url = new URL(raw, window.location.origin)
      if (url.protocol === "http:" || url.protocol === "https:") return esc(raw)
    } catch {}
    return ""
  }

  function displayName(user) {
    if (!user) return "Нет входа"
    return user.username ? `@${user.username}` : user.full_name || `ID ${user.tg_id}`
  }

  function modelPriceLabel(model, kind) {
    const price = model.is_per_second ? `${fmt(model.credits_per_sec || model.credits)} кр/сек` : `${fmt(model.credits)} кр`
    return `${model.display_name || model.key} · ${price}${kind === "video" && model.durations?.length ? " · видео" : ""}`
  }

  function currentModels() {
    return state.models[state.activeKind] || []
  }

  function currentModel() {
    if (!studioForm) return null
    const key = studioForm.elements.model?.value
    return currentModels().find((model) => model.key === key) || null
  }

  function replaceOptions(select, options, fallbackLabel = "По умолчанию") {
    if (!select) return
    select.innerHTML = ""
    const normalized = (options || []).filter((option) => option && option.value !== undefined && option.value !== null)
    if (!normalized.length) {
      const option = document.createElement("option")
      option.value = ""
      option.textContent = fallbackLabel
      select.appendChild(option)
      return
    }
    for (const item of normalized) {
      const option = document.createElement("option")
      option.value = item.value
      option.textContent = item.label || item.value
      select.appendChild(option)
    }
  }

  function estimateCredits() {
    const model = currentModel()
    if (!model || !studioForm) return 0
    if (state.activeKind === "video") {
      const duration = Number(studioForm.elements.duration?.value || model.durations?.[0] || 5)
      const rate = Number(model.credits_per_sec || model.credits || 0)
      return model.is_per_second ? duration * rate : Number(model.credits || 0)
    }
    if (state.activeKind === "image") {
      const quality = studioForm.elements.quality?.value || "basic"
      return Number(model.quality_prices?.[quality] ?? model.credits ?? 0)
    }
    return Number(model.credits || 0)
  }

  function updateSelectedPromptNote() {
    if (!selectedPromptNote) return
    if (!state.selectedPrompt) {
      selectedPromptNote.hidden = true
      selectedPromptNote.textContent = ""
      return
    }
    selectedPromptNote.hidden = false
    selectedPromptNote.innerHTML = `Промпт из библиотеки: <b>${esc(state.selectedPrompt.title || `#${state.selectedPrompt.id}`)}</b>. Вознаграждение автору будет рассчитано после генерации.`
  }

  function updateEstimate() {
    if (!estimateBox) return
    const model = currentModel()
    if (!model) {
      estimateBox.textContent = "Выберите модель, чтобы увидеть стоимость."
      updateSelectedPromptNote()
      return
    }
    const credits = estimateCredits()
    const balance = Number(state.user?.credits || 0)
    const suffix = balance ? ` · баланс ${fmt(balance)} кр` : ""
    const warning = balance && credits > balance ? " · нужно пополнить баланс" : ""
    estimateBox.innerHTML = `Итоговая стоимость: <b>${fmt(credits)} кр</b>${suffix}${warning}`
    updateSelectedPromptNote()
  }

  function syncModelControls() {
    if (!studioForm) return
    const model = currentModel()
    const isImage = state.activeKind === "image"
    const isVideo = state.activeKind === "video"
    const isMusic = state.activeKind === "music"

    const aspectOptions = [{ value: "", label: "По умолчанию" }].concat((model?.aspect_ratios || []).map((value) => ({ value, label: value })))
    replaceOptions(studioForm.elements.aspect_ratio, aspectOptions)

    if (isImage && model?.quality_options?.length) {
      replaceOptions(studioForm.elements.quality, model.quality_options)
    } else {
      replaceOptions(studioForm.elements.quality, [{ value: "basic", label: "Basic" }])
    }

    replaceOptions(
      studioForm.elements.count,
      (isImage ? (model?.counts || [1]) : [1]).map((value) => ({ value: String(value), label: String(value) })),
    )
    replaceOptions(
      studioForm.elements.duration,
      (isVideo ? (model?.durations || [5]) : [5]).map((value) => ({ value: String(value), label: `${value} сек` })),
    )

    studioForm.elements.aspect_ratio.disabled = isMusic || !(model?.aspect_ratios || []).length
    studioForm.elements.quality.disabled = !isImage || !(model?.quality_options || []).length
    studioForm.elements.count.disabled = !isImage
    studioForm.elements.duration.disabled = !isVideo
    studioForm.elements.reference_url.disabled = isMusic
    studioForm.elements.reference_file.disabled = isMusic
    studioForm.elements.instrumental.disabled = !isMusic

    updateEstimate()
  }

  function setLoggedIn(user) {
    state.user = user
    if (dashboard) dashboard.hidden = false
    if (accountTitle) accountTitle.textContent = `Кабинет ${displayName(user)}`
    if (userPill) userPill.textContent = `${displayName(user)} · ${fmt(user.credits)} кр`
    logoutButtons.forEach((button) => { button.hidden = false })
  }

  function setLoggedOut() {
    state.user = null
    if (dashboard) dashboard.hidden = true
    if (accountTitle) accountTitle.textContent = "Войдите, чтобы открыть студию"
    if (userPill) userPill.textContent = "Нет входа"
    logoutButtons.forEach((button) => { button.hidden = true })
  }

  function renderTelegramLogin(botUsername) {
    const slot = $("#telegram-login-slot")
    if (!slot || !botUsername) return
    slot.innerHTML = ""
    const script = document.createElement("script")
    script.async = true
    script.src = "https://telegram.org/js/telegram-widget.js?22"
    script.setAttribute("data-telegram-login", botUsername)
    script.setAttribute("data-size", "large")
    script.setAttribute("data-radius", "12")
    script.setAttribute("data-userpic", "true")
    script.setAttribute("data-request-access", "write")
    script.setAttribute("data-onauth", "onTelegramAuth(user)")
    slot.appendChild(script)
  }

  window.onTelegramAuth = async (telegramUser) => {
    try {
      showAlert("Проверяем вход через Telegram...")
      const payload = await api("/auth/telegram-login", {
        method: "POST",
        body: JSON.stringify(telegramUser),
      })
      state.token = payload.token
      window.localStorage.setItem(TOKEN_KEY, state.token)
      setLoggedIn(payload.user)
      await loadAccount()
      showAlert("Готово: сайт подключён к вашему аккаунту Telegram.", "success")
    } catch (error) {
      showAlert(error.message, "danger")
    }
  }

  async function uploadReference(file) {
    if (!file || !file.size) return ""
    const form = new FormData()
    form.append("file", file)
    const response = await fetch("/upload", {
      method: "POST",
      headers: headers(false),
      body: form,
    })
    if (!response.ok) throw new Error("Не удалось загрузить референс")
    const payload = await response.json()
    return payload.url || ""
  }

  function renderModels(kind) {
    if (!studioForm) return
    const modelSelect = studioForm.elements.model
    modelSelect.innerHTML = ""
    for (const model of state.models[kind] || []) {
      const option = document.createElement("option")
      option.value = model.key
      option.textContent = modelPriceLabel(model, kind)
      modelSelect.appendChild(option)
    }
    if (!modelSelect.options.length) {
      const option = document.createElement("option")
      option.value = ""
      option.textContent = "Модели не загружены"
      modelSelect.appendChild(option)
    }
    studioForm.dataset.kind = kind
    syncModelControls()
  }

  function renderBalance() {
    const stats = $("#balance-stats")
    const plansGrid = $("#plans-grid")
    if (stats && state.user) {
      stats.innerHTML = `
        <div><b>${fmt(state.user.credits)}</b><span>кредитов</span></div>
        <div><b>${fmt(state.user.referral_balance)} ₽</b><span>реферальный баланс</span></div>
        <div><b>${state.user.language || "ru"}</b><span>язык</span></div>
      `
    }
    if (!plansGrid) return
    plansGrid.innerHTML = state.plans.map((plan) => `
      <article class="plan-card">
        <h4>${esc(plan.title || plan.label)}</h4>
        <b>${fmt(plan.credits)} кр</b>
        <p>${esc(plan.price_rub_display || `${fmt(plan.price_rub)} ₽`)} · ${fmt(plan.price_usdt)} USDT · ${fmt(plan.price_stars)} ⭐</p>
        <div>
          <button type="button" data-pay="tbank" data-plan="${plan.key}">Карта</button>
          <button type="button" data-pay="crypto" data-plan="${plan.key}">Crypto</button>
          <button type="button" data-pay="stars" data-plan="${plan.key}">Stars</button>
        </div>
      </article>
    `).join("") || "<p class=\"empty-state\">Планы пока не загружены.</p>"
    updateEstimate()
  }

  function mediaHtml(item) {
    const url = safeUrl(item.result_url)
    if (!url) return ""
    if (item.gen_type === "video" || /\.(mp4|mov|webm)$/i.test(url)) return `<video src="${url}" controls playsinline></video>`
    if (item.gen_type === "music" || /\.(mp3|wav|ogg)$/i.test(url)) return `<audio src="${url}" controls></audio>`
    return `<img src="${url}" alt="" loading="lazy" />`
  }

  function renderHistory() {
    const grid = $("#history-grid")
    if (!grid) return
    grid.innerHTML = state.history.map((item) => `
      <article class="history-card">
        ${mediaHtml(item)}
        <div>
          <span>${esc(item.gen_type)} · ${esc(item.status)}</span>
          <h4>${esc(item.model)}</h4>
          <p>${esc(item.prompt || "")}</p>
          <small>${fmt(item.credits_spent)} кр · ${item.created_at ? esc(new Date(item.created_at).toLocaleString("ru-RU")) : ""}</small>
          <div class="card-actions">
            ${safeUrl(item.result_url) ? `<a href="${safeUrl(item.result_url)}" target="_blank" rel="noopener noreferrer">Открыть</a>` : ""}
            <button type="button" data-publish="${item.id}">Опубликовать</button>
          </div>
        </div>
      </article>
    `).join("") || "<p class=\"empty-state\">История пока пустая.</p>"
  }

  async function renderPrompts() {
    const grid = $("#prompts-grid")
    if (!grid) return
    try {
      const payload = await api("/prompts?limit=12")
      const prompts = Array.isArray(payload.items) ? payload.items : []
      grid.innerHTML = prompts.map((prompt) => `
        <article class="prompt-card">
          ${safeUrl(prompt.preview_url) ? `<img src="${safeUrl(prompt.preview_url)}" alt="" loading="lazy" />` : ""}
          <h4>${esc(prompt.title)}</h4>
          <p>${esc(prompt.description || prompt.prompt_text)}</p>
          <small>${esc(prompt.category)} · ${fmt(prompt.likes || 0)} лайков · ${fmt(prompt.uses_count || 0)} запусков</small>
          <div class="card-actions">
            <button type="button" data-use-prompt="${prompt.id}">В студию</button>
            <button type="button" data-like-prompt="${prompt.id}">Лайк</button>
          </div>
        </article>
      `).join("") || "<p class=\"empty-state\">Промпты пока не найдены.</p>"
    } catch (error) {
      grid.innerHTML = `<p class="empty-state">${esc(error.message)}</p>`
    }
  }

  async function renderFeed() {
    const grid = $("#feed-grid")
    if (!grid) return
    try {
      const feed = await api("/feed?limit=12")
      grid.innerHTML = feed.map((item) => `
        <article class="feed-card">
          ${safeUrl(item.result_url) ? `<img src="${safeUrl(item.result_url)}" alt="" loading="lazy" />` : ""}
          <h4>${esc(item.author)}</h4>
          <p>${fmt(item.likes_count || 0)} лайков · ${fmt(item.remixes || 0)} ремиксов</p>
          <div class="card-actions">
            <button type="button" data-like-feed="${item.id}">Лайк</button>
            <button type="button" data-remix-feed="${item.id}">Ремикс</button>
          </div>
        </article>
      `).join("") || "<p class=\"empty-state\">Лента пока пустая.</p>"
    } catch (error) {
      grid.innerHTML = `<p class="empty-state">${esc(error.message)}</p>`
    }
  }

  async function renderReferrals() {
    const box = $("#referral-box")
    if (!box) return
    try {
      const data = await api("/referrals")
      box.innerHTML = `
        <div class="referral-link"><input readonly value="${esc(data.referral_link || "")}" /><button type="button" data-copy-ref>Копировать</button></div>
        <div class="stat-row">
          <div><b>${data.counts.l1}</b><span>уровень 1</span></div>
          <div><b>${data.counts.l2}</b><span>уровень 2</span></div>
          <div><b>${data.counts.l3}</b><span>уровень 3</span></div>
          <div><b>${fmt(data.balance.available_to_withdraw)} ₽</b><span>доступно</span></div>
        </div>
        <p>Комиссии: ${Math.round(data.commission_l1 * 100)}% / ${Math.round(data.commission_l2 * 100)}% / ${Math.round(data.commission_l3 * 100)}%. Бонус за L1: ${fmt(data.bonus_l1_credits)} кр.</p>
      `
    } catch (error) {
      box.innerHTML = `<p class="empty-state">${esc(error.message)}</p>`
    }
  }

  async function refreshMe() {
    state.user = await api("/me")
    setLoggedIn(state.user)
  }

  async function loadAccount() {
    await refreshMe()
    const [image, video, music, history, plans] = await Promise.all([
      api("/models/image"),
      api("/models/video"),
      api("/models/music"),
      api("/history?limit=24"),
      api("/plans"),
    ])
    state.models = { image, video, music }
    state.history = history
    state.plans = plans
    renderModels(state.activeKind)
    renderBalance()
    renderHistory()
    await Promise.all([renderPrompts(), renderFeed(), renderReferrals()])
  }

  async function pollGeneration(id) {
    let last
    for (let attempt = 0; attempt < 45; attempt += 1) {
      last = await api(`/generations/${id}`)
      resultBox.innerHTML = `<b>${esc(last.status)}</b><p>${esc(last.prompt)}</p>${mediaHtml(last)}`
      if (last.status === "done" || last.status === "failed") break
      await new Promise((resolve) => window.setTimeout(resolve, 4000))
    }
    await loadAccount()
    return last
  }

  async function startGeneration(event) {
    event.preventDefault()
    if (!studioForm) return
    if (state.isSubmitting) return
    const data = new FormData(studioForm)
    const kind = data.get("kind")
    const prompt = String(data.get("prompt") || "").trim()
    const model = String(data.get("model") || "")
    if (!prompt || !model) return
    state.isSubmitting = true
    if (startGenerationButton) {
      startGenerationButton.disabled = true
      startGenerationButton.textContent = "Запускаем..."
    }
    try {
      showAlert("Запускаем генерацию...")
      if (resultBox) resultBox.innerHTML = "<p>Задача отправляется в генератор.</p>"
      const uploadedReference = await uploadReference(data.get("reference_file"))
      const referenceUrl = uploadedReference || String(data.get("reference_url") || "").trim()
      let payload
      if (kind === "music") {
        payload = await api("/generate/music", {
          method: "POST",
          body: JSON.stringify({ prompt, instrumental: Boolean(data.get("instrumental")) }),
        })
      } else if (kind === "video") {
        payload = await api("/generate/video", {
          method: "POST",
          body: JSON.stringify({
            model,
            prompt,
            mode: referenceUrl ? "image" : "text",
            duration: Number(data.get("duration") || 5),
            aspect_ratio: data.get("aspect_ratio") || null,
            image_url: referenceUrl || null,
          }),
        })
      } else {
        payload = await api("/generate/image", {
          method: "POST",
          body: JSON.stringify({
            model,
            prompt,
            aspect_ratio: data.get("aspect_ratio") || null,
            quality: data.get("quality") || "basic",
            count: Number(data.get("count") || 1),
            reference_url: referenceUrl || null,
            prompt_id: state.selectedPrompt?.id || null,
          }),
        })
      }
      showAlert(`Генерация #${payload.id} запущена. Баланс обновится после статуса.`, "success")
      await pollGeneration(payload.id)
      state.selectedPrompt = null
      updateSelectedPromptNote()
    } catch (error) {
      showAlert(error.message, "danger")
      if (resultBox) resultBox.innerHTML = `<p>${esc(error.message)}</p>`
    } finally {
      state.isSubmitting = false
      if (startGenerationButton) {
        startGenerationButton.disabled = false
        startGenerationButton.textContent = "Запустить генерацию"
      }
      updateEstimate()
    }
  }

  async function improvePrompt() {
    if (!studioForm) return
    const prompt = studioForm.elements.prompt.value.trim()
    if (!prompt) return
    try {
      const payload = await api("/prompt/improve", {
        method: "POST",
        body: JSON.stringify({ prompt, kind: studioForm.elements.kind.value }),
      })
      studioForm.elements.prompt.value = payload.prompt || prompt
      showAlert("Промпт улучшен.", "success")
    } catch (error) {
      showAlert(error.message, "danger")
    }
  }

  async function handlePayment(provider, planKey) {
    try {
      const endpoint = provider === "stars" ? "/topup/stars" : provider === "crypto" ? "/topup/crypto" : "/topup/tbank"
      const payload = await api(endpoint, { method: "POST", body: JSON.stringify({ plan_key: planKey }) })
      const url = payload.pay_url || payload.invoice_link
      if (url) window.open(url, "_blank", "noopener,noreferrer")
      showAlert("Счёт создан. После оплаты баланс обновится автоматически.", "success")
    } catch (error) {
      showAlert(error.message, "danger")
    }
  }

  async function sendAssistant(event) {
    event.preventDefault()
    const message = assistantForm.elements.message.value.trim()
    if (!message) return
    const log = $("#assistant-log")
    state.assistantHistory.push({ role: "user", content: message })
    if (log) log.innerHTML += `<div class="assistant-msg user">${esc(message)}</div>`
    assistantForm.reset()
    try {
      const payload = await api("/assistant", {
        method: "POST",
        body: JSON.stringify({ message, history: state.assistantHistory.slice(-10) }),
      })
      state.assistantHistory.push({ role: "assistant", content: payload.reply })
      if (log) log.innerHTML += `<div class="assistant-msg">${esc(payload.reply)}</div>`
    } catch (error) {
      showAlert(error.message, "danger")
    }
  }

  document.addEventListener("click", async (event) => {
    const target = event.target
    if (!(target instanceof HTMLElement)) return
    const tab = target.closest("[data-account-tab]")
    if (tab) {
      const key = tab.dataset.accountTab
      document.querySelectorAll("[data-account-tab]").forEach((button) => button.classList.toggle("is-active", button === tab))
      document.querySelectorAll("[data-account-panel]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.accountPanel === key))
    }
    const pay = target.closest("[data-pay]")
    if (pay) await handlePayment(pay.dataset.pay, pay.dataset.plan)
    const publish = target.closest("[data-publish]")
    if (publish) {
      try {
        const payload = await api(`/generations/${publish.dataset.publish}/publish`, { method: "POST" })
        if (payload.link) {
          try {
            await navigator.clipboard?.writeText(payload.link)
            showAlert(`Работа опубликована. Ссылка скопирована: ${payload.link}`, "success")
          } catch {
            showAlert(`Работа опубликована. Ссылка: ${payload.link}`, "success")
          }
        } else {
          showAlert("Работа опубликована в ленте и библиотеке.", "success")
        }
        await loadAccount()
      } catch (error) {
        showAlert(error.message, "danger")
      }
    }
    const usePrompt = target.closest("[data-use-prompt]")
    if (usePrompt) {
      try {
        const payload = await api(`/prompts/${usePrompt.dataset.usePrompt}/use`, { method: "POST" })
        state.selectedPrompt = payload.prompt
        studioForm.elements.prompt.value = payload.prompt.prompt_text
        studioForm.elements.kind.value = "image"
        state.activeKind = "image"
        renderModels(state.activeKind)
        document.querySelector("[data-account-tab='studio']")?.click()
        showAlert("Промпт загружен в студию.", "success")
      } catch (error) {
        showAlert(error.message, "danger")
      }
    }
    const likePrompt = target.closest("[data-like-prompt]")
    if (likePrompt) {
      await api(`/prompts/${likePrompt.dataset.likePrompt}/like`, { method: "POST" }).catch((error) => showAlert(error.message, "danger"))
      await renderPrompts()
    }
    const likeFeed = target.closest("[data-like-feed]")
    if (likeFeed) {
      await api(`/feed/${likeFeed.dataset.likeFeed}/like`, { method: "POST" }).catch((error) => showAlert(error.message, "danger"))
      await renderFeed()
    }
    const remixFeed = target.closest("[data-remix-feed]")
    if (remixFeed) {
      const imageModel = state.models.image[0]
      if (!imageModel) return
      try {
        const payload = await api(`/feed/${remixFeed.dataset.remixFeed}/remix`, {
          method: "POST",
          body: JSON.stringify({ model: imageModel.key, mode: "image", count: 1, quality: "basic" }),
        })
        showAlert(`Ремикс #${payload.id} запущен.`, "success")
        await pollGeneration(payload.id)
      } catch (error) {
        showAlert(error.message, "danger")
      }
    }
    if (target.closest("[data-copy-ref]")) {
      const input = document.querySelector(".referral-link input")
      if (input) navigator.clipboard?.writeText(input.value)
      showAlert("Реферальная ссылка скопирована.", "success")
    }
    if (target.closest("[data-refresh-account]")) {
      await loadAccount().catch((error) => showAlert(error.message, "danger"))
    }
  })

  logoutButtons.forEach((button) => {
    button.addEventListener("click", () => {
      state.token = ""
      window.localStorage.removeItem(TOKEN_KEY)
      setLoggedOut()
      showAlert("Вы вышли из веб-кабинета.")
    })
  })

  studioForm?.elements.kind?.addEventListener("change", (event) => {
    state.activeKind = event.target.value
    if (state.activeKind !== "image") {
      state.selectedPrompt = null
    }
    renderModels(state.activeKind)
  })
  studioForm?.elements.model?.addEventListener("change", syncModelControls)
  studioForm?.elements.aspect_ratio?.addEventListener("change", updateEstimate)
  studioForm?.elements.quality?.addEventListener("change", updateEstimate)
  studioForm?.elements.count?.addEventListener("change", updateEstimate)
  studioForm?.elements.duration?.addEventListener("change", updateEstimate)
  studioForm?.elements.prompt?.addEventListener("input", () => {
    if (!state.selectedPrompt) return
    if (studioForm.elements.prompt.value !== state.selectedPrompt.prompt_text) {
      state.selectedPrompt = null
      updateSelectedPromptNote()
    }
  })
  studioForm?.addEventListener("submit", startGeneration)
  document.querySelector("[data-improve-prompt]")?.addEventListener("click", improvePrompt)

  promptSubmitForm?.addEventListener("submit", async (event) => {
    event.preventDefault()
    const data = new FormData(promptSubmitForm)
    try {
      await api("/prompts", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(data.entries())),
      })
      promptSubmitForm.reset()
      showAlert("Промпт отправлен на модерацию.", "success")
      await renderPrompts()
    } catch (error) {
      showAlert(error.message, "danger")
    }
  })

  withdrawalForm?.addEventListener("submit", async (event) => {
    event.preventDefault()
    const data = new FormData(withdrawalForm)
    try {
      await api("/referrals/withdrawals", {
        method: "POST",
        body: JSON.stringify({
          amount_rub: Number(data.get("amount_rub") || 0),
          payout_details: String(data.get("payout_details") || ""),
        }),
      })
      withdrawalForm.reset()
      showAlert("Заявка на вывод создана.", "success")
      await renderReferrals()
    } catch (error) {
      showAlert(error.message, "danger")
    }
  })

  assistantForm?.addEventListener("submit", sendAssistant)

  async function init() {
    try {
      const config = await api("/auth/config", { json: false })
      renderTelegramLogin(config.bot_username || "apix_ai_bot")
    } catch {
      renderTelegramLogin("apix_ai_bot")
    }
    if (state.token || telegramInitData()) {
      try {
        await loadAccount()
        showAlert("Кабинет готов.", "success")
      } catch (error) {
        setLoggedOut()
        showAlert("Войдите через Telegram, чтобы открыть реальные данные аккаунта.")
      }
    } else {
      setLoggedOut()
    }
  }

  init()
})()
