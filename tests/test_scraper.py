from decimal import Decimal

from plati_market.scraper import Product, parse_plus_price, parse_plus_tariff, parse_pro_tariff


def test_selects_cheapest_plus_variant_and_applies_delta():
    product = Product(1, "https://example.test/item", "seller", Decimal("1000"), "ChatGPT")
    html = """
    <title>ChatGPT Plus / Pro</title>
    <label class="chips__label"><span class="body-regular">ChatGPT Pro 20x</span><span class="chips__delta">+5 000 ₽</span></label>
    <label class="chips__label"><span class="body-regular">ChatGPT Plus 1 месяц</span><span class="chips__delta">+200 ₽</span></label>
    <label class="chips__label"><span class="body-regular">ChatGPT Plus общий аккаунт</span><span class="chips__delta">-100 ₽</span></label>
    """
    assert parse_plus_tariff(html, product) == ("ChatGPT Plus 1 месяц", Decimal("1200"))


def test_plus_requires_explicit_tariff_option():
    product = Product(1, "https://example.test/item", "seller", Decimal("1499.01"), "ChatGPT Plus")
    assert parse_plus_price("<title>Купить ChatGPT Plus на месяц</title>", product) is None


def test_rejects_pro_only_product():
    product = Product(1, "https://example.test/item", "seller", Decimal("1499"), "ChatGPT Pro")
    assert parse_plus_price("<title>Купить ChatGPT Pro 20x</title>", product) is None


def test_rejects_explicitly_non_plus_tariff():
    product = Product(1, "https://example.test/item", "seller", Decimal("100"), "ChatGPT")
    html = '<label class="chips__label"><span class="body-regular">Бесплатный тариф (не Plus)</span></label>'
    assert parse_plus_tariff(html, product) is None


def test_selects_pro_and_rejects_shared_pro():
    product = Product(1, "https://example.test/item", "seller", Decimal("1000"), "ChatGPT")
    html = """
    <label class="chips__label"><span class="body-regular">ChatGPT Pro 20x public</span><span class="chips__delta">+10 ₽</span></label>
    <label class="chips__label"><span class="body-regular">ChatGPT Pro 5x личный</span><span class="chips__delta">+5000 ₽</span></label>
    """
    assert parse_pro_tariff(html, product) == ("ChatGPT Pro 5x личный", Decimal("6000"))


def test_rejects_product_when_description_mentions_shared_account():
    product = Product(1, "https://example.test/item", "seller", Decimal("1000"), "ChatGPT")
    html = """
    <label class="chips__label"><span class="body-regular">ChatGPT Plus личный</span></label>
    <div id="description-tab-content">Также доступен общий (Public) аккаунт.</div>
    """
    assert parse_plus_tariff(html, product) is None


def test_rejects_prompt_pack_from_pro_sheet():
    product = Product(
        1, "https://example.test/item", "seller", Decimal("299"),
        "100 промптов ChatGPT для студентов — AI Student Pro 2026",
    )
    assert parse_pro_tariff("<title>100 промптов ChatGPT — AI Student Pro 2026</title>", product) is None


def test_rejects_any_common_word_in_description():
    product = Product(1, "https://example.test/item", "seller", Decimal("1000"), "ChatGPT")
    html = """
    <label class="chips__label"><span class="body-regular">ChatGPT Plus личный</span></label>
    <div id="description-tab-content">Общая подписка с гарантией.</div>
    """
    assert parse_plus_tariff(html, product) is None


def test_pro_requires_explicit_tariff_option():
    product = Product(1, "https://example.test/item", "seller", Decimal("1000"), "ChatGPT Pro 5x")
    assert parse_pro_tariff("<title>ChatGPT Pro 5x на 1 месяц</title>", product) is None


def test_rejects_joint_tariff_and_description():
    product = Product(1, "https://example.test/item", "seller", Decimal("1000"), "ChatGPT")
    tariff_html = '<label class="chips__label"><span class="body-regular">ChatGPT Plus — совместный</span></label>'
    description_html = """
    <label class="chips__label"><span class="body-regular">ChatGPT Plus личный</span></label>
    <div id="description-tab-content">Совместный доступ также доступен.</div>
    """
    assert parse_plus_tariff(tariff_html, product) is None
    assert parse_plus_tariff(description_html, product) is None
