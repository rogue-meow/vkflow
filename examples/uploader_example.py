"""
Пример загрузки и отправки файлов.

Демонстрирует:
- Загрузка фотографий через API (сырой VK upload)
- Загрузка документов через API
- Загрузка видео через API
- Отправка файлов через File в ctx.send (attachment/file)
- Скачивание файлов из сообщений
"""

import vkflow

from vkflow import commands
from vkflow.file import File


app = vkflow.App(prefixes=["!"])


# =============================================
# 1. Отправка файлов через File (простой способ)
# =============================================


@app.command()
async def photo(ctx: commands.Context):
    """Отправить фотографию"""
    # File автоматически определяет тип по расширению
    await ctx.send("Вот фото!", file=File("photo.jpg"))


@app.command()
async def doc(ctx: commands.Context):
    """Отправить документ"""
    await ctx.send("Вот документ!", file=File("document.pdf"))


@app.command()
async def voice(ctx: commands.Context):
    """Отправить голосовое сообщение"""
    await ctx.send(file=File("voice.ogg", type="audio_message"))


@app.command()
async def video_msg(ctx: commands.Context):
    """Отправить видео"""
    await ctx.send("Смотри видео!", file=File("video.mp4"))


@app.command()
async def multi_files(ctx: commands.Context):
    """Отправить несколько файлов"""
    await ctx.send(
        "Несколько файлов:",
        files=[
            File("photo1.jpg"),
            File("photo2.png"),
        ],
    )


@app.command()
async def photo_url(ctx: commands.Context, url: str):
    """Отправить фото по URL: !photo_url https://example.com/image.jpg"""
    await ctx.send("Фото по URL:", file=File(url, type="photo"))


@app.command()
async def raw_bytes(ctx: commands.Context):
    """Отправить файл из байтов"""
    content = b"Hello, World!"

    await ctx.send(
        "Текстовый файл:",
        file=File(content, type="doc", filename="hello.txt"),
    )


# =============================================
# 2. Загрузка через API (сырой VK upload)
# =============================================


@app.command()
async def upload_photo(ctx: commands.Context):
    """Загрузить фото через VK API напрямую"""
    # upload_photos_to_message возвращает список Photo объектов
    photos = await ctx.api.upload_photos_to_message(
        "photo.jpg",
        peer_id=ctx.peer_id,
    )

    # Передаём объект Photo напрямую как attachment
    await ctx.send("Загружено через API!", attachment=photos[0])


@app.command()
async def upload_multi_photo(ctx: commands.Context):
    """Загрузить несколько фото"""
    photos = await ctx.api.upload_photos_to_message(
        "photo1.jpg",
        "photo2.png",
        "photo3.jpg",
        peer_id=ctx.peer_id,
    )

    await ctx.send("Три фотографии:", attachments=photos)


@app.command()
async def upload_doc(ctx: commands.Context):
    """Загрузить документ через VK API"""
    doc = await ctx.api.upload_doc_to_message(
        b"print('Hello, World!')",
        "script.py",
        tags="python,code",
        peer_id=ctx.peer_id,
    )

    await ctx.send("Документ загружен!", attachment=doc)


@app.command()
async def upload_voice(ctx: commands.Context):
    """Загрузить голосовое сообщение через VK API"""
    with open("voice.ogg", "rb") as f:
        voice_bytes = f.read()

    doc = await ctx.api.upload_doc_to_message(
        voice_bytes,
        "voice.ogg",
        type="audio_message",
        peer_id=ctx.peer_id,
    )

    await ctx.send(attachment=doc)


@app.command()
async def upload_video(ctx: commands.Context):
    """Загрузить видео через VK API"""
    video = await ctx.api.upload_video_to_message(
        "video.mp4",
        name="Моё видео",
        description="Загружено ботом",
        is_private=True,
    )

    await ctx.send("Видео загружено!", attachment=video)


# =============================================
# 3. Скачивание файлов из сообщений
# =============================================


@app.command()
async def download(ctx: commands.Context):
    """Скачать фотографии из сообщения (ответьте на сообщение с фото)"""
    photos_bytes = await ctx.download_photos()

    if not photos_bytes:
        await ctx.send("В сообщении нет фотографий!")
        return

    await ctx.send(f"Скачано {len(photos_bytes)} фото, всего {sum(len(b) for b in photos_bytes)} байт")


@app.command()
async def get_docs(ctx: commands.Context):
    """Получить документы из сообщения"""
    docs = await ctx.fetch_docs()

    if not docs:
        await ctx.send("В сообщении нет документов!")
        return

    info = "\n".join(f"- {d.title} ({d.ext})" for d in docs)
    await ctx.send(f"Документы:\n{info}")


@app.command()
async def mirror(ctx: commands.Context):
    """Переслать фото из ответа обратно (зеркало)"""
    photos = await ctx.fetch_photos()

    if not photos:
        await ctx.send("Ответьте на сообщение с фотографиями!")
        return

    await ctx.send("Зеркало:", attachments=photos)


# =============================================
# Запуск
# =============================================

app.run("$VK_TOKEN")
