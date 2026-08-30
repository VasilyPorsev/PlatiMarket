from __future__ import annotations

import argparse
import logging

import requests

from .excel import save_excel
from .scraper import fetch_products, scrape_tariffs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Сбор цен ChatGPT Plus с Plati.Market в Excel")
    parser.add_argument("-o", "--output", default="chatgpt_plus.xlsx", help="путь к файлу Excel")
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
    path = save_excel(plus_offers, args.output, pro_offers)
    log.info(
        "Предложений Plus: %d, Pro: %d. Файл: %s",
        len(plus_offers), len(pro_offers), path,
    )
    return 0
