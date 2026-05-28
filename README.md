     1|# hCaptcha Solver для Steam
     2|
     3|[English](#english) | [Русский](#русский)
     4|
     5|---
     6|
     7|## Русский
     8|
     9|### Описание
    10|
    11|Инструмент для автоматического решения hCaptcha на странице входа Steam. Поддерживает несколько стратегий решения с автоматическим переключением при неудаче.
    12|
    13|### Возможности
    14|
    15|🎤 **Аудио-челленджи** — распознавание речи через Google Speech API, Whisper (локально) или Vosk (оффлайн)
    16|
    17|🖼️ **Картинки** — классификация изображений через HuggingFace API, Imagga или локальную ResNet50
    18|
    19|🌐 **Сторонние API** — 2Captcha и AntiCaptcha как надёжный fallback (человек решает за вас)
    20|
    21|🔐 **Steam** — полный flow логина с поддержкой Steam Guard 2FA, сохранением сессий и куков
    22|
    23|🛡️ **Антидетект** — реалистичный fingerprint браузера, скрытие webdriver, имитация поведения человека
    24|
    25|🌐 **Прокси** — поддержка HTTP/SOCKS прокси с авторизацией
    26|
    27|### Установка
    28|
    29|```bash
    30|# Клонировать репозиторий
    31|git clone https://github.com/Asmodei513/hcaptcha-solver.git
    32|cd hcaptcha-solver
    33|
    34|# Установить зависимости
    35|pip install -r requirements.txt
    36|
    37|# Установить браузер Chromium для Playwright
    38|playwright install chromium
    39|
    40|# Опционально: установить дополнительные STT-движки
    41|pip install openai-whisper  # Локальный Whisper (нужен GPU для скорости)
    42|pip install vosk            # Оффлайн-распознавание (лёгкий)
    43|```
    44|
    45|### Конфигурация
    46|
    47|#### Через переменные окружения
    48|
    49|```bash
    50|# Данные Steam
    51|export STEAM_USERNAME="ваш_логин"
    52|export STEAM_PASSWORD="ваш_пароль"
    53|
    54|# API для капчи (опционально, но рекомендуется)
    55|export TWOCAPTCHA_API_KEY="ваш_ключ_2captcha"
    56|export ANTICAPTCHA_API_KEY="ваш_ключ_anticaptcha"
    57|
    58|# API для распознавания картинок (опционально)
    59|export HUGGINGFACE_API_KEY="ваш_ключ_huggingface"
    60|export IMAGGA_API_KEY="ваш_ключ_imagga"
    61|export IMAGGA_API_SECRET="ваш_секрет_imagga"
    62|
    63|# Прокси (опционально)
    64|export HCAPTCHA_PROXY_SERVER="http://proxy:port"
    65|export HCAPTCHA_PROXY_USERNAME="логин_прокси"
    66|export HCAPTCHA_PROXY_PASSWORD="пароль_прокси"
    67|
    68|# Режим отладки
    69|export HCAPTCHA_DEBUG="true"
    70|```
    71|
    72|#### Через Python-код
    73|
    74|```python
    75|from config import SolverConfig, SolverMethod, BrowserConfig, ProxyConfig
    76|
    77|config = SolverConfig(
    78|    primary_method=SolverMethod.AUDIO,
    79|    fallback_methods=[SolverMethod.IMAGE, SolverMethod.API_2CAPTCHA],
    80|    browser=BrowserConfig(
    81|        headless=False,           # False = видимый браузер
    82|        browser_type="chromium",   # chromium, firefox, webkit
    83|    ),
    84|    proxy=ProxyConfig(
    85|        enabled=True,
    86|        server="http://proxy:port",
    87|    ),
    88|    max_retries=5,
    89|    debug=True,
    90|)
    91|```
    92|
    93|### Использование
    94|
    95|#### Быстрый старт
    96|
    97|```python
    98|import asyncio
    99|from solver import solve_hcaptcha
   100|
   101|async def main():
   102|    success = await solve_hcaptcha(
   103|        url="https://store.steampowered.com/login/"
   104|    )
   105|    print(f"Капча решена: {success}")
   106|
   107|asyncio.run(main())
   108|```
   109|
   110|#### Вход в Steam
   111|
   112|```python
   113|import asyncio
   114|from steam_login import steam_login_with_captcha
   115|
   116|async def main():
   117|    result = await steam_login_with_captcha(
   118|        username="ваш_логин",
   119|        password="ваш_пароль",
   120|        steam_guard_code="12345",  # Код из Steam Guard (опционально)
   121|    )
   122|    
   123|    print(f"Статус: {result.status}")
   123|    print(f"Сообщение: {result.message}")
   124|    
   125|    if result.success:
   126|        print(f"Куки: {result.cookies}")
   127|
   128|asyncio.run(main())
   129|```
   130|
   131|#### Только аудио-решатель
   132|
   133|```python
   134|import asyncio
   135|from audio_solver import AudioSolver
   136|
   137|async def main():
   138|    solver = AudioSolver()
   139|    # Передайте page объект от Playwright
   140|    success = await solver.solve(page)
   141|    print(f"Аудио-челлендж решён: {success}")
   142|
   143|asyncio.run(main())
   144|```
   145|
   146|#### Только решатель картинок
   147|
   148|```python
   149|import asyncio
   150|from image_solver import ImageSolver
   151|
   152|async def main():
   153|    solver = ImageSolver()
   154|    # Передайте page объект от Playwright
   155|    success = await solver.solve(page)
   156|    print(f"Картинки решены: {success}")
   157|
   158|asyncio.run(main())
   159|```
   160|
   161|### Как это работает
   162|
   163|#### Цепочка решения (fallback)
   164|
   165|```
   166|Аудио-челлендж → Картинки → 2Captcha API → AntiCaptcha API
   167|```
   168|
   169|Каждый метод пробуется по порядку. Если один не сработал, автоматически переключается на следующий.
   169|
   170|#### Аудио-челлендж
   171|
   172|1. Обнаружение hCaptcha на странице
   173|2. Переключение в режим аудио
   174|3. Скачивание аудиофайла
   175|4. Распознавание текста через STT:
   176|   - Google Speech Recognition (бесплатно, нужен интернет)
   177|   - Whisper (локально, нужен GPU)
   178|   - Vosk (оффлайн, лёгкий)
   179|5. Ввод распознанного текста
   180|6. Проверка решения
   181|7. При неудаче — переход к следующему STT-движку
   182|
   183|#### Картинки
   184|
   185|1. Обнаружение hCaptcha
   186|2. Извлечение текста задания ("Выберите все самолёты")
   187|3. Скачивание всех 9 картинок
   188|4. Классификация каждой картинки:
   189|   - HuggingFace API (точно, нужен ключ)
   190|   - Imagga API (хорошая точность, нужен ключ)
   191|   - ResNet50 локально (бесплатно, менее точно)
   192|5. Сопоставление с заданием через маппинг категорий
   193|6. Клик по нужным картинкам
   194|7. Проверка решения
   195|
   196|#### Сторонние API
   197|
   198|1. Извлечение sitekey hCaptcha со страницы
   199|2. Отправка на 2Captcha/AntiCaptcha
   200|3. Человек решает капчу (обычно 10-60 сек)
   201|4. Получение готового токена
   202|5. Инжект токена в страницу
   203|
   204|### Структура файлов
   205|
   206|```
   207|hcaptcha-solver/
   208|├── config.py           # Конфигурация (dataclass'ы, env vars)
   209|├── solver.py           # Главный оркестратор с fallback
   210|├── audio_solver.py     # Аудио-решатель (STT)
   211|├── image_solver.py     # Решатель картинок (классификация)
   212|├── steam_login.py      # Steam логин + Steam Guard 2FA
   213|├── test_solver.py      # Тесты (7/7 ✅)
   214|├── requirements.txt    # Зависимости Python
   215|├── README.md           # Эта документация
   216|└── LICENSE             # MIT лицензия
   217|```
   218|
   219|### Антидетект
   220|
   221|Солвер подменяет fingerprint браузера:
   222|
   223|| Параметр | Значение |
   224||----------|----------|
   225|| User Agent | Windows Chrome (реалистичный) |
   226|| WebGL Vendor | Intel Inc. |
   227|| WebGL Renderer | Intel(R) UHD Graphics 630 |
   228|| Platform | Win32 |
   229|| Webdriver | Скрыт (navigator.webdriver = false) |
   225|| Плагины | Имитация реального списка |
   226|| Chrome Runtime | Инжект chrome объекта |
   227|
   228|### Прокси
   229|
   230|```python
   231|from config import SolverConfig, ProxyConfig
   232|
   233|config = SolverConfig(
   234|    proxy=ProxyConfig(
   235|        enabled=True,
   236|        server="http://proxy.example.com:8080",
   237|        username="логин",
   238|        password="пароль",
   239|    )
   240|)
   241|```
   242|
   243|### Решение проблем
   244|
   245|| Проблема | Решение |
   246||----------|---------|
   247|| Playwright не установлен | `playwright install chromium` |
   248|| Распознавание речи не работает | Проверьте интернет (Google) или установите Whisper/Vosk |
   249|| Картинки распознаются неточно | Установите `HUGGINGFACE_API_KEY` для лучшей точности |
   250|| hCaptcha не обнаружен | Проверьте, что сайт использует hCaptcha (не reCAPTCHA) |
   251|| Steam блокирует автоматизацию | Используйте прокси и headless=False для отладки |
   252|
   253|### Режим отладки
   254|
   255|```python
   256|config = SolverConfig(debug=True)
   257|```
   258|
   259|Включает:
   260|- Подробные логи
   261|- Скриншоты каждого шага
   262|- Логирование сетевых запросов
   263|- Детальные сообщения об ошибках
   264|
   265|### Тесты
   266|
   267|```bash
   268|python3 test_solver.py
   269|```
   270|
   271|Результат: 7/7 тестов проходят ✅
   272|
   273|### Технические детали
   274|
   275|| Компонент | Технология |
   276||-----------|------------|
   277|| Браузер | Playwright (Chromium) |
   278|| STT | Google Speech / Whisper / Vosk |
   279|| Классификация | HuggingFace / Imagga / ResNet50 |
   280|| Fingerprint | JS-инъекции в navigator/WebGL |
   281|| Язык | Python 3.10+ (async/await) |
   282|| Зависимости | playwright, SpeechRecognition, pydub, requests, aiohttp |
   283|
   284|### Ограничения
   285|
   286|- Точность аудио-решения зависит от качества аудио и STT-движка
   287|- Точность распознавания картинок varies по категориям
   288|- Сторонние API платные (2Captcha ~$2-3 за 1000 капч)
   289|- Steam может блокировать автоматизацию
   290|- Действуют лимиты запросов
   291|
   292|### Юридическое
   293|
   294|Инструмент предназначен только для образовательных целей. Использование автоматизации для входа в Steam может нарушать их Условия использования. Используйте на свой страх и риск.
   295|
   296|### Лицензия
   297|
   298|MIT License
   299|
   300|---
   301|
   302|## English
   303|
   304|### Description
   305|
   306|A comprehensive hCaptcha solver with multiple solving strategies, designed specifically for Steam login automation.
   307|
   308|### Features
   309|
   310|🎤 **Audio Challenge Solver** — speech-to-text via Google Speech API, Whisper (local), or Vosk (offline)
   311|
   312|🖼️ **Image Challenge Solver** — image classification via HuggingFace API, Imagga, or local ResNet50
   313|
   314|🌐 **Third-Party APIs** — 2Captcha and AntiCaptcha as reliable fallback (humans solve for you)
   315|
   316|🔐 **Steam Integration** — full login flow with Steam Guard 2FA, session persistence, cookies
   317|
   318|🛡️ **Anti-Detection** — realistic browser fingerprinting, webdriver hiding, human-like behavior
   319|
   320|🌐 **Proxy Support** — HTTP/SOCKS proxies with authentication
   321|
   322|### Installation
   323|
   324|```bash
   325|git clone https://github.com/Asmodei513/hcaptcha-solver.git
   326|cd hcaptcha-solver
   327|pip install -r requirements.txt
   328|playwright install chromium
   329|```
   330|
   331|### Quick Start
   332|
   333|```python
   334|import asyncio
   335|from solver import solve_hcaptcha
   336|
   337|async def main():
   338|    success = await solve_hcaptcha(
   339|        url="https://store.steampowered.com/login/"
   340|    )
   341|    print(f"Captcha solved: {success}")
   342|
   343|asyncio.run(main())
   344|```
   345|
   346|### Steam Login
   347|
   348|```python
   349|import asyncio
   350|from steam_login import steam_login_with_captcha
   351|
   352|async def main():
   353|    result = await steam_login_with_captcha(
   354|        username="your_username",
   355|        password="your_password",
   356|        steam_guard_code="12345",
   357|    )
   358|    print(f"Status: {result.status}")
   359|    print(f"Message: {result.message}")
   360|
   361|asyncio.run(main())
   362|```
   363|
   364|### How It Works
   365|
   366|```
   367|Audio Challenge → Image Challenge → 2Captcha API → AntiCaptcha API
   368|```
   369|
   370|Each method is tried in order. If one fails, it automatically falls back to the next.
   371|
   372|### License
   374|
   375|MIT License
   376|
   377|### Links
   378|
   379|- [Issues](https://github.com/Asmodei513/hcaptcha-solver/issues)
   380|- [Pull Requests](https://github.com/Asmodei513/hcaptcha-solver/pulls)
   381|
   382|---
   383|
   384|<sub>Made with ❤️ by [Asmodei513](https://github.com/Asmodei513)</sub>
   385|
   386|</s>
   387|
   388|</s>
   389|
   390|</s>
   391|
   392|</s>
   393|
   394|</s>
   395|
   396|</s>
   397|
   398|</s>
   399|
   400|</s>
