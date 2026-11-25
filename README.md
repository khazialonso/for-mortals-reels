# for-mortals-reels

Сборщик рилсов AI for Mortals и Biz for Mortals.

- `render/build.py` — рабочий сборщик v3: очередь из листа «Рилсы» → голос ElevenLabs с таймингами → HTML-композиция → видео HyperFrames → GitHub Release → результат в таблицу.
- `render/chars/` — персонажи (флешка для ИИ, калькулятор для бизнеса), `render/icons/` — 3D-иконки Fluent Emoji (MIT), список в `render/icons.py`.
- `render/test_items.json` + workflow `reels-test` — тестовая сборка без таблицы, результат в ветке `pilot-output`.
- `build.py` в корне — старый сборщик (edge-tts, стоки), не используется, оставлен для отката.
