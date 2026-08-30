from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Iterable
from urllib.parse import urljoin
from xml.sax.saxutils import quoteattr

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://plati.market"
API_URL = "https://api.digiseller.com/api/cataloguer/front/products"
PRICE_OPTIONS_URL = f"{BASE_URL}/asp/price_options.asp"
PRODUCT_DATA_URL = "https://api.digiseller.com/api/products/{product_id}/data"
PRICE_RE = re.compile(r"([+-]?)\s*([\d\s\u00a0.,]+)\s*(?:₽|руб)", re.IGNORECASE)
PLUS_RE = re.compile(r"(?<![\w])(?:chat\s*gpt|chatgpt)?\s*plus(?![\w])", re.IGNORECASE)
PRO_RE = re.compile(r"(?<![\w])pro(?:\s*\d+x)?(?![\w])", re.IGNORECASE)
SHARED_RE = re.compile(r"(?<![\w])(?:общ\w*|shared|public)(?![\w])", re.IGNORECASE)
SHARED_DESCRIPTION_RE = re.compile(
    r"(?:"
    r"(?<![\w])общ(?:ая|ий)(?![\w])"
    r"|"
    r"(?:общ\w*|публичн\w*)\s+(?:\([^)]*\)\s*)?(?:аккаунт\w*|уч[её]тн\w*\s+запис\w*)"
    r"|(?:аккаунт\w*|уч[её]тн\w*\s+запис\w*)\s+(?:общ\w*|публичн\w*)"
    r"|(?:shared|public)\s+account\w*"
    r"|account\w*\s+(?:shared|public)"
    r")",
    re.IGNORECASE,
)
NOT_PLUS_RE = re.compile(
    r"(?<![\w])(?:не|без|not|without)\s+(?:chat\s*gpt\s*)?plus(?![\w])",
    re.IGNORECASE,
)
NOT_PRO_RE = re.compile(
    r"(?<![\w])(?:не|без|not|without)\s+(?:chat\s*gpt\s*)?pro(?![\w])",
    re.IGNORECASE,
)
NON_TARIFF_RE = re.compile(
    r"(?:промпт|prompt|лиценз|licen[cs]e|гайд|guide|курс|course|"
    r"(?:карт\w*\s+(?:для\s+)?chat\s*gpt)|(?:card\w*\s+(?:for\s+)?chat\s*gpt))",
    re.IGNORECASE,
)
PLAN_RE = re.compile(
    r"(?:месяц|дн(?:ей|я)|month|days?|подпис\w*|subscription|активац\w*|activation|"
    r"продлен\w*|renew\w*|аккаунт\w*|account|доступ|access)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Product:
    product_id: int
    url: str
    seller: str
    base_price: Decimal
    title: str
    sold: int | str = 0
    returns: int | str = 0


@dataclass(frozen=True)
class Offer:
    url: str
    seller: str
    tariff: str
    sold: int | str
    returns: int | str
    price: Decimal


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Некорректная цена: {value!r}") from exc


def _localized_name(item: dict) -> str:
    names = item.get("name") or []
    for locale in ("ru-RU", "en-US"):
        for name in names:
            if name.get("locale") == locale:
                return str(name.get("value") or "")
    return str(names[0].get("value") or "") if names else ""


def fetch_products(
    session: requests.Session,
    query: str = "ChatGPT",
    timeout: float = 30,
    max_products: int | None = None,
    page_size: int = 100,
) -> list[Product]:
    products: list[Product] = []
    page = 1
    while True:
        params = {
            "productName": query,
            "ownerId": "plati",
            "currency": "RUB",
            "page": page,
            "count": page_size,
            "sortBy": "price-asc",
            "getProductsRecursive": "true",
            "individual": "false",
            "video": "false",
            "image": "false",
            "includeAggregations": "false",
            "fuzzy": "false",
            "lang": "ru-RU",
        }
        response = session.get(API_URL, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        content = payload.get("content") or {}
        for item in content.get("items") or []:
            product_id = item.get("product_id")
            alias = item.get("name_url") or "product"
            products.append(
                Product(
                    product_id=int(product_id),
                    url=f"{BASE_URL}/itm/{alias}/{product_id}",
                    seller=str(item.get("seller_name") or ""),
                    base_price=_decimal(item.get("price")),
                    title=_localized_name(item),
                )
            )
            if max_products is not None and len(products) >= max_products:
                return _add_statistics(session, products, timeout)
        if not content.get("has_next_page") or not content.get("items"):
            return _add_statistics(session, products, timeout)
        page += 1


def _visible_stat(item: dict, name: str) -> int | str:
    value = int(item.get(name, -1))
    hidden = bool(item.get(f"{name}_hidden", 0))
    if value < 0:
        return "скрыто"
    return f">{value}" if hidden else value


def _add_statistics(session: requests.Session, products: list[Product], timeout: float) -> list[Product]:
    """Public API exposes sales/refunds in one batch (sometimes sellers hide them)."""
    if not products:
        return products
    response = session.post(
        "https://api.digiseller.com/api/products/list",
        json={"ids": [p.product_id for p in products], "lang": "ru-RU"},
        timeout=timeout,
    )
    response.raise_for_status()
    stats = {int(item["id"]): item for item in response.json()}
    return [
        replace(
            product,
            sold=_visible_stat(stats[product.product_id], "cnt_sell"),
            returns=_visible_stat(stats[product.product_id], "cnt_return"),
        )
        if product.product_id in stats
        else replace(product, sold="скрыто", returns="скрыто")
        for product in products
    ]


def _delta_from_label(label) -> Decimal:
    delta_node = label.select_one(".chips__delta")
    text = delta_node.get_text(" ", strip=True) if delta_node else ""
    if not text or "выбран" in text.casefold():
        return Decimal("0")
    match = PRICE_RE.search(text)
    if not match:
        return Decimal("0")
    number = match.group(2).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    value = _decimal(number)
    return -value if match.group(1) == "-" else value


def _parse_tariff(
    html: str,
    product: Product,
    tariff_re: re.Pattern[str],
    forbidden_re: re.Pattern[str],
    negated_re: re.Pattern[str],
    require_plan_for_title: bool = False,
    allow_title_fallback: bool = True,
) -> tuple[str, Decimal] | None:
    soup = BeautifulSoup(html, "html.parser")
    description = soup.select_one("#description-tab-content")
    if description and SHARED_DESCRIPTION_RE.search(description.get_text(" ", strip=True)):
        return None
    candidates: list[tuple[str, Decimal]] = []
    for label in soup.select("label.chips__label"):
        text_node = label.select_one(".body-regular")
        text = (text_node or label).get_text(" ", strip=True)
        if (
            tariff_re.search(text)
            and not forbidden_re.search(text)
            and not SHARED_RE.search(text)
            and not negated_re.search(text)
            and not NON_TARIFF_RE.search(text)
        ):
            candidates.append((text, product.base_price + _delta_from_label(label)))

    # Некоторые карточки целиком посвящены Plus и не имеют вариантов тарифа.
    if not candidates and allow_title_fallback:
        page_title = soup.title.get_text(" ", strip=True) if soup.title else product.title
        if (
            tariff_re.search(page_title)
            and not forbidden_re.search(page_title)
            and not SHARED_RE.search(page_title)
            and not negated_re.search(page_title)
            and not NON_TARIFF_RE.search(page_title)
            and (not require_plan_for_title or PLAN_RE.search(page_title))
        ):
            candidates.append((product.title, product.base_price))
    valid = [(name, price) for name, price in candidates if price >= 0]
    # В интерфейсе Plati рублёвая цена округляется вверх до целого рубля.
    if not valid:
        return None
    name, price = min(valid, key=lambda candidate: candidate[1])
    return name, price.quantize(Decimal("1"), rounding=ROUND_CEILING)


def parse_plus_tariff(html: str, product: Product) -> tuple[str, Decimal] | None:
    return _parse_tariff(
        html, product, PLUS_RE, PRO_RE, NOT_PLUS_RE,
        allow_title_fallback=False,
    )


def parse_pro_tariff(html: str, product: Product) -> tuple[str, Decimal] | None:
    return _parse_tariff(
        html, product, PRO_RE, PLUS_RE, NOT_PRO_RE,
        require_plan_for_title=True, allow_title_fallback=False,
    )


def parse_plus_price(html: str, product: Product) -> Decimal | None:
    """Backward-compatible price-only helper."""
    result = parse_plus_tariff(html, product)
    return result[1] if result else None


def _description_is_shared(soup: BeautifulSoup) -> bool:
    description = soup.select_one("#description-tab-content")
    return bool(description and SHARED_DESCRIPTION_RE.search(description.get_text(" ", strip=True)))


def _matching_choices(
    soup: BeautifulSoup,
    tariff_re: re.Pattern[str],
    forbidden_re: re.Pattern[str],
    negated_re: re.Pattern[str],
) -> list[tuple[str, object]]:
    choices: list[tuple[str, object]] = []
    for label in soup.select("label.chips__label[for]"):
        text_node = label.select_one(".body-regular")
        text = (text_node or label).get_text(" ", strip=True)
        if not (
            tariff_re.search(text)
            and not forbidden_re.search(text)
            and not SHARED_RE.search(text)
            and not negated_re.search(text)
            and not NON_TARIFF_RE.search(text)
        ):
            continue
        option = soup.find(id=label.get("for"))
        if option and option.get("data-id") and option.get("value"):
            choices.append((text, option))
    return choices


def _options_xml(soup: BeautifulSoup, chosen) -> str:
    chosen_group = str(chosen.get("data-id"))
    selected: dict[str, str] = {}
    for option in soup.select("input.cl_checked_option[checked], input.cl_selected2_option[checked]"):
        group = option.get("data-id")
        value = option.get("value")
        if group and value is not None:
            selected[str(group)] = str(value)
    for select in soup.select("select.cl_selected_option[data-id]"):
        option = select.select_one("option[selected]") or select.select_one("option")
        if option and option.get("value") is not None:
            selected[str(select["data-id"])] = str(option["value"])
    selected[chosen_group] = str(chosen["value"])
    body = "".join(
        f"<option O={quoteattr(group)} V={quoteattr(value)}/>"
        for group, value in selected.items()
    )
    return f"<response>{body}</response>"


def _api_matching_choices(
    options: list[dict],
    tariff_re: re.Pattern[str],
    forbidden_re: re.Pattern[str],
    negated_re: re.Pattern[str],
) -> list[tuple[str, int, int]]:
    choices: list[tuple[str, int, int]] = []
    for option in options:
        group_id = option.get("id")
        if not group_id or option.get("type") not in {"radio", "select"}:
            continue
        for variant in option.get("variants") or []:
            text = str(variant.get("text") or "")
            if (
                variant.get("visible", 1)
                and tariff_re.search(text)
                and not forbidden_re.search(text)
                and not SHARED_RE.search(text)
                and not negated_re.search(text)
                and not NON_TARIFF_RE.search(text)
                and variant.get("value") is not None
            ):
                choices.append((text, int(group_id), int(variant["value"])))
    return choices


def _api_options_xml(options: list[dict], chosen: tuple[str, int, int]) -> str:
    _, chosen_group, chosen_value = chosen
    selected: dict[int, int] = {}
    for option in options:
        for variant in option.get("variants") or []:
            if variant.get("default") and variant.get("value") is not None:
                selected[int(option["id"])] = int(variant["value"])
                break
    selected[chosen_group] = chosen_value
    body = "".join(
        f"<option O={quoteattr(str(group))} V={quoteattr(str(value))}/>"
        for group, value in selected.items()
    )
    return f"<response>{body}</response>"


def _recalculated_tariff(
    session: requests.Session,
    product: Product,
    choices: list[tuple[str, int, int]],
    options: list[dict],
    timeout: float,
) -> tuple[str, Decimal] | None:
    prices: list[tuple[str, Decimal]] = []
    for choice in choices:
        name = choice[0]
        response = session.get(
            PRICE_OPTIONS_URL,
            params={
                "p": product.product_id,
                "n": "0",
                "c": "RUB",
                "e": "",
                "d": "false",
                "x": _api_options_xml(options, choice),
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if str(payload.get("err") or "0") != "0":
            continue
        amount = str(payload.get("amount") or "").replace(" ", "").replace("\u00a0", "").replace(",", ".")
        if amount:
            price = _decimal(amount).quantize(Decimal("1"), rounding=ROUND_CEILING)
            if price > 0:
                prices.append((name, price))
    return min(prices, key=lambda candidate: candidate[1]) if prices else None


def _to_offer(product: Product, canonical: str, tariff: tuple[str, Decimal] | None) -> Offer | None:
    if tariff is None:
        return None
    tariff_name, price = tariff
    return Offer(
        url=urljoin(BASE_URL, canonical), seller=product.seller, tariff=tariff_name,
        sold=product.sold, returns=product.returns, price=price,
    )


def _fetch_offers(product: Product, timeout: float, user_agent: str) -> tuple[Offer | None, Offer | None]:
    with requests.Session() as session:
        session.headers["User-Agent"] = user_agent
        response = session.get(
            PRODUCT_DATA_URL.format(product_id=product.product_id),
            params={"lang": "ru-RU"},
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("product") or {}
        description = BeautifulSoup(str(data.get("info") or ""), "html.parser").get_text(" ", strip=True)
        if SHARED_DESCRIPTION_RE.search(description):
            return None, None
        options = data.get("options") or []
        plus_choices = _api_matching_choices(options, PLUS_RE, PRO_RE, NOT_PLUS_RE)
        pro_choices = _api_matching_choices(options, PRO_RE, PLUS_RE, NOT_PRO_RE)
        plus = _recalculated_tariff(session, product, plus_choices, options, timeout)
        pro = _recalculated_tariff(session, product, pro_choices, options, timeout)
        canonical = str(data.get("card_url") or product.url)
        return _to_offer(product, canonical, plus), _to_offer(product, canonical, pro)


def scrape_tariffs(
    products: Iterable[Product],
    workers: int = 8,
    timeout: float = 30,
    logger: logging.Logger | None = None,
) -> tuple[list[Offer], list[Offer]]:
    log = logger or logging.getLogger(__name__)
    user_agent = "Mozilla/5.0 (compatible; PlatiPlusPriceResearch/1.0)"
    plus_offers: list[Offer] = []
    pro_offers: list[Offer] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_offers, p, timeout, user_agent): p for p in products}
        for future in as_completed(futures):
            product = futures[future]
            try:
                plus, pro = future.result()
                if plus is not None:
                    plus_offers.append(plus)
                if pro is not None:
                    pro_offers.append(pro)
            except (requests.RequestException, ValueError) as exc:
                log.warning("Не удалось обработать %s: %s", product.url, exc)
    key = lambda offer: (offer.price, offer.seller.casefold())
    return sorted(plus_offers, key=key), sorted(pro_offers, key=key)


def scrape_offers(
    products: Iterable[Product], workers: int = 8, timeout: float = 30,
    logger: logging.Logger | None = None,
) -> list[Offer]:
    """Backward-compatible helper returning only Plus offers."""
    return scrape_tariffs(products, workers, timeout, logger)[0]
