import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).date()
STATE_FILE = "alarm_state.json"
EXCLUDE = {"BTC", "USDT", "USDC"}

session = requests.Session()

with session.get("https://api.bithumb.com/public/ticker/ALL_KRW", timeout=20) as r:
    r.raise_for_status()
    result = r.json()
if result.get("status") != "0000":
    raise RuntimeError(f"빗썸 시세 조회 실패: {result.get('status')}")

try:
    with open(STATE_FILE, encoding="utf-8") as f:
        state = json.load(f)
except FileNotFoundError:
    state = {}

if state.get("date") != TODAY.isoformat():
    state = {"date": TODAY.isoformat(), "history": {}, "alerted": []}

history = state["history"]
alerted = set(state["alerted"])
signals = []

for coin, ticker in result["data"].items():
    if coin in EXCLUDE or not isinstance(ticker, dict) or coin in alerted:
        continue

    try:
        price = float(ticker["closing_price"])
        today_volume = float(ticker["units_traded"])
    except (KeyError, TypeError, ValueError):
        continue

    if price <= 0 or today_volume <= 0:
        continue

    if coin not in history:
        try:
            with session.get(
                "https://api.bithumb.com/v1/candles/days",
                params={
                    "market": f"KRW-{coin}",
                    "to": f"{TODAY.isoformat()} 00:00:00",
                    "count": 25,
                },
                timeout=20,
            ) as r:
                r.raise_for_status()
                candles = r.json()

            if (
                not isinstance(candles, list)
                or len(candles) < 25
                or candles[0]["candle_date_time_kst"][:10]
                != (TODAY - timedelta(days=1)).isoformat()
            ):
                continue

            history[coin] = {
                "closes": [float(c["trade_price"]) for c in candles[:25]],
                "yesterday_volume": float(
                    candles[0]["candle_acc_trade_volume"]
                ),
            }
        except (requests.RequestException, KeyError, TypeError, ValueError) as e:
            print(f"{coin} 일봉 조회 건너뜀: {e}")
            continue

        time.sleep(0.15)

    closes = history[coin]["closes"]  # 어제부터 과거 순서
    yesterday_volume = history[coin]["yesterday_volume"]
    if yesterday_volume <= 0:
        continue

    yesterday_ma5 = sum(closes[:5]) / 5
    yesterday_ma25 = sum(closes[:25]) / 25
    today_ma5 = (price + sum(closes[:4])) / 5
    today_ma25 = (price + sum(closes[:24])) / 25
    volume_ratio = today_volume / yesterday_volume

    if (
        yesterday_ma5 <= yesterday_ma25
        and today_ma5 > today_ma25
        and volume_ratio >= 3
    ):
        signals.append((volume_ratio, coin, price, today_ma5, today_ma25))

signals.sort(reverse=True)

if signals:
    lines = [
        "🚨 빗썸 일봉 장중 신호",
        datetime.now(KST).strftime("확인: %m월 %d일 %H:%M KST"),
        "5일선 25일선 상향 돌파 + 전일 거래량 3배 이상",
        "",
    ]
    for ratio, coin, price, ma5, ma25 in signals:
        lines.append(
            f"{coin} | {price:,.8g}원 | 거래량 {ratio:.1f}배"
            f" | 5일선 {ma5:,.8g} / 25일선 {ma25:,.8g}"
        )

    lines.append("\n장중 수치라 마감 전 신호가 사라질 수 있습니다.")
    for start in range(0, len(lines), 20):
        with session.post(
            f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}"
            "/sendMessage",
            data={
                "chat_id": os.environ["TELEGRAM_CHAT_ID"],
                "text": "\n".join(lines[start:start + 20]),
            },
            timeout=20,
        ) as r:
            r.raise_for_status()

    alerted.update(coin for _, coin, _, _, _ in signals)

state["alerted"] = sorted(alerted)
with open(STATE_FILE, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False)
