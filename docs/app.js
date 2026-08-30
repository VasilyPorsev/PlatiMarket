const state = { data: { plus: [], pro: [], updated_at: null }, plan: "plus", query: "" };
const rubles = new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 });
const API = "https://api.digiseller.com";
const plusPattern = /(?:chat\s*gpt|chatgpt)?\s*plus/i;
const proPattern = /(?:^|\s)pro(?:\s*x?\s*(?:5|20)|\s*(?:5|20)\s*x)?(?:\s|$)/i;
const sharedPattern = /(?:общ|совместн|shared|public)/iu;
const sharedDescriptionPattern = /(?:общая|общий|совместн\p{L}*|(?:shared|public)\s+account|account\s+(?:shared|public))/iu;
const nonTariffPattern = /(?:промпт|prompt|лиценз|licen[cs]e|гайд|guide|курс|course|карт\p{L}*\s+(?:для\s+)?chat\s*gpt|card\w*\s+(?:for\s+)?chat\s*gpt)/iu;
const notPlusPattern = /(?:не|без|not|without)\s+(?:chat\s*gpt\s*)?plus/i;
const notProPattern = /(?:не|без|not|without)\s+(?:chat\s*gpt\s*)?pro/i;

function stat(value) {
  return typeof value === "number" ? new Intl.NumberFormat("ru-RU").format(value) : value;
}

function render() {
  const all = state.data[state.plan] || [];
  const needle = state.query.trim().toLocaleLowerCase("ru");
  const rows = needle ? all.filter(item => `${item.seller} ${item.tariff}`.toLocaleLowerCase("ru").includes(needle)) : all;
  const tbody = document.querySelector("#offers");
  tbody.replaceChildren(...rows.map(item => {
    const row = document.createElement("tr");
    [item.seller, item.tariff, stat(item.sold), stat(item.returns)].forEach(value => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    });
    const price = document.createElement("td");
    price.className = "price";
    price.textContent = rubles.format(item.price);
    row.append(price);
    const action = document.createElement("td");
    const link = document.createElement("a");
    link.className = "open-link";
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.title = "Открыть предложение";
    link.textContent = "↗";
    action.append(link);
    row.append(action);
    return row;
  }));
  document.querySelector("#empty").hidden = rows.length !== 0;
  document.querySelector("#offers-count").textContent = stat(all.length);
  document.querySelector("#sellers-count").textContent = stat(new Set(all.map(item => item.seller)).size);
  document.querySelector("#min-price").textContent = all.length ? rubles.format(Math.min(...all.map(item => item.price))) : "—";
  document.querySelector("#plus-count").textContent = state.data.plus.length;
  document.querySelector("#pro-count").textContent = state.data.pro.length;
}

function visibleStat(stats, key) {
  const value = Number(stats?.[key] ?? -1);
  if (value < 0) return "скрыто";
  return stats?.[`${key}_hidden`] ? `>${value}` : value;
}

function matchesTariff(text, kind) {
  if (sharedPattern.test(text) || nonTariffPattern.test(text)) return false;
  if (kind === "plus") return plusPattern.test(text) && !proPattern.test(text) && !notPlusPattern.test(text);
  return proPattern.test(text) && !plusPattern.test(text) && !notProPattern.test(text);
}

function choicesFor(options, kind) {
  const choices = [];
  for (const option of options) {
    if (!["radio", "select"].includes(option.type)) continue;
    for (const variant of option.variants || []) {
      const text = String(variant.text || "");
      if (variant.visible !== 0 && variant.value != null && matchesTariff(text, kind)) {
        choices.push({ name: text, group: option.id, value: variant.value });
      }
    }
  }
  return choices;
}

function selectedOptions(options, choice) {
  const selected = new Map();
  for (const option of options) {
    const variant = (option.variants || []).find(item => item.default && item.value != null);
    if (variant) selected.set(option.id, variant.value);
  }
  selected.set(choice.group, choice.value);
  return selected;
}

async function priceFor(productId, options, choice) {
  const params = new URLSearchParams({ product_id: productId, currency: "RUB", count: "1" });
  for (const [group, value] of selectedOptions(options, choice)) params.append("options[]", `${group}:${value}`);
  const response = await fetch(`${API}/api/products/price/calc?${params}`);
  if (!response.ok) throw new Error(`Цена: HTTP ${response.status}`);
  const payload = await response.json();
  const amount = Number(payload.data?.amount || 0);
  return payload.retval === 0 && amount > 0 ? Math.ceil(amount) : null;
}

async function cheapestTariff(productId, options, kind) {
  const priced = await Promise.all(choicesFor(options, kind).map(async choice => ({
    choice,
    price: await priceFor(productId, options, choice),
  })));
  return priced.filter(item => item.price != null).sort((a, b) => a.price - b.price)[0] || null;
}

async function fetchProduct(product) {
  const response = await fetch(`${API}/api/products/${product.product_id}/data?lang=ru-RU`, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`Товар ${product.product_id}: HTTP ${response.status}`);
  const data = (await response.json()).product || {};
  const description = new DOMParser().parseFromString(String(data.info || ""), "text/html").body.textContent || "";
  if (sharedDescriptionPattern.test(description)) return { plus: null, pro: null };
  const options = data.options || [];
  const [plus, pro] = await Promise.all([
    cheapestTariff(product.product_id, options, "plus"),
    cheapestTariff(product.product_id, options, "pro"),
  ]);
  const base = {
    url: data.card_url || `https://plati.market/itm/${product.product_id}`,
    seller: data.seller?.name || product.seller_name || "",
    sold: visibleStat(data.statistics, "sales"),
    returns: visibleStat(data.statistics, "refunds"),
  };
  return {
    plus: plus ? { ...base, tariff: plus.choice.name, price: plus.price } : null,
    pro: pro ? { ...base, tariff: pro.choice.name, price: pro.price } : null,
  };
}

async function searchProducts() {
  const products = [];
  let page = 1;
  while (true) {
    const params = new URLSearchParams({
      productName: "ChatGPT", ownerId: "plati", currency: "RUB", page: String(page), count: "100",
      sortBy: "price-asc", getProductsRecursive: "true", individual: "false", video: "false",
      image: "false", includeAggregations: "false", fuzzy: "false", lang: "ru-RU",
    });
    const response = await fetch(`${API}/api/cataloguer/front/products?${params}`);
    if (!response.ok) throw new Error(`Поиск: HTTP ${response.status}`);
    const content = (await response.json()).content || {};
    products.push(...(content.items || []));
    if (!content.has_next_page) break;
    page += 1;
  }
  return products;
}

async function mapConcurrent(items, concurrency, mapper, onProgress) {
  const results = new Array(items.length);
  let next = 0;
  let done = 0;
  async function worker() {
    while (next < items.length) {
      const index = next++;
      try { results[index] = await mapper(items[index]); } catch (error) { console.warn(error); }
      onProgress(++done, items.length);
    }
  }
  await Promise.all(Array.from({ length: concurrency }, worker));
  return results.filter(Boolean);
}

async function refreshFromPlati() {
  const button = document.querySelector("#refresh");
  const updated = document.querySelector("#updated");
  button.disabled = true;
  button.querySelector("svg").style.animation = "spin 1s linear infinite";
  try {
    updated.textContent = "Получаем список товаров…";
    const products = await searchProducts();
    const results = await mapConcurrent(products, 10, fetchProduct, (done, total) => {
      updated.textContent = `Обновляем тарифы: ${done} из ${total}`;
    });
    const plus = results.flatMap(item => item.plus ? [item.plus] : []).sort((a, b) => a.price - b.price);
    const pro = results.flatMap(item => item.pro ? [item.pro] : []).sort((a, b) => a.price - b.price);
    state.data = { plus, pro, updated_at: new Date().toISOString() };
    updated.textContent = `Обновлено ${new Date().toLocaleString("ru-RU")}`;
    render();
  } catch (error) {
    updated.textContent = `Ошибка обновления: ${error.message}`;
  } finally {
    button.disabled = false;
    button.querySelector("svg").style.animation = "";
  }
}

function xmlEscape(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

function exportExcel() {
  const headers = ["Ссылка", "Продавец", "Название тарифа", "Продано", "Возвратов", "Цена"];
  const worksheet = (name, rows) => `<Worksheet ss:Name="${name}"><Table>${[headers, ...rows.map(item => [item.url, item.seller, item.tariff, item.sold, item.returns, item.price])].map(row => `<Row>${row.map((value, index) => `<Cell><Data ss:Type="${index === 5 && typeof value === "number" ? "Number" : "String"}">${xmlEscape(value)}</Data></Cell>`).join("")}</Row>`).join("")}</Table></Worksheet>`;
  const xml = `<?xml version="1.0"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">${worksheet("ChatGPT Plus", state.data.plus)}${worksheet("ChatGPT Pro", state.data.pro)}</Workbook>`;
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([xml], { type: "application/vnd.ms-excel;charset=utf-8" }));
  link.download = "chatgpt_tariffs.xls";
  link.click();
  URL.revokeObjectURL(link.href);
}

document.querySelectorAll(".tab").forEach(tab => tab.addEventListener("click", () => {
  state.plan = tab.dataset.plan;
  document.querySelectorAll(".tab").forEach(item => {
    const active = item === tab;
    item.classList.toggle("active", active);
    item.setAttribute("aria-selected", active);
  });
  render();
}));
document.querySelector("#search").addEventListener("input", event => { state.query = event.target.value; render(); });
document.querySelector("#refresh").addEventListener("click", refreshFromPlati);
document.querySelector("#export").addEventListener("click", exportExcel);

fetch("data.json", { cache: "no-store" })
  .then(response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
  .then(data => {
    state.data = data;
    document.querySelector("#updated").textContent = `Обновлено ${new Date(data.updated_at).toLocaleString("ru-RU")}`;
    document.querySelector("#loading").remove();
    render();
  })
  .catch(error => { document.querySelector("#loading").textContent = `Не удалось загрузить данные: ${error.message}`; });
