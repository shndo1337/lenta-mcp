# Lenta MCP Server

Сервер [Model Context Protocol](https://modelcontextprotocol.io) для «Ленты» ([lenta.com](https://lenta.com)). Даёт LLM доступ к каталогу: поиск товаров, цены, скидки, категории и ближайшие магазины. Магазин по умолчанию — гипермаркет в Томске (Пушкина, 59).

> [!NOTE]
> Сервер использует официальный открытый Integration API «Ленты» ([спецификация](https://lenta.com/llms.txt)). Авторизация и ключи не нужны. Доступ только на чтение: корзина и заказы не затрагиваются. Проект не связан с «Лентой».

### Доступные инструменты

- `nearest_stores` — ближайшие магазины к точке с расстоянием и часами работы. Поле `id` в ответе используется как `store_id` в остальных инструментах.
    - `latitude` (number, необязательный): широта (по умолчанию центр Томска)
    - `longitude` (number, необязательный): долгота (по умолчанию центр Томска)
    - `count` (integer, необязательный): сколько магазинов вернуть (по умолчанию 5)

- `check_availability` — наличие и цена товара сразу в нескольких ближайших магазинах.
    - `query` (string, обязательный): поисковый запрос
    - `latitude`, `longitude` (number, необязательные): точка, от которой считать расстояние (по умолчанию центр Томска)
    - `stores` (integer, необязательный): сколько ближайших магазинов проверить (по умолчанию 3)
    - `channel` (string, необязательный): `lo` или `locc` (по умолчанию `lo`)
    - `limit` (integer, необязательный): товаров по каждому магазину (по умолчанию 5)

- `search_products` — поиск товаров. Цены в рублях.
    - `query` (string, обязательный): поисковый запрос
    - `store_id` (integer, необязательный): ID магазина (по умолчанию 99, гипермаркет на Пушкина, 59)
    - `channel` (string, необязательный): `lo` — доставка, `locc` — самовывоз Ленты Онлайн (по умолчанию `lo`)
    - `only_discounted` (boolean, необязательный): оставить только товары со скидкой, применяется к полученной странице (по умолчанию false)
    - `limit` (integer, необязательный): товаров на странице (по умолчанию 20)
    - `offset` (integer, необязательный): смещение для пагинации (по умолчанию 0)

- `get_product` — карточка товара: цена, скидка, вес, остаток, ограничения на количество.
    - `product_id` (integer, обязательный): ID товара
    - `store_id`, `channel` (необязательные): как в `search_products`

- `list_categories` — категории каталога. Без `parent_id` возвращает верхний уровень.
    - `parent_id` (integer, необязательный): ID родительской категории
    - `store_id`, `channel` (необязательные): как в `search_products`

- `get_category_products` — товары категории.
    - `category_id` (integer, обязательный): ID категории из `list_categories`
    - `store_id`, `channel`, `limit`, `offset` (необязательные): как в `search_products`

## Установка

Требуется Python 3.10 или новее.

```
git clone https://github.com/shndo1337/lenta-mcp.git
cd lenta-mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

На Windows используйте `.venv\Scripts\` вместо `.venv/bin/`.

Проверить запуск можно командой `.venv/bin/python server.py`. Сервер работает через stdio и ждёт запросов клиента.

## Конфигурация

Во всех примерах укажите абсолютные пути к `python` из `.venv` и к `server.py`.

### Claude Code

```
claude mcp add lenta -- /путь/к/lenta-mcp/.venv/bin/python /путь/к/lenta-mcp/server.py
```

### Claude Desktop

Добавьте в `claude_desktop_config.json` и перезапустите приложение.

<details>
<summary>Расположение файла</summary>

- Linux: `~/.config/Claude/claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
</details>

```json
{
  "mcpServers": {
    "lenta": {
      "command": "/путь/к/lenta-mcp/.venv/bin/python",
      "args": ["/путь/к/lenta-mcp/server.py"]
    }
  }
}
```

### Cursor, Cline и другие клиенты

Подойдёт тот же блок `mcpServers`.

### Свой адрес и магазин

Магазин, канал и точка отсчёта (ваш дом) задаются переменными окружения. Координаты адреса можно взять на карте, а `id` магазина — через `nearest_stores`:

```json
{
  "mcpServers": {
    "lenta": {
      "command": "/путь/к/lenta-mcp/.venv/bin/python",
      "args": ["/путь/к/lenta-mcp/server.py"],
      "env": {
        "LENTA_STORE_ID": "99",
        "LENTA_CHANNEL": "lo",
        "LENTA_LAT": "56.4887",
        "LENTA_LON": "84.9523"
      }
    }
  }
}
```

## Примеры запросов

- «Найди в Ленте молоко со скидкой»
- «Есть ли гречка в ближайших к проспекту Ленина, 40 магазинах Ленты?»
- «Покажи товары из категории Крупы»

## Ограничения

- Состав и КБЖУ API не отдаёт.
- Канал самовывоза `cc` из документации на момент написания возвращает ошибку 500; используйте `lo` или `locc`.
- Остатки (`in_stock_count`) относятся к онлайн-каталогу магазина и могут отличаться от наличия на полке.
- Зоомагазины («Ленты» типа `zoo`) в выдачу ближайших магазинов не входят.

## Лицензия

MIT, см. [LICENSE](LICENSE).
