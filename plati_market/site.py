from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .excel import save_excel
from .scraper import Offer


def _offer_dict(offer: Offer) -> dict[str, object]:
    return {
        "url": offer.url,
        "seller": offer.seller,
        "tariff": offer.tariff,
        "sold": offer.sold,
        "returns": offer.returns,
        "price": float(offer.price),
    }


def save_site(plus_offers: list[Offer], pro_offers: list[Offer], output_dir: str | Path) -> tuple[Path, Path]:
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    data_path = directory / "data.json"
    excel_path = directory / "chatgpt_tariffs.xlsx"
    payload = {
        "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "plus": [_offer_dict(offer) for offer in plus_offers],
        "pro": [_offer_dict(offer) for offer in pro_offers],
    }
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save_excel(plus_offers, excel_path, pro_offers)
    return data_path, excel_path
