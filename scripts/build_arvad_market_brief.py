#!/usr/bin/env python3
import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional


SCRIPT_PATH = Path(__file__).resolve()
BASE_DIR = SCRIPT_PATH.parents[1] if SCRIPT_PATH.parent.name == "scripts" else SCRIPT_PATH.parent
OUTPUT_DIR = BASE_DIR / "output"
JSON_DIR = OUTPUT_DIR / "json"
MD_DIR = OUTPUT_DIR / "markdown"
HTML_DIR = OUTPUT_DIR / "html"
CACHE_DIR = BASE_DIR / "cache"
LATEST_CACHE_PATH = CACHE_DIR / "latest_success.json"
LOCAL_TZ = timezone(timedelta(hours=5))

BITRIX_DIALOG_ID = os.environ.get("ARVAD_BITRIX_DIALOG_ID", "chat4071")

COMPANY_CONTEXT = """ARVAD GROUP производит сантехнику в Китае и России; доля производства в России около 15%.
Около 60% ассортимента и продаж составляют смесители.
Основные рынки: Россия и Беларусь.
Нужны сигналы для управленческих решений: продажи, закупки, производство, логистика, ассортимент, цены, конкуренты, каналы, макроэкономика, регулирование."""

PROMPT_RULES = """Подготовь недельную управленческую сводку для ARVAD GROUP.
Формат результата строго JSON с полями:
title, day_assessment, main_signals, fx_block, actions_today, watch_signals.
main_signals: массив из 6-10 объектов с полями source, happened, why, action.
actions_today: 3-5 коротких конкретных действий.
watch_signals: 2-4 темы.
Пиши по-русски, коротко и по делу.
Фокус: маркетплейсы, DIY, ритейл, стройка, импорт, Китай, Беларусь, регулирование, конкуренты.
Если обязательных источников мало, честно говори это в day_assessment.
Не добавляй ничего вне JSON."""

BLOCK_QUOTAS = {
    "Маркетплейсы и каналы": 4,
    "Стройка, жильё и ремонт": 5,
    "DIY ритейл": 5,
    "Импорт, Китай, логистика и платежи": 4,
    "Регулирование и локализация": 4,
    "Беларусь": 3,
}

RELEVANT_KEYWORDS = {
    "marketplace": ["wildberries", "ozon", "яндекс маркет", "marketplace", "маркетплейс", "seller", "селлер", "комисси", "карточ"],
    "logistics": ["топлив", "логист", "достав", "перевоз", "склад", "fbo", "fbs", "себестоим"],
    "china": ["китай", "юан", "cny", "импорт", "тамож", "пошлин", "трансгранич", "платеж"],
    "housing": ["ипотек", "жиль", "новостро", "ремонт", "строитель", "дом", "квартир", "отделк"],
    "regulation": ["гост", "локализ", "минпром", "сертифик", "регулирован", "поддержк", "маркиров"],
    "belarus": ["беларус", "минск", "pravo.by", "belta", "еаэс"],
    "retail": ["diy", "ритейл", "сеть", "лемана", "леруа", "петрович", "максидом", "obi", "всеинструменты"],
    "design": ["дизайн", "интерьер", "коллекц", "ванн", "душев", "смесител"],
}

CATEGORY_PRIORITY_KEYWORDS = [
    "сантех",
    "смесител",
    "душев",
    "ванн",
    "раковин",
    "унитаз",
    "инсталляц",
    "дизайн ванной",
    "санфаянс",
    "аксессуар для ванной",
    "ремонт",
    "отделк",
    "новостро",
    "ипотек",
    "строитель",
    "diy",
    "петрович",
    "леруа",
    "лемана",
    "максидом",
    "всеинструменты",
]

BUSINESS_SIGNAL_KEYWORDS = [
    "wildberries",
    "ozon",
    "яндекс маркет",
    "маркетплейс",
    "комисси",
    "логист",
    "достав",
    "склад",
    "китай",
    "юан",
    "импорт",
    "тамож",
    "платеж",
    "локализ",
    "маркиров",
    "гост",
    "беларус",
    "еаэс",
]

STRONG_KEEP_KEYWORDS = [
    "wildberries",
    "ozon",
    "маркетплейс",
    "комисси",
    "лемана",
    "леруа",
    "петрович",
    "максидом",
    "diy",
    "сантех",
    "смесител",
    "маркиров",
    "топлив",
    "логист",
    "ипотек",
    "новостро",
    "ремонт",
    "китай",
    "юан",
    "импорт",
    "тамож",
    "платеж",
    "беларус",
    "гост",
    "всеинструменты",
    "яндекс маркет",
    "душев",
    "коллекц",
]

EXCLUDE_KEYWORDS = [
    "морожен",
    "молочн",
    "коктейл",
    "сосиск",
    "сардел",
    "птицевод",
    "мясокомбинат",
    "мясо",
    "птиц",
    "морепродукт",
    "напитк",
    "кофе",
    "чай",
    "шоколад",
    "мороженое",
    "продукт питан",
    "еда",
    "ресторан",
    "доставк[аи] еды",
    "робокурьер",
    "авто",
    "автомобил",
    "палат",
    "сапборд",
]

IRRELEVANT_KEYWORDS = [
    "спорт",
    "матч",
    "олимпиад",
    "теннис",
    "дрон",
    "бпла",
    "убий",
    "актер",
    "iphone",
    "apple",
    "свадьб",
    "суд отправил",
    "мотоцикл",
    "кинотеатр",
    "посольств",
]

MANDATORY_SOURCES = {
    "Retailer.ru": "https://retailer.ru/feed/",
    "Retail.ru": "https://www.retail.ru/rss/news/",
    "РБК": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "Коммерсантъ": "https://www.kommersant.ru/RSS/news.xml",
    "Интерфакс": "https://www.interfax.ru/rss.asp",
}

ADDITIONAL_SOURCES = {
    "БЕЛТА": "https://belta.by/rss",
}

COMPETITOR_CHANNELS = {
    "IDDIS Telegram": {
        "url": "https://t.me/s/iddisgram",
        "signal": "дизайн и комплектные интерьерные решения",
    },
    "ESKO Telegram": {
        "url": "https://t.me/s/eskorus",
        "signal": "акции, новые коллекции, сервисные новости",
    },
    "RMS Telegram": {
        "url": "https://t.me/s/RMStoday",
        "signal": "монтаж, product education, трафик в маркетплейсы",
    },
}


@dataclass
class Article:
    source: str
    title: str
    url: str
    published_at: str
    snippet: str
    mandatory: bool
    score: int
    theme: str


@dataclass
class CompetitorSignal:
    source: str
    url: str
    published_at: str
    summary: str
    why: str


def ensure_output_dirs() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    MD_DIR.mkdir(parents=True, exist_ok=True)
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def fetch_url(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def normalize_text(text: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", text or "")
    clean = clean.replace("&nbsp;", " ")
    clean = clean.replace("&#33;", "!")
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def slugify_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(LOCAL_TZ)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=LOCAL_TZ)
            return dt.astimezone(LOCAL_TZ)
        except ValueError:
            continue
    return None


def find_child_text(node: ET.Element, tag_name: str) -> str:
    for child in list(node):
        if child.tag.split("}")[-1] == tag_name:
            return child.text or ""
    return ""


def detect_theme(text: str) -> str:
    lowered = text.lower()
    best_theme = "retail"
    best_hits = 0
    for theme, keywords in RELEVANT_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in lowered)
        if hits > best_hits:
            best_theme = theme
            best_hits = hits
    return best_theme


def count_keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def has_regex_pattern(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def is_category_article(text: str) -> bool:
    return count_keyword_hits(text, CATEGORY_PRIORITY_KEYWORDS) > 0


def is_business_signal_article(text: str) -> bool:
    return count_keyword_hits(text, BUSINESS_SIGNAL_KEYWORDS) > 0


def score_article(source: str, title: str, snippet: str, mandatory: bool) -> int:
    text = f"{title} {snippet}".lower()
    score = 0
    for keywords in RELEVANT_KEYWORDS.values():
        for keyword in keywords:
            if keyword in text:
                score += 3 if len(keyword) > 5 else 1
    score += count_keyword_hits(text, CATEGORY_PRIORITY_KEYWORDS) * 4
    score += count_keyword_hits(text, BUSINESS_SIGNAL_KEYWORDS) * 2
    if has_regex_pattern(text, EXCLUDE_KEYWORDS):
        score -= 12
    if mandatory:
        score += 5
    if any(word in text for word in ["wildberries", "ozon", "ипотек", "китай", "топлив", "логист", "лемана"]):
        score += 4
    return score


def is_relevant(title: str, snippet: str) -> bool:
    text = f"{title} {snippet}".lower()
    if has_regex_pattern(text, EXCLUDE_KEYWORDS) and not is_category_article(text):
        return False
    if any(keyword in text for keyword in IRRELEVANT_KEYWORDS) and not any(
        keyword in text for keyword in STRONG_KEEP_KEYWORDS
    ):
        return False
    if is_category_article(text):
        return True
    if is_business_signal_article(text):
        return True
    return any(keyword in text for keyword in STRONG_KEEP_KEYWORDS)


def parse_rss(source: str, url: str, mandatory: bool, min_dt: datetime) -> list[Article]:
    data = fetch_url(url)
    root = ET.fromstring(data)
    items = [node for node in root.iter() if node.tag.split("}")[-1] == "item"]
    articles: list[Article] = []
    for item in items:
        title = normalize_text(find_child_text(item, "title"))
        link = normalize_text(find_child_text(item, "link"))
        pub_date = find_child_text(item, "pubDate") or find_child_text(item, "date")
        snippet = normalize_text(find_child_text(item, "description") or find_child_text(item, "full-text"))
        if not title or not link:
            continue
        dt = parse_date(pub_date)
        if dt and dt < min_dt:
            continue
        score = score_article(source, title, snippet, mandatory)
        if score < 5 or not is_relevant(title, snippet):
            continue
        articles.append(
            Article(
                source=source,
                title=title,
                url=link,
                published_at=(dt or datetime.now(LOCAL_TZ)).strftime("%Y-%m-%d %H:%M"),
                snippet=snippet[:420],
                mandatory=mandatory,
                score=score,
                theme=detect_theme(f"{title} {snippet}"),
            )
        )
    return articles


def fetch_cbr_rates(run_date: datetime) -> dict[str, str]:
    url = f"https://www.cbr.ru/scripts/XML_daily.asp?date_req={run_date.strftime('%d/%m/%Y')}"
    root = ET.fromstring(fetch_url(url))
    result = {}
    for valute in root.findall("Valute"):
        code = valute.findtext("CharCode")
        if code in {"USD", "CNY"}:
            result[code] = valute.findtext("Value", "")
    return result


def fetch_cbr_rates_safe(run_date: datetime) -> dict[str, str]:
    try:
        return fetch_cbr_rates(run_date)
    except Exception as exc:
        print(f"Warning: failed to fetch CBR rates: {exc}", file=sys.stderr)
        return {}


def parse_rate_value(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def fetch_cbr_weekly_rates(run_date: datetime, days: int = 7) -> dict[str, list[dict[str, str]]]:
    history = {"USD": [], "CNY": []}
    for offset in range(days - 1, -1, -1):
        current_date = run_date - timedelta(days=offset)
        rates = fetch_cbr_rates_safe(current_date)
        for code in ("USD", "CNY"):
            history[code].append(
                {
                    "date": current_date.strftime("%d.%m"),
                    "value": rates.get(code, ""),
                }
            )
    return history


def build_fx_forecast(history: list[dict[str, str]], code: str) -> str:
    values = [parse_rate_value(item["value"]) for item in history if parse_rate_value(item["value"]) is not None]
    if len(values) < 2:
        return f"{code}: данных недостаточно для прогноза."
    change = values[-1] - values[0]
    pct = (change / values[0] * 100) if values[0] else 0.0
    if abs(pct) < 1.0:
        trend = "боковик"
        action = "держать короткий горизонт фиксации, без агрессивных пересмотров цен"
    elif change > 0:
        trend = "умеренный рост"
        action = "не затягивать платежи и проверить запас по валютной марже"
    else:
        trend = "умеренное снижение"
        action = "можно точечно отложить часть конверсий, но без накопления риска"
    return f"{code}: за неделю {trend} ({pct:+.1f}%). Инерционный прогноз на новую неделю: {trend}; действие: {action}."


def gather_articles(run_date: datetime, lookback_hours: int) -> list[Article]:
    min_dt = run_date - timedelta(hours=lookback_hours)
    articles: list[Article] = []
    for source, url in MANDATORY_SOURCES.items():
        try:
            articles.extend(parse_rss(source, url, True, min_dt))
        except Exception as exc:
            print(f"Warning: failed to fetch mandatory source {source}: {exc}", file=sys.stderr)
    for source, url in ADDITIONAL_SOURCES.items():
        try:
            articles.extend(parse_rss(source, url, False, min_dt))
        except Exception as exc:
            print(f"Warning: failed to fetch additional source {source}: {exc}", file=sys.stderr)

    unique: dict[str, Article] = {}
    for article in sorted(articles, key=lambda item: (item.score, item.published_at), reverse=True):
        unique.setdefault(article.url, article)
    return list(unique.values())


def fetch_competitor_signals(run_date: datetime, lookback_hours: int) -> list[CompetitorSignal]:
    min_dt = run_date - timedelta(hours=lookback_hours)
    signals: list[CompetitorSignal] = []
    pattern = re.compile(
        r'data-post="[^"]+".*?<div class="tgme_widget_message_text js-message_text"[^>]*>(.*?)</div>.*?<time datetime="([^"]+)"',
        re.S,
    )
    for name, config in COMPETITOR_CHANNELS.items():
        try:
            html = fetch_url(config["url"], timeout=40).decode("utf-8", errors="ignore")
        except Exception as exc:
            print(f"Warning: failed to fetch competitor channel {name}: {exc}", file=sys.stderr)
            continue
        for text_html, dt_raw in pattern.findall(html):
            dt = parse_date(dt_raw)
            if not dt or dt < min_dt:
                continue
            text = normalize_text(text_html)
            if not text:
                continue
            signals.append(
                CompetitorSignal(
                    source=name,
                    url=config["url"],
                    published_at=dt.strftime("%Y-%m-%d %H:%M"),
                    summary=text[:420],
                    why=f"Открытый канал конкурента показывает, как он использует digital-контур: {config['signal']}.",
                )
            )
        # Keep only the latest 2 visible posts per channel to avoid overloading the brief.
    deduped: list[CompetitorSignal] = []
    seen = {}
    for signal in sorted(signals, key=lambda item: item.published_at, reverse=True):
        count = seen.get(signal.source, 0)
        if count >= 2:
            continue
        deduped.append(signal)
        seen[signal.source] = count + 1
    return deduped


def article_why(theme: str) -> str:
    mapping = {
        "marketplace": "Это влияет на маржу и управляемость продаж на маркетплейсах, где для ARVAD важны цены, промо и unit economics по смесителям.",
        "logistics": "Это прямой риск для исполнения поставок, доступности товара и штрафов со стороны клиентов или площадок.",
        "china": "Это влияет на импортную себестоимость, стабильность оплаты китайским поставщикам и риск задержек в закупке.",
        "housing": "Это опережающий индикатор спроса на ремонт, отделку и базовую сантехнику в ближайшие месяцы.",
        "regulation": "Это может перейти в новые требования к локализации, документации, материалам или тендерам.",
        "belarus": "Это важно для белорусского канала: может влиять на продажи, импорт, цены и регуляторные риски.",
        "retail": "Это сигнал по каналам сбыта и требованиям сетей, который может повлиять на ассортимент и условия работы.",
        "design": "Это сигнал по ассортиментным трендам и языку продукта, который влияет на карточки, презентацию и коммерческую подачу.",
    }
    return mapping.get(theme, mapping["retail"])


def article_action(theme: str) -> str:
    mapping = {
        "marketplace": "Пересчитать цены, комиссии и промо по ключевым SKU на маркетплейсах и проверить, где нужна коррекция ассортимента.",
        "logistics": "Проверить SLA перевозчиков, запасы по ходовым SKU и риски задержек на ближайшие 1-2 недели.",
        "china": "Сверить комиссии, сроки и лимиты по платежным маршрутам в Китай и оценить влияние на ближайшие закупки.",
        "housing": "Сопоставить сигнал со спросом по регионам и понять, где усиливать склад, матрицу и активность продаж.",
        "regulation": "Проверить, нужны ли обновления в документации, локализации, упаковке или входных спецификациях клиентов.",
        "belarus": "Проверить влияние на белорусских партнеров, цены, импортные схемы и возможные локальные ограничения.",
        "retail": "Связаться с ключевыми сетями или аккаунтами и уточнить, меняются ли условия, требования или приоритетные категории.",
        "design": "Проверить, нужно ли усилить продуктовую и визуальную подачу в карточках и презентациях по ключевым сериям.",
    }
    return mapping.get(theme, mapping["retail"])


def select_main_articles(articles: list[Article]) -> list[Article]:
    selected: list[Article] = []
    used_urls = set()
    category_terms = [
        "сантех",
        "смесител",
        "душев",
        "ванн",
        "ремонт",
        "новостро",
        "строитель",
        "diy",
        "леруа",
        "лемана",
        "петрович",
        "всеинструменты",
    ]
    preferred_terms = [
        "wildberries",
        "ozon",
        "маркиров",
        "топлив",
        "лемана",
        "ипотек",
        "китай",
        "платеж",
        "беларус",
    ]
    for term in category_terms:
        for article in articles:
            haystack = f"{article.title} {article.snippet}".lower()
            if article.url in used_urls:
                continue
            if term in haystack:
                selected.append(article)
                used_urls.add(article.url)
                break
    for term in preferred_terms:
        for article in articles:
            haystack = f"{article.title} {article.snippet}".lower()
            if article.url in used_urls:
                continue
            if term in haystack:
                selected.append(article)
                used_urls.add(article.url)
                break
    for article in articles:
        if article.url in used_urls:
            continue
        haystack = f"{article.title} {article.snippet}".lower()
        if has_regex_pattern(haystack, EXCLUDE_KEYWORDS) and not is_category_article(haystack):
            continue
        if len(selected) >= 8:
            break
        selected.append(article)
        used_urls.add(article.url)
    return selected[:8]


def classify_article_block(article: Article) -> Optional[str]:
    haystack = f"{article.title} {article.snippet}".lower()
    if any(keyword in haystack for keyword in ["беларус", "минск", "belta", "еаэс", "брест", "право.by"]):
        return "Беларусь"
    if any(keyword in haystack for keyword in ["wildberries", "ozon", "яндекс маркет", "маркетплейс", "селлер", "комисси", "карточ", "авито"]):
        return "Маркетплейсы и каналы"
    if any(keyword in haystack for keyword in ["ипотек", "новостро", "ремонт", "отделк", "строитель", "жиль", "квартир", "дом"]):
        return "Стройка, жильё и ремонт"
    if any(keyword in haystack for keyword in ["diy", "лемана", "леруа", "петрович", "максидом", "всеинструменты", "obi"]):
        return "DIY ритейл"
    if any(keyword in haystack for keyword in ["китай", "юан", "cny", "импорт", "тамож", "пошлин", "платеж", "логист", "достав", "склад", "топлив", "перевоз"]):
        return "Импорт, Китай, логистика и платежи"
    if any(keyword in haystack for keyword in ["гост", "локализ", "минпром", "сертифик", "регулирован", "поддержк", "маркиров", "российской полке", "налогооблож"]):
        return "Регулирование и локализация"
    return None


def article_to_signal(article: Article) -> dict[str, str]:
    happened = article.snippet or article.title
    if happened and not happened.endswith("."):
        happened += "."
    return {
        "source": article.source,
        "happened": happened[:360],
        "why": article_why(article.theme),
        "action": article_action(article.theme),
    }


def build_grouped_signals(articles: list[Article]) -> dict[str, list[dict[str, str]]]:
    grouped = {block: [] for block in BLOCK_QUOTAS}
    used_urls = set()
    ordered_articles = sorted(articles, key=lambda item: (item.score, item.published_at), reverse=True)
    for article in ordered_articles:
        if article.url in used_urls:
            continue
        block = classify_article_block(article)
        if not block:
            continue
        if len(grouped[block]) >= BLOCK_QUOTAS[block]:
            continue
        grouped[block].append(article_to_signal(article))
        used_urls.add(article.url)
    return grouped


def flatten_grouped_signals(grouped_signals: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    flat = []
    for block in BLOCK_QUOTAS:
        flat.extend(grouped_signals.get(block, []))
    return flat


def build_fallback_summary(
    articles: list[Article],
    competitor_signals: list[CompetitorSignal],
    run_date: datetime,
    rates: dict[str, str],
    fx_history: dict[str, list[dict[str, str]]],
) -> dict:
    grouped_signals = build_grouped_signals(articles)
    selected_articles = flatten_grouped_signals(grouped_signals)
    dominant_themes = []
    for theme in ("marketplace", "logistics", "china", "housing", "regulation", "belarus", "design"):
        if any(article.theme == theme for article in articles):
            dominant_themes.append(theme)
    theme_names = {
        "marketplace": "маркетплейсы",
        "logistics": "логистика",
        "china": "расчеты с Китаем",
        "housing": "спрос на ремонт и стройку",
        "regulation": "регулирование",
        "belarus": "Беларусь",
        "design": "ассортимент и дизайн",
    }
    day_assessment = (
        f"Неделя была {'плотной' if len(articles) >= 8 else 'умеренной'} по релевантным сигналам; "
        f"доминируют: {', '.join(theme_names[t] for t in dominant_themes[:3]) or 'каналы и спрос'}. "
        f"По конкурентам открытый social-pass дал {len(competitor_signals)} наблюдаемых публикаций."
    )
    fx_forecast = {
        "USD": build_fx_forecast(fx_history.get("USD", []), "USD/RUB"),
        "CNY": build_fx_forecast(fx_history.get("CNY", []), "CNY/RUB"),
    }
    fx_block = (
        f"Источник: ЦБ РФ. Дата: {run_date.strftime('%d.%m.%Y')}. "
        f"USD/RUB: {rates.get('USD', 'н/д')}. CNY/RUB: {rates.get('CNY', 'н/д')}. "
        f"Прогноз: {fx_forecast['USD']} {fx_forecast['CNY']}"
    )
    actions_today = [
        "Пересчитать экономику Wildberries по топ-SKU смесителей и аксессуаров.",
        "Проверить карточки, атрибуты и документы по ключевым SKU.",
        "Развести прогноз спроса на новостройки и ремонт/замену.",
        "Проверить окно фиксации ближайших платежей Китаю.",
        "Сравнить активность конкурентов в Telegram с собственной digital-подачей.",
    ]
    watch_signals = [
        "Вторичный эффект комиссий маркетплейсов на цены и ассортимент.",
        "Беларусь и ЕАЭС: платежи, импорт и регуляторные изменения.",
        "Промо-активность конкурентов в Telegram и маркетплейсах.",
        "Спрос по контуру ремонт/замена против первичного жилья.",
    ]
    return {
        "title": f"ARVAD GROUP — weekly-сводка за {run_date.strftime('%d.%m.%Y')}",
        "day_assessment": day_assessment,
        "main_signals": selected_articles,
        "grouped_signals": grouped_signals,
        "fx_block": fx_block,
        "fx_history": fx_history,
        "fx_forecast": fx_forecast,
        "actions_today": actions_today,
        "watch_signals": watch_signals,
    }


def extract_response_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
        return payload["output_text"]
    chunks = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def call_openai(summary_seed: dict, articles: list[Article], competitor_signals: list[CompetitorSignal]) -> tuple[Optional[dict], str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, "OpenAI summary: no API key"
    model = os.environ.get("OPENAI_MODEL", "gpt-5")
    seed_json = {
        "company_context": COMPANY_CONTEXT,
        "prebuilt_summary": summary_seed,
        "articles": [asdict(article) for article in articles[:12]],
        "competitor_signals": [asdict(item) for item in competitor_signals[:6]],
    }
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": PROMPT_RULES}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": json.dumps(seed_json, ensure_ascii=False)}],
            },
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        text = extract_response_text(response_payload)
        if not text:
            return None, "OpenAI summary: empty response, fallback to rules"
        return json.loads(text), f"OpenAI summary: request succeeded with model {model}"
    except Exception as exc:
        print(f"OpenAI summarization failed, falling back to rules: {exc}", file=sys.stderr)
        return None, f"OpenAI summary: fallback after API error ({exc})"


def ensure_appendix(summary: dict, articles: list[Article], competitor_signals: list[CompetitorSignal]) -> dict:
    if "grouped_signals" not in summary:
        summary["grouped_signals"] = build_grouped_signals(articles)
    summary["main_signals"] = flatten_grouped_signals(summary["grouped_signals"])
    summary["appendix_items"] = [asdict(article) for article in articles[:18]]
    summary["competitor_signals"] = [asdict(item) for item in competitor_signals[:8]]
    return summary


def render_fx_history_markdown(summary: dict) -> list[str]:
    lines = ["## Курс валют: динамика за неделю", ""]
    for code in ("USD", "CNY"):
        lines.append(f"### {code}/RUB")
        for item in summary.get("fx_history", {}).get(code, []):
            lines.append(f"- {item['date']}: {item['value'] or 'н/д'}")
        forecast_text = summary.get("fx_forecast", {}).get(code)
        if forecast_text:
            lines.append(f"- Прогноз: {forecast_text}")
        lines.append("")
    return lines


def build_chart_svg(points: list[Optional[float]], color: str) -> str:
    width = 280
    height = 110
    padding_x = 10
    padding_y = 24
    valid = [point for point in points if point is not None]
    if len(valid) < 2:
        return ""
    min_v = min(valid)
    max_v = max(valid)
    span = max(max_v - min_v, 0.0001)
    coords = []
    markers = []
    for idx, point in enumerate(points):
        if point is None:
            continue
        x = padding_x + idx * ((width - 2 * padding_x) / max(len(points) - 1, 1))
        y = height - padding_y - ((point - min_v) / span) * (height - 2 * padding_y)
        coords.append(f"{x:.1f},{y:.1f}")
        label_y = max(12, y - 8)
        if label_y < 16:
            label_y = min(height - 6, y + 16)
        markers.append(
            f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3.5' fill='{color}' />"
            f"<text x='{x:.1f}' y='{label_y:.1f}' text-anchor='middle' "
            f"font-size='10' font-family='Arial, sans-serif' fill='{color}'>{point:.2f}</text>"
        )
    if len(coords) < 2:
        return ""
    polyline = " ".join(coords)
    return (
        f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}' role='img' aria-label='chart'>"
        f"<polyline fill='none' stroke='{color}' stroke-width='3' points='{polyline}' />"
        f"{''.join(markers)}"
        f"</svg>"
    )


def save_latest_cache(
    summary: dict,
    articles: list[Article],
    competitor_signals: list[CompetitorSignal],
    rates: dict[str, str],
    run_date: datetime,
) -> None:
    ensure_output_dirs()
    payload = {
        "saved_at": datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M"),
        "source_run_date": run_date.strftime("%Y-%m-%d"),
        "summary": summary,
        "articles": [asdict(article) for article in articles],
        "competitor_signals": [asdict(item) for item in competitor_signals],
        "rates": rates,
    }
    LATEST_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_latest_cache() -> Optional[dict]:
    if not LATEST_CACHE_PATH.exists():
        return None
    try:
        return json.loads(LATEST_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Warning: failed to read local cache: {exc}", file=sys.stderr)
        return None


def build_offline_summary(run_date: datetime, cached_payload: Optional[dict]) -> tuple[dict, list[Article], list[CompetitorSignal]]:
    if cached_payload:
        cached_summary = dict(cached_payload.get("summary") or {})
        cached_articles = [Article(**item) for item in cached_payload.get("articles", [])]
        cached_signals = [CompetitorSignal(**item) for item in cached_payload.get("competitor_signals", [])]
        cached_date_raw = cached_payload.get("source_run_date", "")
        cached_date = parse_date(f"{cached_date_raw} 07:30") if cached_date_raw else None
        cached_date_label = cached_date.strftime("%d.%m.%Y") if cached_date else cached_date_raw or "неизвестно"
        saved_at = cached_payload.get("saved_at", "неизвестно")

        cached_summary["title"] = f"ARVAD GROUP — weekly-сводка за {run_date.strftime('%d.%m.%Y')} (офлайн-режим)"
        cached_summary["day_assessment"] = (
            f"Интернет недоступен, поэтому выпуск собран из последнего успешного локального кэша. "
            f"Базовые выводы и приложение взяты из сводки от {cached_date_label}; кэш обновлён {saved_at}. "
            "После восстановления сети повторите сбор, чтобы подтянуть свежие новости, курсы и сигналы конкурентов."
        )
        cached_summary["fx_block"] = (
            "Офлайн-режим: актуальные курсы и прогноз не обновлены. "
            f"Используется последняя сохранённая версия блока: {cached_summary.get('fx_block', 'данные отсутствуют')}."
        )
        actions = list(cached_summary.get("actions_today", []))
        cached_summary["actions_today"] = [
            "Проверить подключение к интернету и повторить сбор сводки после восстановления доступа.",
            "Если выпуск нужен срочно, использовать текущую офлайн-версию как временную управленческую справку.",
            *actions[:3],
        ][:5]
        watch = list(cached_summary.get("watch_signals", []))
        cached_summary["watch_signals"] = [
            "Свежесть данных: после восстановления сети обновить все обязательные источники и соцсети конкурентов.",
            *watch[:3],
        ][:4]
        return cached_summary, cached_articles, cached_signals

    summary = {
        "title": f"ARVAD GROUP — weekly-сводка за {run_date.strftime('%d.%m.%Y')} (офлайн-режим)",
        "day_assessment": (
            "Интернет недоступен, а локальный кэш прошлых выпусков ещё не накоплен. "
            "Сформирована служебная офлайн-версия, чтобы автоматизация не падала и фиксировала состояние мониторинга."
        ),
        "main_signals": [
            {
                "source": "Система мониторинга",
                "happened": "Обязательные источники, курсы валют и публичные каналы конкурентов не были доступны по сети в момент запуска.",
                "why": "Это операционный риск: руководство остаётся без обновлённой картины рынка и каналов сбыта.",
                "action": "Восстановить доступ к сети и повторить сбор; до этого использовать предыдущие материалы вручную, если они есть вне системы.",
            }
        ],
        "fx_block": "Офлайн-режим: курсы USD/RUB и CNY/RUB не обновлены из ЦБ РФ, прогноз на неделю не сформирован.",
        "actions_today": [
            "Проверить интернет-подключение на компьютере, где работает автоматизация.",
            "После восстановления сети повторно запустить сбор сводки.",
            "Проверить доступ к Bitrix24, чтобы итоговый HTML можно было отправить в чат.",
        ],
        "watch_signals": [
            "Когда сеть восстановится, первыми проверить маркетплейсы, курсы валют и каналы конкурентов.",
            "Если офлайн-режим повторяется, проверить стабильность провайдера и DNS.",
        ],
    }
    return summary, [], []


def render_markdown(summary: dict, articles: list[Article], competitor_signals: list[CompetitorSignal]) -> str:
    lines = [f"# {summary['title']}", "", summary["day_assessment"], ""]
    lines.append("## Основные сигналы недели")
    lines.append("")
    for block, quota in BLOCK_QUOTAS.items():
        block_signals = summary.get("grouped_signals", {}).get(block, [])
        lines.append(f"### {block} (до {quota})")
        if not block_signals:
            lines.append("- Существенных сигналов за период не выделено.")
            lines.append("")
            continue
        for signal in block_signals:
            lines.extend(
                [
                    f"- Источник: {signal['source']}",
                    f"  Что произошло: {signal['happened']}",
                    f"  Почему важно: {signal['why']}",
                    f"  Что проверить: {signal['action']}",
                ]
            )
        lines.append("")
    lines.extend(["## Курсы и краткий взгляд", summary["fx_block"], ""])
    lines.extend(render_fx_history_markdown(summary))
    lines.append("## Что проверить сегодня")
    for item in summary["actions_today"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Сигналы для наблюдения"])
    for item in summary["watch_signals"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Конкуренты: открытые соцсети"])
    for signal in competitor_signals:
        lines.append(f"- [{signal.source}] {signal.published_at} - {signal.summary}")
    lines.extend(["", "## Приложение: публикации"])
    for article in articles:
        lines.append(f"- [{article.source}] {article.published_at} - {article.title} - {article.url}")
    return "\n".join(lines) + "\n"


def html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_html(summary: dict) -> str:
    grouped_sections = []
    for block, quota in BLOCK_QUOTAS.items():
        rows = []
        for signal in summary.get("grouped_signals", {}).get(block, []):
            rows.append(
                f"""
                <tr>
                  <td>{html_escape(signal['source'])}</td>
                  <td>{html_escape(signal['happened'])}</td>
                  <td>{html_escape(signal['why'])}</td>
                  <td>{html_escape(signal['action'])}</td>
                </tr>
                """
            )
        grouped_sections.append(
            f"""
            <div class="panel">
              <h3>{html_escape(block)} <span class="quota">до {quota}</span></h3>
              <table>
                <thead>
                  <tr><th>Источник</th><th>Что произошло</th><th>Почему важно</th><th>Что делать</th></tr>
                </thead>
                <tbody>
                  {''.join(rows) or '<tr><td colspan="4">Существенных сигналов за период не выделено.</td></tr>'}
                </tbody>
              </table>
            </div>
            """
        )
    competitor_rows = []
    for item in summary.get("competitor_signals", []):
        competitor_rows.append(
            f"""
            <tr>
              <td>{html_escape(item['source'])}</td>
              <td>{html_escape(item['published_at'])}</td>
              <td>{html_escape(item['summary'])}</td>
              <td>{html_escape(item['why'])}</td>
            </tr>
            """
        )
    actions_html = "".join(f"<li>{html_escape(item)}</li>" for item in summary["actions_today"])
    watch_html = "".join(f"<li>{html_escape(item)}</li>" for item in summary["watch_signals"])
    usd_points = [parse_rate_value(item["value"]) for item in summary.get("fx_history", {}).get("USD", [])]
    cny_points = [parse_rate_value(item["value"]) for item in summary.get("fx_history", {}).get("CNY", [])]
    usd_chart = build_chart_svg(usd_points, "#0c4d8a")
    cny_chart = build_chart_svg(cny_points, "#d96c00")
    appendix_rows = []
    for item in summary.get("appendix_items", []):
        appendix_rows.append(
            f"""
            <tr>
              <td>{html_escape(item['source'])}</td>
              <td>{html_escape(item['published_at'])}</td>
              <td><a href="{html_escape(item['url'])}">{html_escape(item['title'])}</a></td>
              <td>{html_escape(item['snippet'])}</td>
            </tr>
            """
        )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html_escape(summary['title'])}</title>
  <style>
    :root {{
      --blue: #0c4d8a;
      --text: #2f3640;
      --muted: #65707c;
      --line: #d7e0ea;
      --bg: #eef3f7;
      --panel: #ffffff;
      --chip: #edf4fa;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      font-family: Arial, Helvetica, sans-serif;
      color: var(--text);
    }}
    .deck {{
      width: min(1560px, calc(100vw - 36px));
      margin: 18px auto 36px;
    }}
    .slide {{
      min-height: 860px;
      background: var(--panel);
      margin-bottom: 22px;
      padding: 40px 54px 44px;
      box-shadow: 0 14px 36px rgba(28, 48, 73, 0.08);
      display: flex;
      flex-direction: column;
      gap: 24px;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      padding-bottom: 20px;
      border-bottom: 2px solid var(--line);
    }}
    .brand {{
      color: var(--blue);
      font-size: 34px;
      line-height: 0.95;
      font-weight: 500;
    }}
    .meta {{
      max-width: 520px;
      font-size: 16px;
      line-height: 1.45;
      color: var(--muted);
      text-align: right;
    }}
    .title {{
      font-size: 42px;
      line-height: 1.08;
      color: var(--blue);
      margin: 0;
    }}
    .subtitle {{
      margin: 0;
      font-size: 19px;
      line-height: 1.45;
    }}
    .grid-2, .grid-4 {{
      display: grid;
      gap: 16px;
    }}
    .grid-2 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .grid-4 {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
    .panel {{
      border: 1px solid var(--line);
      padding: 18px 20px;
      background: #fff;
    }}
    .panel h3 {{
      margin: 0 0 12px;
      font-size: 17px;
      color: var(--blue);
    }}
    .quota {{
      color: var(--muted);
      font-weight: 400;
      font-size: 14px;
    }}
    .metric .label {{
      font-size: 14px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 12px;
    }}
    .metric .value {{
      font-size: 34px;
      line-height: 1;
      color: var(--blue);
      font-weight: 700;
      margin-bottom: 10px;
    }}
    .metric .desc {{
      font-size: 15px;
      line-height: 1.45;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
      line-height: 1.35;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 8px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      color: var(--muted);
      font-weight: 700;
    }}
    ul {{
      margin: 0;
      padding-left: 20px;
      font-size: 16px;
      line-height: 1.45;
    }}
    li + li {{ margin-top: 8px; }}
    a {{ color: var(--blue); text-decoration: none; }}
    .chart-wrap {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .chart-note {{
      font-size: 14px;
      line-height: 1.4;
      color: var(--muted);
      margin-top: 8px;
    }}
    @media (max-width: 1200px) {{
      .slide {{ min-height: auto; padding: 28px; }}
      .grid-2, .grid-4, .chart-wrap {{ grid-template-columns: 1fr; }}
      .topbar {{ flex-direction: column; gap: 14px; }}
      .meta {{ text-align: left; }}
    }}
  </style>
</head>
<body>
  <main class="deck">
    <section class="slide">
      <div class="topbar">
        <div class="brand">Arvad<br>Group</div>
        <div class="meta">Еженедельная сводка для топ-менеджмента. Формат: HTML. Отправка в Bitrix24. Время запуска: понедельник 07:30, Екатеринбург.</div>
      </div>
      <h1 class="title">{html_escape(summary['title'])}</h1>
      <p class="subtitle">{html_escape(summary['day_assessment'])}</p>
      <div class="grid-4">
        <div class="panel metric"><div class="label">Фокус</div><div class="value">WB</div><div class="desc">Комиссии, карточки, unit economics.</div></div>
        <div class="panel metric"><div class="label">Спрос</div><div class="value">2</div><div class="desc">Отдельно: новостройки и ремонт/замена.</div></div>
        <div class="panel metric"><div class="label">Валюты</div><div class="value">USD/CNY</div><div class="desc">{html_escape(summary['fx_block'])}</div></div>
        <div class="panel metric"><div class="label">Конкуренты</div><div class="value">{len(summary.get('competitor_signals', []))}</div><div class="desc">Открытые сигналы из Telegram и других публичных каналов.</div></div>
      </div>
      <div class="grid-2">
        <div class="panel">
          <h3>Что проверить сегодня</h3>
          <ul>{actions_html}</ul>
        </div>
        <div class="panel">
          <h3>Сигналы для наблюдения</h3>
          <ul>{watch_html}</ul>
        </div>
      </div>
      <div class="panel">
        <h3>Курс валют: динамика за неделю и прогноз</h3>
        <p class="subtitle">{html_escape(summary['fx_block'])}</p>
        <div class="chart-wrap">
          <div>
            <h3>USD/RUB</h3>
            {usd_chart or '<div class="chart-note">Недостаточно данных для графика.</div>'}
            <div class="chart-note">{html_escape(summary.get('fx_forecast', {}).get('USD', ''))}</div>
          </div>
          <div>
            <h3>CNY/RUB</h3>
            {cny_chart or '<div class="chart-note">Недостаточно данных для графика.</div>'}
            <div class="chart-note">{html_escape(summary.get('fx_forecast', {}).get('CNY', ''))}</div>
          </div>
        </div>
      </div>
    </section>

    <section class="slide">
      <div class="topbar">
        <div class="brand">Arvad<br>Group</div>
        <div class="meta">Главные weekly-сигналы из обязательных и дополнительных источников.</div>
      </div>
      {''.join(grouped_sections)}
    </section>

    <section class="slide">
      <div class="topbar">
        <div class="brand">Arvad<br>Group</div>
        <div class="meta">Открытые соцсети конкурентов. Если public-feed недоступен, это тоже фиксируется как сигнал по качеству внешнего контура.</div>
      </div>
      <div class="panel">
        <h3>Конкуренты: публичные сигналы</h3>
        <table>
          <thead>
            <tr><th>Источник</th><th>Дата</th><th>Содержание</th><th>Почему важно</th></tr>
          </thead>
          <tbody>
            {''.join(competitor_rows) or '<tr><td colspan="4">Открытые weekly-сигналы конкурентов не извлеклись.</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>

    <section class="slide">
      <div class="topbar">
        <div class="brand">Arvad<br>Group</div>
        <div class="meta">Приложение: публикации, из которых собран weekly-pass.</div>
      </div>
      <div class="panel">
        <h3>Приложение: публикации</h3>
        <table>
          <thead>
            <tr><th>Источник</th><th>Дата</th><th>Заголовок</th><th>Фрагмент</th></tr>
          </thead>
          <tbody>
            {''.join(appendix_rows)}
          </tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""


def call_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def send_html_to_bitrix(html_path: Path, webhook_url: str, dialog_id: str) -> dict:
    folder = call_json(f"{webhook_url}im.disk.folder.get", {"DIALOG_ID": dialog_id})
    folder_id = int(folder["result"]["ID"])
    content = base64.b64encode(html_path.read_bytes()).decode("ascii")
    upload = call_json(
        f"{webhook_url}disk.folder.uploadfile",
        {
            "id": folder_id,
            "data": {"NAME": html_path.name},
            "fileContent": [html_path.name, content],
            "generateUniqueName": True,
        },
    )
    file_id = int(upload["result"]["ID"])
    commit = call_json(
        f"{webhook_url}im.disk.file.commit",
        {"DIALOG_ID": dialog_id, "FILE_ID": [file_id], "MESSAGE": ""},
    )
    return {"folder": folder, "upload": upload, "commit": commit}


def write_outputs(summary: dict, articles: list[Article], competitor_signals: list[CompetitorSignal], run_date: datetime) -> dict[str, Path]:
    slug = slugify_date(run_date)
    ensure_output_dirs()

    summary = ensure_appendix(summary, articles, competitor_signals)
    json_path = JSON_DIR / f"arvad-market-brief-{slug}.json"
    md_path = MD_DIR / f"arvad-market-brief-{slug}.md"
    html_path = HTML_DIR / f"arvad-market-brief-{slug}.html"

    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(summary, articles, competitor_signals), encoding="utf-8")
    html_path.write_text(render_html(summary), encoding="utf-8")
    return {"json": json_path, "markdown": md_path, "html": html_path}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Run date in YYYY-MM-DD. Defaults to local today.")
    parser.add_argument("--lookback-hours", type=int, default=168)
    parser.add_argument("--send-bitrix", action="store_true")
    args = parser.parse_args()

    if args.date:
        run_date = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ)
    else:
        run_date = datetime.now(LOCAL_TZ)

    articles = gather_articles(run_date, args.lookback_hours)
    competitor_signals = fetch_competitor_signals(run_date, args.lookback_hours)
    if not articles and not competitor_signals:
        raise RuntimeError("No relevant materials collected from configured sources.")

    rates = fetch_cbr_rates_safe(run_date)
    fx_history = fetch_cbr_weekly_rates(run_date)
    fallback = build_fallback_summary(articles, competitor_signals, run_date, rates, fx_history)
    openai_summary, openai_status = call_openai(fallback, articles, competitor_signals)
    print(openai_status)
    summary = openai_summary or fallback
    outputs = write_outputs(summary, articles, competitor_signals, run_date)
    save_latest_cache(summary, articles, competitor_signals, rates, run_date)

    if args.send_bitrix:
        webhook = os.environ.get("ARVAD_BITRIX_WEBHOOK_URL")
        if not webhook:
            print("Warning: ARVAD_BITRIX_WEBHOOK_URL is not set, skipping Bitrix24 delivery.", file=sys.stderr)
        else:
            try:
                result = send_html_to_bitrix(outputs["html"], webhook, BITRIX_DIALOG_ID)
                print(f"bitrix_message_id: {result['commit']['result']['MESSAGE_ID']}")
            except Exception as exc:
                print(f"Warning: failed to send HTML to Bitrix24: {exc}", file=sys.stderr)

    for label, path in outputs.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
