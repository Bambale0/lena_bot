const translations = {
  ru: {
    nav: { features: "Возможности", examples: "Примеры", models: "Модели", how: "Как это работает", pricing: "Цены", channel: "Канал", cta: "Открыть бота" },
    hero: {
      badge: "Генерация изображений, видео и музыки в Telegram",
      titleStart: "Создавай изображения,",
      titleAccent: "видео и музыку",
      titleEnd: "в одном рабочем потоке",
      description: "APIX объединяет text-to-image, image edit, text-to-video, image-to-video, музыку через Suno, ленту работ и ремиксы внутри одного Telegram-бота.",
      primary: "Открыть в Telegram",
      secondary: "Запустить бота",
      channelBadge: "Telegram-канал",
      channelTitle: "LeluPromt",
      channelText: "Подборки промптов, визуальные референсы и идеи для генераций.",
      linkFeatures: "Возможности",
      linkExamples: "Примеры",
      linkModels: "Модели",
      linkHow: "Как это работает",
      linkPricing: "Цены",
    },
    panel: {
      eyebrow: "Что внутри",
      title: "Изображения, видео, музыка и ремиксы в одном боте",
      imageTitle: "Изображения",
      image: "text-to-image, edit, референсы и несколько моделей под разные задачи",
      videoTitle: "Видео",
      video: "ролики по тексту, image-to-video и motion-сценарии",
      musicTitle: "Музыка",
      music: "трек по описанию, инструментал или песня с настроением и жанром",
      feedTitle: "Лента",
      feed: "публичные работы, повтор удачных результатов и remix из ленты",
      live: "Цены без сюрпризов",
      liveText: "На сайте — те же тарифы, что и в боте. Без расхождений, устаревших цифр и лишних вопросов перед запуском.",
    },
    features: {
      title: "Сделано для реальных креативных задач",
      subtitle: "От первого промпта до серии вариаций, ремиксов и публикации без переключения между сервисами.",
      items: [
        { title: "Изображения под задачу", text: "Собирай рекламные key visual, фэшн-кадры, концепты, product shot и правки по референсу в одном потоке." },
        { title: "Видео из текста и фото", text: "Запускай короткие ролики по описанию, оживляй кадры и тестируй разные модели под стиль и бюджет." },
        { title: "Ремикс удачных работ", text: "Бери сильный результат из ленты или собственной серии и делай новую итерацию без старта с нуля." },
        { title: "Промпты и идеи", text: "Используй библиотеку промптов и разбор фото, чтобы быстрее находить точную формулировку под генерацию." },
        { title: "Музыка внутри APIX", text: "Генерируй треки по настроению, жанру, темпу и сценарию без отдельного музыкального сервиса." },
        { title: "Серии и повторяемость", text: "Сохраняй настройки, возвращайся к прошлым генерациям и собирай последовательные creative loops." },
      ],
    },
    examples: {
      title: "Примеры того, что можно сделать",
      subtitle: "Не абстрактные AI-обещания, а понятные задачи, которые можно запустить прямо в боте.",
      items: [
        {
          badge: "Изображение",
          title: "Собрать key visual для поста",
          text: "Пример: «cinematic beauty product shot, glass bottle, blue reflections, premium advertising, clean background».",
        },
        {
          badge: "Видео",
          title: "Оживить фото в короткий ролик",
          text: "Пример: загрузить фото персонажа и попросить «slow camera push-in, wind in hair, dramatic neon street, cinematic motion».",
        },
        {
          badge: "Музыка",
          title: "Сделать трек под moodboard",
          text: "Пример: «dark synthwave intro, female vocal, glossy fashion energy, 110 bpm, atmospheric chorus».",
        },
        {
          badge: "Ремикс",
          title: "Переделать удачную работу из ленты",
          text: "Пример: взять готовую генерацию и сделать новую версию «more realistic lighting, cleaner skin texture, luxury campaign style».",
        },
      ],
    },
    how: {
      title: "Как это работает",
      subtitle: "Быстрый путь от идеи до готового результата внутри Telegram.",
      items: [
        { title: "Открой APIX", text: "Зайди в Telegram-бота по ссылке с этого сайта." },
        { title: "Выбери сценарий", text: "Изображение, видео, музыка или ремикс от уже готовой работы в ленте." },
        { title: "Отправь промпт или фото", text: "Опиши задачу словами, загрузи референс или возьми существующий результат как основу." },
        { title: "Запусти и повторяй", text: "Получай результат, делай вариации, ремиксы, публикуй в ленту и собирай серию дальше." },
      ],
    },
    models: {
      title: "Модели внутри APIX",
      subtitle: "Ниже перечислены пользовательские модели, которые сейчас заведены в боте и доступны в продуктовых сценариях.",
      imageBadge: "Изображения",
      imageTitle: "Модели для изображений",
      videoBadge: "Видео",
      videoTitle: "Модели для видео",
      musicBadge: "Музыка",
      musicTitle: "Музыкальная модель",
      musicNote: "Музыкальный режим работает отдельно и использует генерацию треков внутри того же продукта.",
    },
    pricing: {
      title: "Прозрачные тарифы",
      subtitle: "Стоимость обновляется автоматически, поэтому перед запуском ты всегда видишь актуальную цену.",
      starter: {
        badge: "Старт",
        title: "15 бонусных кредитов",
        text: "Хватает, чтобы спокойно попробовать продукт в деле: собрать первую картинку, запустить видео, музыку или ремикс.",
        items: ["Доступ через Telegram-бота", "Изображения, видео, музыка и лента", "Промпты, референсы и remix-flow"],
        cta: "Открыть бота",
      },
      planCta: "Открыть бота",
      planMeta: "Актуальный тариф",
      planUsage: "Кредиты работают во всех режимах: изображения, видео, музыка и ремиксы",
    },
    cta: {
      title: "Готов запустить первый сценарий в APIX?",
      text: "Открой Telegram-бота, выбери режим и протестируй генерацию изображений, видео, музыки или ремиксов прямо сейчас.",
      primary: "Открыть бота",
      secondary: "Перейти в Telegram",
      channelLead: "Нужны идеи перед стартом?",
      channelLink: "Посмотреть канал с промптами",
      supportLead: "Нужен саппорт или разработка под задачу?",
      supportLink: "Написать разработчику",
    },
    footer: {
      copy: "Изображения, видео, музыка, референсы и ремиксы внутри одного Telegram-бота.",
      features: "Возможности",
      examples: "Примеры",
      models: "Модели",
      pricing: "Цены",
      channel: "Канал с промптами",
      supportLead: "Саппорт и вопросы по разработке:",
      supportLink: "@Chillcreative",
    },
  },
  en: {
    nav: { features: "Features", examples: "Examples", models: "Models", how: "How it works", pricing: "Pricing", channel: "Channel", cta: "Open bot" },
    hero: {
      badge: "Image, video, and music generation inside Telegram",
      titleStart: "Create images,",
      titleAccent: "video, and music",
      titleEnd: "in one focused workflow",
      description: "APIX brings together text-to-image, image editing, text-to-video, image-to-video, Suno music, feed publishing, and remix workflows inside one Telegram bot.",
      primary: "Open in Telegram",
      secondary: "Launch the bot",
      channelBadge: "Telegram channel",
      channelTitle: "LeluPromt",
      channelText: "Prompt picks, visual references, and fresh generation ideas.",
      linkFeatures: "Features",
      linkExamples: "Examples",
      linkModels: "Models",
      linkHow: "How it works",
      linkPricing: "Pricing",
    },
    panel: {
      eyebrow: "Inside APIX",
      title: "Images, video, music, and remix workflows in one bot",
      imageTitle: "Images",
      image: "text-to-image, editing, references, and multiple creative model styles",
      videoTitle: "Video",
      video: "text-driven clips, image-to-video, and motion-first scenarios",
      musicTitle: "Music",
      music: "tracks from mood, genre, pacing, and scene direction",
      feedTitle: "Feed",
      feed: "public work, result replay, and remix from the feed",
      live: "Clear pricing",
      liveText: "The website shows the same pricing as the bot, so you see the real cost before you launch anything.",
    },
    features: {
      title: "Built for practical creative work",
      subtitle: "From the first prompt to variations, remixing, and publishing without tool switching.",
      items: [
        { title: "Images for real tasks", text: "Build campaign visuals, fashion frames, concept art, product shots, and reference-based edits in one flow." },
        { title: "Video from text and photos", text: "Launch short clips from prompts, animate still images, and test different models by style and budget." },
        { title: "Remix what already works", text: "Take a strong result from the feed or your own history and iterate without starting from zero." },
        { title: "Prompts and ideas", text: "Use the prompt library and photo-to-prompt analysis to reach strong wording faster." },
        { title: "Music inside APIX", text: "Generate tracks by mood, genre, tempo, and scene direction without switching to another music app." },
        { title: "Repeatable sessions", text: "Return to saved settings, continue old generations, and build consistent creative loops." },
      ],
    },
    examples: {
      title: "Examples of what you can actually do",
      subtitle: "Not vague AI claims, but concrete tasks you can launch right away in the bot.",
      items: [
        {
          badge: "Image",
          title: "Build a key visual for a post",
          text: "Example: “cinematic beauty product shot, glass bottle, blue reflections, premium advertising, clean background.”",
        },
        {
          badge: "Video",
          title: "Animate a still image into a short clip",
          text: "Example: upload a portrait and ask for “slow camera push-in, wind in hair, dramatic neon street, cinematic motion.”",
        },
        {
          badge: "Music",
          title: "Generate a track for a moodboard",
          text: "Example: “dark synthwave intro, female vocal, glossy fashion energy, 110 bpm, atmospheric chorus.”",
        },
        {
          badge: "Remix",
          title: "Rework a strong result from the feed",
          text: "Example: take a finished generation and request “more realistic lighting, cleaner skin texture, luxury campaign style.”",
        },
      ],
    },
    how: {
      title: "How it works",
      subtitle: "A fast route from idea to result inside Telegram.",
      items: [
        { title: "Open APIX", text: "Jump into the Telegram bot from this website." },
        { title: "Choose a scenario", text: "Image, video, music, or a remix from an existing work in the feed." },
        { title: "Send a prompt or reference", text: "Describe the task, upload a photo reference, or start from a previous result." },
        { title: "Launch and iterate", text: "Get the result, create variations, remix it, publish to the feed, and keep building the series." },
      ],
    },
    models: {
      title: "Models available in APIX",
      subtitle: "Below is the current set of user-facing models that are wired into the bot and available in product flows.",
      imageBadge: "Images",
      imageTitle: "Image models",
      videoBadge: "Video",
      videoTitle: "Video models",
      musicBadge: "Music",
      musicTitle: "Music model",
      musicNote: "Music runs as a separate mode while staying inside the same product experience.",
    },
    pricing: {
      title: "Transparent pricing",
      subtitle: "Pricing updates automatically, so you always see the current cost before you start.",
      starter: {
        badge: "Starter",
        title: "15 bonus credits",
        text: "Enough to try the product in practice: your first image, video, track, or remix.",
        items: ["Access via Telegram bot", "Images, video, music, and feed", "Prompts, references, and remix flow"],
        cta: "Open bot",
      },
      planCta: "Open bot",
      planMeta: "Current plan",
      planUsage: "Credits work across image, video, music, and remix modes",
    },
    cta: {
      title: "Ready to launch your first APIX workflow?",
      text: "Open the Telegram bot and test image generation, video, music, or remix flows right away.",
      primary: "Open bot",
      secondary: "Go to Telegram",
      channelLead: "Need ideas before you start?",
      channelLink: "Browse the prompt channel",
      supportLead: "Need support or custom development?",
      supportLink: "Message the developer",
    },
    footer: {
      copy: "Images, video, music, references, and remix workflows inside one Telegram bot.",
      features: "Features",
      examples: "Examples",
      models: "Models",
      pricing: "Pricing",
      channel: "Prompt channel",
      supportLead: "Support and development inquiries:",
      supportLink: "@Chillcreative",
    },
  },
}

const languageButtons = Array.from(document.querySelectorAll("[data-lang]"))
const pricingGrid = document.getElementById("pricing-grid")
const modelLists = Array.from(document.querySelectorAll("#models .model-list"))

function get(obj, path) {
  return path.split(".").reduce((acc, key) => (acc == null ? undefined : acc[key]), obj)
}

function detectLanguage() {
  const saved = window.localStorage.getItem("apix-landing-language")
  if (saved === "ru" || saved === "en") return saved
  return String(navigator.language || "ru").toLowerCase().startsWith("ru") ? "ru" : "en"
}

function renderText(language) {
  const copy = translations[language] || translations.ru
  document.documentElement.lang = language
  languageButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.lang === language)
  })
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const value = get(copy, node.dataset.i18n)
    if (typeof value === "string") {
      node.textContent = value
    }
  })
}

function formatRub(language, value) {
  const amount = Number(value || 0)
  if (!Number.isFinite(amount)) return ""
  return new Intl.NumberFormat(language === "ru" ? "ru-RU" : "en-US", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(amount)
}

function renderPlans(language, plans) {
  const copy = translations[language] || translations.ru
  const cards = plans.map((plan, index) => {
    const article = document.createElement("article")
    article.className = `price-card${index === 0 ? " featured" : ""}`
    article.innerHTML = `
      <span class="price-badge">${plan.title || plan.label || "Plan"}</span>
      <h3>${plan.credits} 💋</h3>
      <p>${formatRub(language, plan.price_rub)}</p>
      <ul>
        <li>${copy.pricing.planMeta}</li>
        <li>${plan.title || plan.key}</li>
        <li>${copy.pricing.planUsage}</li>
      </ul>
      <a class="btn btn-primary" href="https://t.me/apix_ai_bot" target="_blank" rel="noopener noreferrer">${copy.pricing.planCta}</a>
    `
    return article
  })

  const starter = pricingGrid.querySelector(".starter-card")
  pricingGrid.innerHTML = ""
  if (starter) pricingGrid.appendChild(starter)
  cards.forEach((card) => pricingGrid.appendChild(card))
}

async function loadPlans(language) {
  try {
    const response = await fetch("/api/v1/plans", { credentials: "same-origin" })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const plans = await response.json()
    if (Array.isArray(plans) && plans.length) {
      renderPlans(language, plans)
    }
  } catch (error) {
    console.warn("Failed to load plans", error)
  }
}

function renderModelSummary(summary) {
  if (!modelLists.length || !summary) return
  const buckets = [summary.image || [], summary.video || [], summary.music || []]
  buckets.forEach((entries, index) => {
    const list = modelLists[index]
    if (!list || !entries.length) return
    list.innerHTML = ""
    entries.forEach((name) => {
      const item = document.createElement("li")
      item.textContent = name
      list.appendChild(item)
    })
  })
}

async function loadModelSummary() {
  try {
    const response = await fetch("/api/v1/public/models", { credentials: "same-origin" })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    renderModelSummary(await response.json())
  } catch (error) {
    console.warn("Failed to load model summary", error)
  }
}

const language = detectLanguage()
renderText(language)
loadPlans(language)
loadModelSummary()

languageButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const nextLanguage = button.dataset.lang === "en" ? "en" : "ru"
    window.localStorage.setItem("apix-landing-language", nextLanguage)
    renderText(nextLanguage)
    loadPlans(nextLanguage)
  })
})
