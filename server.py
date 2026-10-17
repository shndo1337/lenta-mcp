"""MCP-сервер для «Ленты» на основе открытого Integration API.

Спецификация API: https://lenta.com/llms.txt (авторизация не нужна).
Только чтение: магазины, категории, поиск и карточки товаров.

По умолчанию используется Томск: гипермаркет на Пушкина, 59 (id 99) и канал доставки.
Переопределяется переменными окружения LENTA_STORE_ID, LENTA_CHANNEL,
LENTA_LAT и LENTA_LON (точка, от которой считается расстояние).
"""
import asyncio
import math
import os

import httpx
from fastmcp import FastMCP

API = "https://integration.api.lenta.com"
SITE = "https://lenta.com"
RETAIL_BRAND = "lo"
HOME = (
    float(os.environ.get("LENTA_LAT", "56.4887")),
    float(os.environ.get("LENTA_LON", "84.9523")),
)

DEFAULT_STORE = int(os.environ.get("LENTA_STORE_ID", "99"))
DEFAULT_CHANNEL = os.environ.get("LENTA_CHANNEL", "lo")

mcp = FastMCP("lenta")

_client = httpx.AsyncClient(
    base_url=API,
    headers={"User-Agent": "lenta-mcp (+https://github.com/shndo1337/lenta-mcp)"},
    timeout=25,
)


async def _get(path: str, params: dict) -> dict:
    r = await _client.get(path, params={"retailBrand": RETAIL_BRAND, **params})
    if r.status_code >= 400:
        raise RuntimeError(f"Lenta API {r.status_code}: {r.text[:200]}")
    return r.json()


def _rub(kopecks: int | None) -> float | None:
    return None if kopecks is None else round(kopecks / 100, 2)


def _product(p: dict, store_id: int) -> dict:
    prices = p.get("prices") or {}
    price, regular = prices.get("price"), prices.get("priceRegular")
    weight = p.get("weight") or {}
    return {
        "id": p["id"],
        "name": p["name"],
        "price": _rub(price),
        "regular_price": _rub(regular) if regular != price else None,
        "discount_percent": prices.get("discountPercentage")
        or (round((1 - price / regular) * 100) if price and regular and regular > price else None),
        "loyalty_card_price": prices.get("isLoyaltyCardPrice"),
        "promo": prices.get("isPromoactionPrice"),
        "weight": weight.get("package") or None,
        "in_stock_count": p.get("count"),
        "category_id": p.get("categoryId"),
        "store_id": store_id,
        "url": f"{SITE}/product/{p['slug']}-{p['id']}/" if p.get("slug") else None,
    }


def _category(c: dict) -> dict:
    return {
        "id": c["id"],
        "name": c["name"],
        "level": c.get("level"),
        "parent_id": c.get("parentId") or None,
        "has_children": c.get("hasChildren"),
    }


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * 6371000 * math.asin(math.sqrt(h)))


async def _nearest(lat: float, lon: float, count: int) -> list[dict]:
    stores = (await _get("/v1/stores", {}))["stores"]
    for s in stores:
        s["distance_m"] = _distance_m(lat, lon, s["lat"], s["long"])
    # «zoo» — зоомагазины без продуктового каталога
    stores = [s for s in stores if s.get("type") != "zoo"]
    stores.sort(key=lambda s: s["distance_m"])
    return stores[:count]


def _store(s: dict) -> dict:
    return {
        "id": int(s["id"]),
        "address": s["address"],
        "city": s["cityName"],
        "type": s.get("type"),
        "distance_m": s["distance_m"],
        "hours": "24 часа" if s.get("is24hStore") else f"{s['opensAt']}–{s['closesAt']}",
        "pickup": s.get("isPickupAvailable"),
    }


@mcp.tool()
async def nearest_stores(
    latitude: float = HOME[0], longitude: float = HOME[1], count: int = 5
) -> list[dict]:
    """Ближайшие магазины «Ленты» к точке (по умолчанию центр Томска).

    Поле `id` используется как store_id в остальных инструментах.

    Args:
        latitude: Широта.
        longitude: Долгота.
        count: Сколько магазинов вернуть.
    """
    return [_store(s) for s in await _nearest(latitude, longitude, count)]


@mcp.tool()
async def check_availability(
    query: str,
    latitude: float = HOME[0],
    longitude: float = HOME[1],
    stores: int = 3,
    channel: str = DEFAULT_CHANNEL,
    limit: int = 5,
) -> list[dict]:
    """Проверить наличие и цену товара в ближайших магазинах.

    Для каждого из ближайших магазинов делает поиск и возвращает совпадения
    с остатком (`in_stock_count`).

    Args:
        query: Что искать, например "гречка".
        latitude: Широта точки (по умолчанию центр Томска).
        longitude: Долгота точки.
        stores: Сколько ближайших магазинов проверить.
        channel: Канал продаж: "lo" доставка, "locc" самовывоз.
        limit: Сколько товаров показать по каждому магазину.
    """
    nearby = await _nearest(latitude, longitude, stores)

    async def one(s: dict) -> dict:
        sid = int(s["id"])
        data = await _get(
            "/catalog/v1/items",
            {"stores": sid, "channel": channel, "query": query, "limit": limit},
        )
        return {
            "store": _store(s),
            "found": data.get("total", 0),
            "products": [_product(p, sid) for p in data.get("items", [])],
        }

    return await asyncio.gather(*(one(s) for s in nearby))


@mcp.tool()
async def search_products(
    query: str,
    store_id: int = DEFAULT_STORE,
    channel: str = DEFAULT_CHANNEL,
    only_discounted: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Поиск товаров «Ленты». Цены в рублях.

    Args:
        query: Что искать, например "молоко".
        store_id: ID магазина (из nearest_stores). По умолчанию гипермаркет на Пушкина, 59.
        channel: Канал продаж: "lo" доставка, "locc" самовывоз Ленты Онлайн.
        only_discounted: Оставить только товары со скидкой (фильтр на стороне сервера MCP,
            применяется к уже полученной странице).
        limit: Товаров на странице.
        offset: Смещение для пагинации (начинать с 0).
    """
    data = await _get(
        "/catalog/v1/items",
        {"stores": store_id, "channel": channel, "query": query,
         "limit": limit, "offset": offset},
    )
    items = [_product(p, store_id) for p in data.get("items", [])]
    if only_discounted:
        items = [i for i in items if i["discount_percent"]]
    return {"total": data.get("total", 0), "offset": offset, "products": items}


@mcp.tool()
async def get_product(
    product_id: int, store_id: int = DEFAULT_STORE, channel: str = DEFAULT_CHANNEL
) -> dict:
    """Карточка товара по id: цена, скидка, вес, остаток.

    API «Ленты» не отдаёт состав и КБЖУ.

    Args:
        product_id: ID товара (из поиска или каталога).
        store_id: ID магазина.
        channel: Канал продаж ("lo" или "locc").
    """
    p = await _get(
        f"/catalog/v1/items/{product_id}", {"stores": store_id, "channel": channel}
    )
    result = _product(p, store_id)
    limit = p.get("saleLimit") or {}
    result["min_quantity"] = limit.get("minSaleQuantity")
    result["max_quantity"] = limit.get("maxSaleQuantity")
    features = p.get("features") or {}
    result["is_adult"] = features.get("isAdult")
    result["is_weight"] = features.get("isWeight")
    return result


@mcp.tool()
async def list_categories(
    parent_id: int | None = None,
    store_id: int = DEFAULT_STORE,
    channel: str = DEFAULT_CHANNEL,
) -> list[dict]:
    """Категории каталога. Без parent_id возвращает верхний уровень.

    Args:
        parent_id: ID родительской категории, чтобы получить подкатегории.
        store_id: ID магазина.
        channel: Канал продаж ("lo" или "locc").
    """
    params = {"stores": store_id, "channel": channel}
    if parent_id is None:
        params["levels"] = 1
    else:
        params["parentId"] = parent_id
    data = await _get("/catalog/v1/categories", params)
    return [_category(c) for c in data.get("categories", [])]


@mcp.tool()
async def get_category_products(
    category_id: int,
    store_id: int = DEFAULT_STORE,
    channel: str = DEFAULT_CHANNEL,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Товары категории (id из list_categories).

    Args:
        category_id: ID категории.
        store_id: ID магазина.
        channel: Канал продаж ("lo" или "locc").
        limit: Товаров на странице.
        offset: Смещение для пагинации (начинать с 0).
    """
    data = await _get(
        "/catalog/v1/items",
        {"stores": store_id, "channel": channel, "categoryId": category_id,
         "limit": limit, "offset": offset},
    )
    return {
        "total": data.get("total", 0),
        "offset": offset,
        "products": [_product(p, store_id) for p in data.get("items", [])],
    }


if __name__ == "__main__":
    mcp.run()
