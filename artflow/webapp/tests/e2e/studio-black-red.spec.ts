import { expect, test } from "@playwright/test";

test("Studio black red navigation, balance cancel and profile work across the device matrix", async ({page}) => {
  const mutations: string[] = [];
  await page.addInitScript(() => {
    window.Telegram = { WebApp: { initData:"studio-device-fixture", version:"8.0", colorScheme:"dark", ready(){}, expand(){}, requestFullscreen(){}, HapticFeedback:{impactOccurred(){},notificationOccurred(){}} } };
  });
  await page.route("**/telegram-web-app.js", route => route.fulfill({body:""}));
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== "GET") mutations.push(path);
    const json = (data:unknown) => route.fulfill({json:data});
    if (path.endsWith("/auth/config")) return json({bot_username:"fixture_bot"});
    if (path.endsWith("/studio/preview")) return json({allowed:true,ui_version:3});
    if (path.endsWith("/me")) return json({id:7,tg_id:123,full_name:"Студия",credits:120,language:"ru",miniapp_ux2_available:true});
    if (path.endsWith("/models/image")) return json([{key:"fixture-photo",display_name:"Фото",modes:["text","image"],credits:5,max_refs:2,aspect_ratios:["1:1"],counts:[1]}]);
    if (path.endsWith("/history")) return json([{id:77,model:"fixture-photo",gen_type:"image",prompt:"Моя работа",status:"done"}]);
    if (path.endsWith("/referrals")) return json({counts:{},balance:{},children:{},withdrawals:[]});
    if (path.endsWith("/plans")) return json([{key:"server-plan",title:"Пакет с сервера",credits:50,price_rub:99}]);
    if (path.endsWith("/payment-methods")) return json(["tbank"]);
    return json([]);
  });
  await page.goto("/?ux=3");
  await expect(page.locator("body")).toHaveCSS("background-color","rgb(0, 0, 0)");
  const nav = page.getByRole("navigation");
  await expect(nav.locator("button")).toHaveCount(5);
  const create = await nav.locator('[data-destination="create"]').boundingBox();
  expect(create!.height).toBeGreaterThanOrEqual(44); expect(create!.width).toBeGreaterThanOrEqual(44);
  await page.getByRole("button",{name:"Создать фото",exact:true}).click();
  const prompt = page.getByRole("textbox",{name:/^Промпт/}); await prompt.fill("Сохранённый красный портрет");
  await nav.getByRole("button",{name:"Пополнить",exact:true}).click();
  await expect(page.getByRole("dialog")).toContainText("Пакет с сервера");
  await page.getByRole("dialog").getByRole("button",{name:"Закрыть",exact:true}).click();
  await expect(prompt).toHaveValue("Сохранённый красный портрет");
  await nav.getByRole("tab",{name:"Профиль",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Мои работы",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Моя работа — Готово",exact:true}).click();
  const task = page.getByRole("dialog",{name:"Задача #77"});
  await task.getByRole("button",{name:"Пополнить",exact:true}).click();
  await expect(task).not.toBeVisible();
  await page.getByRole("dialog").getByRole("button",{name:"Закрыть",exact:true}).click();
  await expect(task).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(mutations.filter(path => /\/topup\/|\/generate\//.test(path))).toHaveLength(0);
});
