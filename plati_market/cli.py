from __future__ import annotations

import argparse
import logging

import requests

from .scraper import fetch_products, scrape_tariffs
from .site import save_site


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Обновление сайта с тарифами ChatGPT на Plati.Market")
    parser.add_argument("--site-dir", default="docs", help="каталог статического сайта")
    parser.add_argument("--query", default="ChatGPT", help="поисковый запрос")
    parser.add_argument("--workers", type=int, default=8, help="число одновременных запросов")
    parser.add_argument("--timeout", type=float, default=30, help="тайм-аут запроса, секунд")
    parser.add_argument("--max-products", type=int, help="обработать не более N карточек")
    parser.add_argument("--verbose", action="store_true", help="подробный журнал")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.workers < 1 or args.timeout <= 0 or (args.max_products is not None and args.max_products < 1):
        raise SystemExit("workers, timeout и max-products должны быть положительными")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s")
    log = logging.getLogger("plati_market")
    with requests.Session() as session:
        session.headers["User-Agent"] = "Mozilla/5.0 (compatible; PlatiPlusPriceResearch/1.0)"
        products = fetch_products(session, args.query, args.timeout, args.max_products)
    log.info("Найдено карточек: %d. Открываю страницы товаров...", len(products))
    plus_offers, pro_offers = scrape_tariffs(products, args.workers, args.timeout, log)
    data_path, excel_path = save_site(plus_offers, pro_offers, args.site_dir)
    log.info(
        "Предложений Plus: %d, Pro: %d. Сайт: %s. Excel: %s",
        len(plus_offers), len(pro_offers), data_path.parent, excel_path,
    )
    return 0
