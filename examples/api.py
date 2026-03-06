"""
Пример работы с VK API без бота.

Демонстрирует:
- Создание экземпляра API
- Вызов методов через атрибуты (dot-notation)
- Вызов методов через .method()
- Загрузка фотографий
- Загрузка документов
- Использование кэширования
- Работа с переменными окружения ($TOKEN)
"""

import asyncio

import vkflow


async def main():
    # Токен можно передать напрямую или из переменной окружения через $
    api = vkflow.API("$VK_TOKEN")  # читает os.environ["VK_TOKEN"]
    # api = vkflow.API("vk1.a.xxxxxxxxx")  # или напрямую

    # --- Определение владельца токена ---
    token_owner, owner = await api.define_token_owner()
    print(f"Тип токена: {token_owner}")
    print(f"Владелец: {owner}")

    # --- Вызов методов через dot-notation ---
    # snake_case автоматически конвертируется в camelCase
    users = await api.users.get(user_ids=[1, 2, 3], fields=["photo_200"])

    for user in users:
        print(f"{user['first_name']} {user['last_name']}")

    # --- Вызов методов через .method() ---
    wall = await api.method("wall.get", owner_id=1, count=5)
    print(f"Записей на стене: {wall['count']}")

    # --- Кэширование ---
    # Следующий запрос будет закэширован (TTL по умолчанию - 2 часа)
    cached_users = await api.use_cache().users.get(user_ids=[1])
    # Повторный вызов с теми же параметрами вернёт результат из кэша
    cached_users_again = await api.use_cache().users.get(user_ids=[1])

    # --- Загрузка фотографий ---
    photos = await api.upload_photos_to_message(
        "path/to/photo.jpg",
        # Можно передавать: путь к файлу, URL, bytes, BytesIO
    )

    print(f"Загружено фотографий: {len(photos)}")
    # photos можно напрямую передать в attachment при отправке сообщения

    # --- Загрузка документов ---
    doc = await api.upload_doc_to_message(
        b"Hello, World!",
        "hello.txt",
        tags="test",
    )

    print(f"Загружен документ: {doc}")

    # --- Загрузка голосового сообщения ---
    voice = await api.upload_doc_to_message(
        open("voice.ogg", "rb").read(),
        "voice.ogg",
        type="audio_message",
    )

    # --- Загрузка видео ---
    video = await api.upload_video_to_message(
        "path/to/video.mp4",
        name="Моё видео",
        description="Описание видео",
        is_private=True,
    )

    # --- Отправка сообщения с вложениями ---
    await api.messages.send(
        peer_id=123456789,
        message="Привет!",
        attachment=photos,  # список Photo объектов
        random_id=vkflow.random_id(),
    )

    # --- Execute (VKScript) ---
    result = await api.execute(
        vkflow.CallMethod("users.get", user_ids="1"),
        vkflow.CallMethod("groups.getById"),
    )

    print(f"Результат: {result}")

    # Закрываем сессию
    await api.close_session()


if __name__ == "__main__":
    asyncio.run(main())
