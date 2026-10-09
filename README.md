# PumVPN Story Factory — MVP

Бесплатная локальная генерация **5 вертикальных роликов 1080×1920**: история → Piper-озвучка → faster-whisper таймкоды слов → ASS-субтитры → FFmpeg → MP4. В конце ролика появляется трёхсекундная заставка PUM VPN. Публикация в TikTok **не автоматизирована**.

## Установка (Manjaro / Arch)

Нужны Python 3.10–3.12, `ffmpeg` с фильтром `ass`, интернет при первой загрузке моделей.

```bash
sudo pacman -S --needed ffmpeg python python-pip ttf-dejavu
cd pumvpn_tiktok_mvp
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m piper.download_voices --data-dir voices ru_RU-irina-medium
python generate.py --limit 1
python generate.py
```

Если установлен Python 3.13+ и возникнут ошибки совместимости, используйте отдельное окружение с Python 3.11/3.12 (через pyenv/uv). Убедитесь, что фильтр доступен: `ffmpeg -filters | grep ass`.

## Установка (Windows PowerShell)

Установите Python 3.11/3.12, FFmpeg и добавьте ffmpeg.exe/ffprobe.exe в PATH.

```powershell
cd pumvpn_tiktok_mvp
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m piper.download_voices --data-dir voices ru_RU-irina-medium
python generate.py --limit 1
python generate.py
```

Первый запуск **сам скачает** модель faster-whisper `small` (несколько сотен МБ). Для экономии ресурсов замените в `config.json` `small` на `base` или `tiny` (субтитры станут менее точными). Модель Piper скачивается командой выше. Модели хранятся локально, после загрузки интернет для рендеринга не нужен.

## Как добавить свой материал

- `stories.json` — 5 историй, меняйте поля `title` и `text`. Не превышайте ~130–160 слов на видео, если хотите короткий формат.
- `assets/backgrounds/` — добавьте свои `mp4`, `webm`, `jpg` или `png`, фон выбирается по кругу. Если папка пустая, используется процедурный тёмный фон.
- `assets/music/` — опциональный фоновый трек, выбирается по кругу. Используйте музыку с подходящей лицензией.
- `config.json` — голос, громкость фоновой музыки, параметры рендера, рекламная надпись и CTA.
- `output/` — готовые MP4, WAV и ASS (субтитры можно исправить вручную и перерендерить).

Видео используют **нейтральный текст рекламной заставки**. Замените `brand_line` на фактический, корректный CTA, например `VPN — ссылка в профиле`; соблюдайте требования маркировки рекламы и правила площадки.

## Частые проблемы

1. **Нет русской модели Piper** — проверьте `python -m piper.download_voices --data-dir voices ru_RU-irina-medium`. Для доступных названий: `python -m piper.download_voices | grep ru_RU`.
2. **`No such filter: ass`** — нужен FFmpeg, собранный с `libass`.
3. **Заставка/текст не видны** — установите DejaVu Sans либо укажите установленный шрифт в `config.json`.
4. **Субтитры содержат ошибки** — Whisper транскрибирует уже сгенерированную речь, поэтому может ошибаться. Просматривайте MP4 перед публикацией.
5. **Тест без Whisper** — `python generate.py --limit 1 --skip-whisper`. В этом режиме таймкоды **приблизительные**, полезен только для проверки конвейера.
6. **Windows и путь с кириллицей** — для FFmpeg лучше распаковать проект в путь вроде `C:\video-factory\pumvpn_tiktok_mvp`.

## Границы MVP

Сценарии готовые, а не генерируются через LLM автоматически. Не делает ИИ-видеоряд из текста и не скачивает чужие клипы. Для красивого результата положите собственные фоны в `assets/backgrounds`. TTS и выравнивание выполняются локально после первоначальной загрузки моделей. Результат проверяйте: Whisper не гарантирует точность, а синтетический голос может звучать неестественно. Права на фоновые материалы и музыку — ответственность публикующего.
