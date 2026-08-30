const state = { data: { plus: [], pro: [] }, plan: "plus", query: "" };
const rubles = new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 });

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
document.querySelector("#search").addEventListener("input", event => {
  state.query = event.target.value;
  render();
});

fetch("data.json", { cache: "no-store" })
  .then(response => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then(data => {
    state.data = data;
    document.querySelector("#plus-count").textContent = data.plus.length;
    document.querySelector("#pro-count").textContent = data.pro.length;
    document.querySelector("#updated").textContent = `Обновлено ${new Date(data.updated_at).toLocaleString("ru-RU")}`;
    document.querySelector("#loading").remove();
    render();
  })
  .catch(error => {
    document.querySelector("#loading").textContent = `Не удалось загрузить данные: ${error.message}`;
  });
