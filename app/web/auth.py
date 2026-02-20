"""
Верификация данных от Telegram Login Widget.

Алгоритм (официальная документация Telegram):
1. Исключить поле "hash" из данных.
2. Отсортировать оставшиеся поля: "key=value", соединить через \n.
3. secret_key = SHA256(bot_token) — в виде байтов, НЕ hex.
4. HMAC-SHA256(secret_key, data_check_string) == hash → данные подлинные.
5. auth_date должен быть не старше 24 часов.
"""

import hashlib
import hmac
import time


def verify_telegram_auth(data: dict, bot_token: str) -> bool:
    """
    Возвращает True если данные от Telegram Login Widget подлинные.
    data — словарь параметров из callback URL (включая 'hash' и 'auth_date').
    """
    received_hash = data.get("hash")
    if not received_hash:
        return False

    # Проверяем свежесть (не старше 24 часов)
    try:
        auth_date = int(data["auth_date"])
    except (KeyError, ValueError):
        return False

    if time.time() - auth_date > 86400:
        return False

    # Строим data_check_string
    check_fields = {k: v for k, v in data.items() if k != "hash"}
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(check_fields.items())
    )

    # Вычисляем ожидаемый hash
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_hash, received_hash)
