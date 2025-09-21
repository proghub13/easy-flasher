# Плагины для EASY-FLASHER / EASY-FLASHER Plugin System

Ниже — краткая документация для разработки плагинов к приложению. Док содержит две секции: RU и EN.

---

## RU — Разработка плагинов

### Возможности плагинов
- Регистрация бэкенд‑функций через `PLUGIN_API` и/или `register(eel)`.
- Переопределение базовых операций приложения: `perform_root`, `perform_flash`, `perform_unlock` через ключи `action.perform_root`, `action.perform_flash`, `action.perform_unlock` в `PLUGIN_API`.
- Инъекция фронтенд‑ассетов плагина (JS/CSS/HTML) без правки основного кода.
- Хуки на фронтенде через глобальный API `window.PluginUI`:
  - `addTab(id, title, html)` — добавить вкладку со своим содержимым.
  - `addSidebarItem(label, onClick)` — добавить пункт в сайдбар.
  - `overrideAction(name, handler)` — заменить обработчик действия на фронте.

### Структура файлов
- Все плагины — `.py` файлы в папке `plugins/`.
- Необязательные ассеты фронтенда — в `plugins/<имя_плагина>/web/` (или `plugins/<имя_плагина>_assets/web/`).
  - Все `.css`, `.js`, `.html` из этой папки инжектятся автоматически при старте.

Примеры структур:
```
plugins/
  my_plugin.py
  my_plugin/
    web/
      index.js
      styles.css
      panel.html
```
или
```
plugins/
  my_plugin.py
  my_plugin_assets/
    web/
      ui.js
      ui.css
```

### Минимальный плагин
```python
# plugins/hello.py
PLUGIN = {
    "id": "plugin.hello",
    "name": "Hello World",
    "version": "1.0.0",
    "author": "You",
    "description": "Demo plugin",
}

# Регистрировать нечего? Можно оставить пусто
def register(eel):
    pass

# Экспортируем функции плагина
PLUGIN_API = {
    'say_hello': lambda: {"ok": True, "message": "Hello from plugin!"}
}
```

Вызов с фронтенда:
```javascript
const res = await eel.plugin_call('say_hello')();
```

### Переопределение базовых операций
Чтобы заменить логику приложения, экспортируйте в `PLUGIN_API` функции с именами `action.<название>`:

```python
# plugins/override_root.py
PLUGIN = {"id":"plugin.override-root","name":"Override Root","version":"1.0.0"}

def my_root(image_path=None, method='auto'):
    # Ваша логика; верните dict вида {ok: bool, ...}
    return {"ok": False, "error": "perform_root overridden by plugin"}

PLUGIN_API = {
    'action.perform_root': my_root,
}
```

Фронтенд уже вызывает действия через прокси:
```javascript
await eel.call_action('perform_root', img, method)();
await eel.call_action('perform_flash', partition, path, method)();
await eel.call_action('perform_unlock', method)();
```
Если плагин определил `action.*`, вызов уйдёт в него, иначе выполнится встроенная реализация.

### Инъекция UI
Поместите HTML/CSS/JS в `plugins/<id>/web/` и при старте они загрузятся автоматически.
После инъекции доступен `window.PluginUI`:

```javascript
// plugins/my_plugin/web/index.js
(function(){
  if (!window.PluginUI) return;
  window.PluginUI.addTab('my-tab', 'My Tab', '<div class="neon-details"><div class="details-body">Hello!</div></div>');
  window.PluginUI.addSidebarItem('My Button', () => showTab('my-tab'));

  // Переопределить фронтовый хендлер при желании
  window.PluginUI.overrideAction('perform_root', async (...args) => {
    const res = await eel.plugin_call('custom_front_handler', ...args)();
    console.log('front override result', res);
  });
})();
```

### Бэкенд API, доступные плагинам
- `register(eel)`: вызывается при загрузке модуля. Можно делать `@eel.expose` или подписки.
- `PLUGIN_API`: dict имя→функция. Функции вызываются через `eel.plugin_call(name, ...args)` или автоматически через `eel.call_action(name, ...args)` для `action.*`.
- Встроенные expose‑функции:
  - `reload_plugins()` — перезагрузка всех плагинов.
  - `get_plugins()` — список загруженных плагинов (метаданные).
  - `get_plugin_assets()` — JS/CSS/HTML ассеты.
  - `plugin_call(name, ...args)` — прямой вызов функции из `PLUGIN_API`.
  - `call_action(name, ...args)` — прокси на `action.*` или встроенные действия.

### Требования к функциям
- Возвращайте `dict` со схемой `{ "ok": bool, ... }`. Любой другой тип оборачивается в `{ ok: true, result: … }`.
- Ловите исключения внутри плагина и возвращайте `{ ok: false, error: str(e) }`.

### Рекомендации
- Изолируйте логику, не блокируйте UI. Старайтесь не выполнять длительные операции синхронно.
- Имена функций/действий делайте префиксными: `myplugin.*`.
- Для настроек используйте свой JSON рядом с плагином (центр. конфиг может быть добавлен позднее).

---

## EN — Plugin Development

### What plugins can do
- Register backend functions via `PLUGIN_API` and/or `register(eel)`.
- Override core actions: `perform_root`, `perform_flash`, `perform_unlock` by exporting `action.perform_root|flash|unlock` in `PLUGIN_API`.
- Inject frontend assets (JS/CSS/HTML) without touching core.
- Use `window.PluginUI` on the frontend:
  - `addTab(id, title, html)` — add custom tab.
  - `addSidebarItem(label, onClick)` — add sidebar item.
  - `overrideAction(name, handler)` — override a frontend handler.

### File layout
- Put `.py` in `plugins/`.
- Optional frontend assets in `plugins/<plugin>/web/` (or `plugins/<plugin>_assets/web/`). All `.css/.js/.html` files are auto‑injected at startup.

### Minimal plugin
```python
# plugins/hello.py
PLUGIN = {
    "id": "plugin.hello",
    "name": "Hello World",
    "version": "1.0.0",
    "author": "You",
    "description": "Demo plugin",
}

def register(eel):
    pass

PLUGIN_API = {
    'say_hello': lambda: {"ok": True, "message": "Hello from plugin!"}
}
```
Frontend call:
```javascript
const res = await eel.plugin_call('say_hello')();
```

### Overriding core actions
```python
PLUGIN = {"id":"plugin.override-root","name":"Override Root","version":"1.0.0"}

def my_root(image_path=None, method='auto'):
    return {"ok": False, "error": "perform_root overridden by plugin"}

PLUGIN_API = {
    'action.perform_root': my_root,
}
```
Frontend already uses the proxy:
```javascript
await eel.call_action('perform_root', img, method)();
await eel.call_action('perform_flash', partition, path, method)();
await eel.call_action('perform_unlock', method)();
```
If a plugin exports `action.*`, it will be called; otherwise built‑in action runs.

### UI injection
Place your HTML/CSS/JS into `plugins/<id>/web/`. After injection, use `window.PluginUI`:
```javascript
(function(){
  if (!window.PluginUI) return;
  window.PluginUI.addTab('my-tab', 'My Tab', '<div class=\"neon-details\"><div class=\"details-body\">Hello!</div></div>');
  window.PluginUI.addSidebarItem('My Button', () => showTab('my-tab'));
})();
```

### Backend API available
- `register(eel)` — called on load.
- `PLUGIN_API` — name→callable (called via `eel.plugin_call`).
- Exposed helpers: `reload_plugins()`, `get_plugins()`, `get_plugin_assets()`, `plugin_call(name, ...)`, `call_action(name, ...)`.

### Function contract
- Return `{ ok: boolean, ... }`. Non‑dict return values are wrapped.
- Catch exceptions and return `{ ok: false, error: string }`.

### Tips
- Keep long tasks off the UI thread.
- Use namespacing for function names.
- Store your config near the plugin (a shared config store may arrive later).

---

## FAQ

- Где лежат плагины?
  — В `plugins/`. Создайте `.py` и (опционально) папку `web/` рядом.

- Как обновить список плагинов без перезапуска?
  — В данный момент вызывается автоматически при старте. Можно дернуть `eel.reload_plugins()` из консоли DevTools.

- Как отладить фронтенд плагина?
  — Откройте DevTools (F12), вкладка Console/Network/Sources.
