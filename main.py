import os
import requests

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

r = requests.post(
    url,
    data={
        "chat_id": CHAT_ID,
        "text": "🔔 빗썸 알람 테스트 성공!"
    },
    timeout=10
)

r.raise_for_status()
print("Telegram message sent.")
