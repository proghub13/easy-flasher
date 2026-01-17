// web/script.js

function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const toggleBtn = document.getElementById('sidebar-toggle');
    const content = document.querySelector('.content');
    sidebar.classList.toggle('hidden');
    // Move toggle button with sidebar edge
    if (sidebar.classList.contains('hidden')) {
        toggleBtn.style.left = '0px';
        toggleBtn.textContent = '❯';
        content.classList.add('shifted');
    } else {
        toggleBtn.style.left = '200px';
        toggleBtn.textContent = '❮';
        content.classList.remove('shifted');
    }
}

function openThemeModal() {
    const modal = document.getElementById('theme-modal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeThemeModal() {
    const modal = document.getElementById('theme-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

function openErrorModal(message) {
    const modal = document.getElementById('error-modal');
    const box = document.getElementById('error-message');
    box.textContent = message || 'Произошла ошибка';
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeErrorModal() {
    const modal = document.getElementById('error-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

function openInfoModal(message, title) {
    const modal = document.getElementById('info-modal');
    const box = document.getElementById('info-message');
    if (title) {
        modal.querySelector('h2').textContent = String(title);
    } else {
        modal.querySelector('h2').textContent = 'Информация';
    }
    box.textContent = message || '';
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeInfoModal() {
    const modal = document.getElementById('info-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('app_theme', theme);
    if (theme !== 'custom') {
        // clear inline overrides so presets work after custom
        const root = document.documentElement;
        root.style.removeProperty('--neon');
        root.style.removeProperty('--bg');
        root.style.removeProperty('--panel');
        root.style.removeProperty('--sidebar');
        // Очищаем все background-свойства, чтобы не ломать фоновые эффекты
        document.body.style.removeProperty('background-color');
        document.body.style.removeProperty('background-image');
        document.body.style.removeProperty('background-repeat');
        document.body.style.removeProperty('background-position');
        document.body.style.removeProperty('background-size');
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    const saved = localStorage.getItem('app_theme') || 'blue';
    applyTheme(saved);
    
    // Автоматическая проверка обновлений при запуске (только если пользователь не отключил)
    const autoCheckUpdates = localStorage.getItem('auto_check_updates');
    if (autoCheckUpdates !== 'false') {
        setTimeout(async () => {
            try {
                const result = await eel.check_for_updates()();
                if (result.success && result.has_update) {
                    const updateInfo = await eel.get_update_info()();
                    if (updateInfo.success) {
                        currentUpdateInfo = updateInfo;
                        showUpdateModal(updateInfo, result.current_version);
                        // Подчёркиваем кнопку обновления как индикатор
                        const btn = document.getElementById('update-fab');
                        if (btn) btn.classList.add('update-available');
                    }
                }
            } catch (error) {
                // Тихо игнорируем ошибки автоматической проверки
                console.log('Auto-update check failed:', error);
            }
        }, 2000); // Проверяем через 2 секунды после загрузки
    }
    
    document.querySelectorAll('.theme-option').forEach(btn => {
        btn.addEventListener('click', () => {
            applyTheme(btn.getAttribute('data-theme'));
        });
    });
    document.getElementById('theme-modal').addEventListener('click', (e) => {
        if (e.target.id === 'theme-modal') closeThemeModal();
    });
    // Load plugins
    eel.reload_plugins()().then(async () => {
        // Очищаем старые элементы плагинов перед загрузкой новых
        clearAllPluginAssets();
        await refreshPlugins();
        await injectPluginAssets();
    });

    // Настройки кастомной темы теперь добавляются плагином (если есть)
    // Автоопределение устройства для вкладки прошивок
    try {
        const dev = await eel.fw_get_device()();
        if (!dev || !dev.ok || !dev.connected) {
            // Откроем модалку выбора устройства, если вкладка прошивок активна или при первом входе
            // открывать не будем автоматически, пользователь нажмет иконку
        }
    } catch (_) { /* ignore */ }
});

async function startRoot() {
    const img = document.getElementById('root-boot-path').value || null;
    const method = document.getElementById('root-method').value || 'auto';
    const res = await eel.call_action('perform_root', img, method)();
    if (res && res.manual_ident) {
        document.getElementById('manual-ident').style.display = 'block';
        return;
    }
    if (res && res.needs_unlock) {
        const agree = confirm('Загрузчик заблокирован. Запустить разблокировку через Brom?');
        if (agree) {
            alert('Выключите телефон и удерживайте кнопку уменьшения громкости, подключив кабель.');
            const unlockRes = await eel.run_mtk_unlock()();
            handleResult(unlockRes, 'Разблокировка завершена');
            alert('Нажмите кнопку питания для включения устройства, затем дождитесь загрузки.');
            alert('Повторно запустим рут после загрузки. Убедитесь, что включена отладка по USB.');
            const res2 = await eel.call_action('perform_root', img)();
            handleResult(res2, 'Рут завершён');
        }
        return;
    }
    if (res && res.manual_fastboot) {
        const steps = (res.instructions || []).join('\n- ');
        alert('Нужно войти в fastboot вручную:\n- ' + steps);
        const res2 = await eel.call_action('perform_root', img, method)();
        handleResult(res2, 'Рут завершён');
        return;
    }
    // Проверяем результат установки Magisk
    if (res && res.magisk_installed) {
        handleResult(res, 'Рут завершён и Magisk установлен');
    } else if (res && res.magisk_error) {
        handleResult(res, 'Рут завершён, но не удалось установить Magisk');
        console.warn('Ошибка установки Magisk:', res.magisk_error);
    } else {
        handleResult(res, 'Рут завершён');
    }
}

async function installMagiskManually() {
    try {
        const result = await eel.install_magisk()();
        if (result.success) {
            alert('Magisk успешно установлен!');
        } else {
            alert('Ошибка установки Magisk: ' + result.error);
        }
    } catch (error) {
        alert('Ошибка: ' + error);
    }
}

// Функции для работы с обновлениями
let currentUpdateInfo = null;

async function checkForUpdates() {
    try {
        const result = await eel.check_for_updates()();
        if (result.success) {
            if (result.has_update) {
                // Получаем подробную информацию об обновлении
                const updateInfo = await eel.get_update_info()();
                if (updateInfo.success) {
                    currentUpdateInfo = updateInfo;
                    showUpdateModal(updateInfo, result.current_version);
                    const btn = document.getElementById('update-fab');
                    if (btn) btn.classList.add('update-available');
                } else {
                    openErrorModal('Ошибка получения информации об обновлении: ' + updateInfo.error);
                }
            } else {
                openInfoModal('У вас уже установлена последняя версия!', 'Обновления');
                const btn = document.getElementById('update-fab');
                if (btn) btn.classList.remove('update-available');
            }
        } else {
            openErrorModal('Ошибка проверки обновлений: ' + result.error);
        }
    } catch (error) {
        openErrorModal('Ошибка: ' + error);
    }
}

function showUpdateModal(updateInfo, currentVersion) {
    document.getElementById('current-version').textContent = currentVersion;
    document.getElementById('latest-version').textContent = updateInfo.version;
    document.getElementById('update-description').textContent = updateInfo.body || 'Описание недоступно';
    
    // Форматируем дату
    const date = new Date(updateInfo.published_at);
    document.getElementById('update-date').textContent = date.toLocaleDateString('ru-RU');
    
    // Если это тестовый режим, добавляем индикацию
    if (currentVersion === "0.0.0") {
        const modal = document.getElementById('update-modal');
        const title = modal.querySelector('h2');
        title.innerHTML = 'Обновление доступно <span class="text-yellow-400 text-sm">(ТЕСТОВЫЙ РЕЖИМ)</span>';
    }
    
    document.getElementById('update-modal').classList.remove('hidden');
    document.getElementById('update-modal').classList.add('flex');
}

function closeUpdateModal() {
    // Сохраняем настройку авто-проверки
    const disableAutoUpdates = document.getElementById('disable-auto-updates').checked;
    localStorage.setItem('auto_check_updates', disableAutoUpdates ? 'false' : 'true');
    
    // Сбрасываем заголовок
    const modal = document.getElementById('update-modal');
    const title = modal.querySelector('h2');
    title.textContent = 'Обновление доступно';
    
    document.getElementById('update-modal').classList.add('hidden');
    document.getElementById('update-modal').classList.remove('flex');
    currentUpdateInfo = null;
}

async function downloadUpdate() {
    if (!currentUpdateInfo || !currentUpdateInfo.download_url) {
        openErrorModal('Ошибка: нет ссылки для скачивания');
        return;
    }
    
    try {
        const result = await eel.download_update(currentUpdateInfo.download_url)();
        if (result.success) {
            openInfoModal(`Обновление скачано: ${result.message}\n\nФайл сохранен в папку updates/`, 'Обновление скачано');
            closeUpdateModal();
            const btn = document.getElementById('update-fab');
            if (btn) btn.classList.remove('update-available');
        } else {
            openErrorModal('Ошибка скачивания: ' + result.error);
        }
    } catch (error) {
        openErrorModal('Ошибка: ' + error);
    }
}

function openUpdateInBrowser() {
    if (currentUpdateInfo && currentUpdateInfo.html_url) {
        window.open(currentUpdateInfo.html_url, '_blank');
    } else {
        openErrorModal('Ошибка: нет ссылки на релиз');
    }
}

async function saveManualIdent() {
    const m = document.getElementById('manual-manufacturer').value;
    const mod = document.getElementById('manual-model').value;
    if (!m || !mod) {
        alert('Введите производителя и модель');
        return;
    }
    const saved = await eel.set_manual_device_info(m, mod)();
    if (saved && saved.ok) {
        document.getElementById('manual-ident').style.display = 'none';
        await startRoot();
    } else {
        alert('Не удалось сохранить данные.');
    }
}

async function startUnlock() {
    const method = document.getElementById('unlock-method').value || 'auto';
    const res = await eel.call_action('perform_unlock', method)();
    handleResult(res, 'Разблокировка завершена');
}

async function startFlash() {
    const partition = document.getElementById('flash-partition').value;
    const path = document.getElementById('flash-image-path').value;
    const method = document.getElementById('flash-method').value || 'auto';
    const res = await eel.call_action('perform_flash', partition, path, method)();
    handleResult(res, 'Прошивка завершена');
}

function handleResult(res, successMsg) {
    if (!res || !res.ok) {
        openErrorModal('Ошибка: ' + (res && res.error ? res.error : 'Неизвестная'));
    } else {
        // success could use a toast later
        alert(successMsg);
    }
}

async function refreshPlugins() {
    try {
        const plugins = await eel.get_plugins()();
        const nav = document.getElementById('plugins-nav');
        const list = document.getElementById('plugins-list');
        if (!plugins || plugins.length === 0) {
            if (nav) nav.classList.add('hidden');
            if (list) list.innerHTML = '<div class="text-slate-400">Плагины не найдены</div>';
            return;
        }
        if (nav) nav.classList.remove('hidden');
        if (list) {
            list.innerHTML = plugins.map(p => renderPluginCard(p)).join('');
        }
    } catch (e) {
        console.error(e);
    }
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"]~/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','~':'&#126;'}[c]));
}

function renderPluginCard(p) {
    const isEnabled = p.enabled !== false; // по умолчанию включен
    const statusText = isEnabled ? 'Включен' : 'Отключен';
    const statusColor = isEnabled ? 'text-green-400' : 'text-red-400';
    const toggleButton = isEnabled ? 
        `<button class="neon-button text-xs px-2 py-1 bg-orange-600 hover:bg-orange-700" onclick="disablePlugin('${escapeHtml(p.id || '')}')">Отключить</button>` :
        `<button class="neon-button text-xs px-2 py-1 bg-green-600 hover:bg-green-700" onclick="enablePlugin('${escapeHtml(p.id || '')}')">Включить</button>`;
    
    return `
        <div class="neon-details">
            <div class="details-body">
                <div class="flex items-center justify-between mb-2">
                    <div class="flex items-center gap-2">
                        <div class="text-neon-400"><b>${escapeHtml(p.name || 'Без названия')}</b> <span class="text-slate-400">v${escapeHtml(p.version || '0.0.0')}</span></div>
                        <span class="text-xs ${statusColor}">(${statusText})</span>
                    </div>
                    <div class="flex items-center gap-2">
                        <button class="neon-button text-xs px-2 py-1" onclick="openPluginEditor('${escapeHtml(p.id || '')}')">Редактировать</button>
                        ${toggleButton}
                        <button class="neon-button text-xs px-2 py-1 bg-red-600 hover:bg-red-700" onclick="deletePlugin('${escapeHtml(p.id || '')}')">Удалить</button>
                    </div>
                </div>
                <div class="text-slate-300">${escapeHtml(p.description || '')}</div>
                <div class="text-slate-500 text-sm">${escapeHtml(p.author || 'unknown')} · ${escapeHtml(p.file || '')}</div>
            </div>
        </div>`;
}

function applyCustomTheme(pal) {
    const root = document.documentElement;
    root.style.setProperty('--neon', pal.neon || '#22d3ee');
    root.style.setProperty('--bg', pal.bg || '#0f172a');
    // derive panel and sidebar colors from bg to avoid mismatched stripes
    try {
        const bg = pal.bg || '#0f172a';
        const rgbaPanel = 'rgba(' + hexToRgb(bg).join(', ') + ', 0.60)';
        const rgbaSidebar = 'rgba(' + hexToRgb(bg).map((v,i)=> Math.max(0, Math.min(255, i===0? v+15 : v+18))).join(', ') + ', 0.60)';
        root.style.setProperty('--panel', rgbaPanel);
        root.style.setProperty('--sidebar', rgbaSidebar);
    } catch (e) { /* noop */ }
    localStorage.setItem('app_theme', 'custom');
    // Устанавливаем фон через CSS переменную, а не inline стиль, чтобы не ломать фоновые эффекты
    document.body.style.backgroundColor = '';
    document.body.style.backgroundImage = '';
    document.body.style.backgroundRepeat = '';
    document.body.style.backgroundPosition = '';
    document.body.style.backgroundSize = '';
    // Фон будет браться из CSS переменной --bg через style.css
}

function clearAllPluginAssets() {
    // Удаляем все CSS стили плагинов
    document.querySelectorAll('style[data-plugin-css]').forEach(el => el.remove());
    
    // Удаляем все HTML фрагменты плагинов
    document.querySelectorAll('div[data-plugin-html]').forEach(el => el.remove());
    
    // Удаляем все JS скрипты плагинов
    document.querySelectorAll('script[data-plugin-js]').forEach(el => el.remove());
    
    // Удаляем все элементы с data-plugin-* атрибутами
    document.querySelectorAll('[data-plugin-css], [data-plugin-html], [data-plugin-js], [data-plugin-ui]').forEach(el => el.remove());
    
    // Очищаем переопределения действий
    if (window.PluginUI && window.PluginUI._overrides) {
        window.PluginUI._overrides = {};
    }
    
    // Удаляем все элементы, добавленные плагинами через PluginUI
    document.querySelectorAll('[data-plugin-ui]').forEach(el => el.remove());
    
    // Очищаем все кастомные темы и модалки, добавленные плагинами
    document.querySelectorAll('#ct-save-modal, #plugin-editor-modal').forEach(el => el.remove());
    
    // Очищаем все элементы в модальном окне тем, добавленные плагинами
    const themeModal = document.getElementById('theme-modal');
    if (themeModal) {
        themeModal.querySelectorAll('.neon-details').forEach(el => {
            // Удаляем только те, что содержат "Custom Theme" или "Saved Custom Themes"
            const text = el.textContent || '';
            if (text.includes('Custom Theme') || text.includes('Saved Custom Themes')) {
                el.remove();
            }
        });
    }
    
    // Восстанавливаем оригинальные функции, переопределенные плагинами
    if (window.openThemeModal && window.openThemeModal._original) {
        window.openThemeModal = window.openThemeModal._original;
    }
    
    if (window.applyTheme && window.applyTheme._original) {
        window.applyTheme = window.applyTheme._original;
    }
    
    // Очищаем localStorage от данных плагинов
    Object.keys(localStorage).forEach(key => {
        if (key.startsWith('custom_theme_') || key === 'theme_changed_by_user') {
            localStorage.removeItem(key);
        }
    });
    
    // Сбрасываем кастомную тему если она была применена
    const currentTheme = localStorage.getItem('app_theme');
    if (currentTheme === 'custom') {
        // Возвращаемся к последней сохраненной теме или blue по умолчанию
        const savedTheme = localStorage.getItem('app_theme_backup') || 'blue';
        if (window.applyTheme) {
            window.applyTheme(savedTheme);
        }
    }
}

async function injectPluginAssets() {
    try {
        const assets = await eel.get_plugin_assets()();
        // inject CSS first
        Object.values(assets || {}).forEach(group => {
            (group.css || []).forEach(file => {
                try {
                    const style = document.createElement('style');
                    style.setAttribute('data-plugin-css', file.name || '');
                    style.textContent = String(file.content || '');
                    document.head.appendChild(style);
                } catch (e) { console.error(e); }
            });
        });
        // inject HTML fragments
        Object.values(assets || {}).forEach(group => {
            (group.html || []).forEach(file => {
                try {
                    const div = document.createElement('div');
                    div.setAttribute('data-plugin-html', file.name || '');
                    div.innerHTML = String(file.content || '');
                    document.body.appendChild(div);
                } catch (e) { console.error(e); }
            });
        });
        // inject JS last
        for (const group of Object.values(assets || {})) {
            for (const file of (group.js || [])) {
                await new Promise(resolve => {
                    try {
                        const script = document.createElement('script');
                        script.setAttribute('data-plugin-js', file.name || '');
                        script.textContent = String(file.content || '');
                        script.onload = () => resolve();
                        document.body.appendChild(script);
                        // give scripts a tick to run
                        setTimeout(resolve, 0);
                    } catch (e) { console.error(e); resolve(); }
                });
            }
        }
        // Provide a minimal frontend API for plugins to hook UI
        window.PluginUI = window.PluginUI || {
            addSidebarItem(label, onClick) {
                const ul = document.querySelector('.sidebar ul');
                if (!ul) return;
                const li = document.createElement('li');
                li.textContent = String(label);
                li.addEventListener('click', () => {
                    if (typeof onClick === 'function') try { onClick(); } catch(e){ console.error(e); }
                });
                ul.appendChild(li);
            },
            addTab(id, title, html) {
                const content = document.querySelector('.content');
                const tabs = document.querySelectorAll('.tab-content');
                if (!content) return;
                const li = document.createElement('li');
                li.textContent = String(title);
                li.addEventListener('click', () => showTab(id));
                document.querySelector('.sidebar ul')?.appendChild(li);
                const div = document.createElement('div');
                div.id = id;
                div.className = 'tab-content';
                div.innerHTML = html || '';
                content.appendChild(div);
            },
            overrideAction(name, handler) {
                // inform backend to route action.* via plugin_call if desired
                // on frontend, replace callers to use call_action
                window.PluginUI._overrides = window.PluginUI._overrides || {};
                window.PluginUI._overrides[name] = handler;
            }
        };
    } catch (e) {
        console.error(e);
    }
}

function hexToRgb(hex) {
    const m = String(hex||'').trim().replace('#','');
    const n = parseInt(m.length===3 ? m.split('').map(x=>x+x).join('') : m, 16);
    return [n>>16 & 255, n>>8 & 255, n & 255];
}

// -------------------- Plugin Management Functions --------------------

async function disablePlugin(pluginId) {
    try {
        const result = await eel.disable_plugin(pluginId)();
        if (result.ok) {
            // Очищаем все элементы плагинов, обновляем список и перезагружаем только включенные плагины
            clearAllPluginAssets();
            await refreshPlugins();
            await injectPluginAssets();
        } else {
            openErrorModal('Ошибка отключения плагина: ' + (result.error || 'unknown'));
        }
    } catch (e) {
        openErrorModal('Ошибка отключения плагина: ' + e.message);
    }
}

async function enablePlugin(pluginId) {
    try {
        const result = await eel.enable_plugin(pluginId)();
        if (result.ok) {
            // Очищаем все элементы плагинов и перезагружаем
            clearAllPluginAssets();
            await refreshPlugins();
            await injectPluginAssets();
        } else {
            openErrorModal('Ошибка включения плагина: ' + (result.error || 'unknown'));
        }
    } catch (e) {
        openErrorModal('Ошибка включения плагина: ' + e.message);
    }
}

async function deletePlugin(pluginId) {
    if (!confirm(`Вы уверены, что хотите удалить плагин "${pluginId}"? Это действие нельзя отменить.`)) {
        return;
    }
    
    try {
        const result = await eel.delete_plugin(pluginId)();
        if (result.ok) {
            // Очищаем все элементы плагинов перед перезагрузкой
            clearAllPluginAssets();
            await refreshPlugins();
            await injectPluginAssets();
        } else {
            openErrorModal('Ошибка удаления плагина: ' + (result.error || 'unknown'));
        }
    } catch (e) {
        openErrorModal('Ошибка удаления плагина: ' + e.message);
    }
}

let currentEditingPlugin = null;
let currentEditingFile = null;

async function openPluginEditor(pluginId) {
    currentEditingPlugin = pluginId;
    
    // Создаем модальное окно редактора
    let modal = document.getElementById('plugin-editor-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'plugin-editor-modal';
        modal.className = 'fixed inset-0 bg-black/60 hidden items-center justify-center z-50';
        modal.innerHTML = `
            <div class="w-[90vw] h-[90vh] max-w-7xl rounded-xl modal-panel flex flex-col">
                <div class="flex items-center justify-between p-4 border-b border-slate-700">
                    <h2 class="page-title text-xl">Редактор плагина: <span id="editor-plugin-name">${pluginId}</span></h2>
                    <button onclick="closePluginEditor()" class="neon-button">Закрыть</button>
                </div>
                <div class="flex flex-1 overflow-hidden">
                    <div class="w-64 border-r border-slate-700 bg-slate-800/50 overflow-y-auto">
                        <div class="p-3">
                            <h3 class="text-neon-400 font-semibold mb-2">Файлы плагина</h3>
                            <div id="plugin-files-list" class="space-y-1"></div>
                        </div>
                    </div>
                    <div class="flex-1 flex flex-col">
                        <div class="flex items-center justify-between p-3 border-b border-slate-700">
                            <span id="editor-file-name" class="text-slate-300">Выберите файл</span>
                            <div class="flex gap-2">
                                <button onclick="saveCurrentFile()" class="neon-button text-sm px-3 py-1">Сохранить</button>
                                <button onclick="reloadCurrentFile()" class="neon-button text-sm px-3 py-1">Перезагрузить</button>
                            </div>
                        </div>
                        <div class="flex-1 p-3">
                            <textarea id="plugin-editor-textarea" 
                                class="w-full h-full bg-slate-900 text-slate-100 font-mono text-sm p-3 rounded border border-slate-600 resize-none focus:outline-none focus:border-neon-400"
                                placeholder="Выберите файл для редактирования..."></textarea>
                        </div>
                    </div>
                </div>
            </div>`;
        document.body.appendChild(modal);
    }
    
    // Загружаем файлы плагина
    await loadPluginFiles(pluginId);
    
    // Показываем модалку
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closePluginEditor() {
    const modal = document.getElementById('plugin-editor-modal');
    if (modal) {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
    }
    currentEditingPlugin = null;
    currentEditingFile = null;
}

async function loadPluginFiles(pluginId) {
    try {
        const result = await eel.get_plugin_files(pluginId)();
        if (!result.ok) {
            openErrorModal('Ошибка загрузки файлов: ' + (result.error || 'unknown'));
            return;
        }
        
        const filesList = document.getElementById('plugin-files-list');
        filesList.innerHTML = result.files.map(file => `
            <button class="w-full text-left p-2 rounded hover:bg-slate-700 text-slate-300 text-sm file-item" 
                    data-path="${file.path}" data-type="${file.type}">
                <div class="flex items-center gap-2">
                    <span class="text-xs">${getFileIcon(file.type)}</span>
                    <span>${file.name}</span>
                </div>
            </button>
        `).join('');
        
        // Добавляем обработчики кликов
        filesList.querySelectorAll('.file-item').forEach(btn => {
            btn.addEventListener('click', () => loadFileForEditing(btn.dataset.path, btn.dataset.type));
        });
        
    } catch (e) {
        openErrorModal('Ошибка загрузки файлов: ' + e.message);
    }
}

function getFileIcon(type) {
    switch (type) {
        case 'main': return '🐍';
        case 'web': return '🌐';
        default: return '📄';
    }
}

async function loadFileForEditing(filePath, fileType) {
    currentEditingFile = filePath;
    
    try {
        const result = await eel.read_plugin_file(filePath)();
        if (!result.ok) {
            openErrorModal('Ошибка чтения файла: ' + (result.error || 'unknown'));
            return;
        }
        
        const textarea = document.getElementById('plugin-editor-textarea');
        const fileName = document.getElementById('editor-file-name');
        
        textarea.value = result.content;
        fileName.textContent = filePath.split('/').pop();
        
        // Подсвечиваем активный файл
        document.querySelectorAll('.file-item').forEach(btn => {
            btn.classList.remove('bg-slate-700', 'text-neon-400');
            if (btn.dataset.path === filePath) {
                btn.classList.add('bg-slate-700', 'text-neon-400');
            }
        });
        
    } catch (e) {
        openErrorModal('Ошибка чтения файла: ' + e.message);
    }
}

async function saveCurrentFile() {
    if (!currentEditingFile) {
        openErrorModal('Файл не выбран');
        return;
    }
    
    const textarea = document.getElementById('plugin-editor-textarea');
    const content = textarea.value;
    
    try {
        const result = await eel.write_plugin_file(currentEditingFile, content)();
        if (!result.ok) {
            openErrorModal('Ошибка сохранения файла: ' + (result.error || 'unknown'));
            return;
        }
        
        // Показываем уведомление об успешном сохранении
        const notification = document.createElement('div');
        notification.className = 'fixed top-4 right-4 bg-green-600 text-white px-4 py-2 rounded z-50';
        notification.textContent = 'Файл сохранен';
        document.body.appendChild(notification);
        setTimeout(() => notification.remove(), 2000);
        
    } catch (e) {
        openErrorModal('Ошибка сохранения файла: ' + e.message);
    }
}

async function reloadCurrentFile() {
    if (!currentEditingFile) {
        openErrorModal('Файл не выбран');
        return;
    }
    
    await loadFileForEditing(currentEditingFile, '');
}

// -------------------- Backup Management Functions --------------------

let currentEditingBackup = null;

function showTab(tabId) {
    const tabs = document.querySelectorAll('.tab-content');
    tabs.forEach(tab => {
        tab.classList.remove('active');
    });
    document.getElementById(tabId).classList.add('active');

    // Специальная логика для вкладки бэкапов
    if (tabId === 'backups') {
        loadBackupsList();
    }
    if (tabId === 'firmware') {
        fwInitOnce();
        fwRefresh();
    }
}

async function openCustomBackupModal() {
    const modal = document.getElementById('custom-backup-modal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    await loadPartitionsIntoSelect();
}

function closeCustomBackupModal() {
    const modal = document.getElementById('custom-backup-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

async function loadPartitionsIntoSelect() {
    const select = document.getElementById('backup-partition-select');
    select.innerHTML = ''; // Очищаем старые опции
    try {
        const result = await eel.get_partitions()();
        if (result.ok && result.partitions && result.partitions.length > 0) {
            result.partitions.forEach(p => {
                const option = document.createElement('option');
                option.value = p;
                option.textContent = p;
                select.appendChild(option);
            });
        } else {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = result.error || 'Не удалось получить разделы';
            option.disabled = true;
            select.appendChild(option);
            openErrorModal(result.error || 'Не удалось получить список разделов устройства.');
        }
    } catch (e) {
        openErrorModal('Ошибка при загрузке разделов: ' + e.message);
    }
}

async function loadBackupsList() {
    const listDiv = document.getElementById('backups-list');
    listDiv.innerHTML = '<div class="text-slate-400">Загрузка...</div>';
    try {
        const result = await eel.get_backup_files()();
        if (result.ok && result.files && result.files.length > 0) {
            listDiv.innerHTML = result.files.map(file => renderBackupCard(file)).join('');
        } else if (result.ok) {
            listDiv.innerHTML = '<div class="text-slate-400">Резервных копий пока нет.</div>';
        } else {
            listDiv.innerHTML = '<div class="text-red-400">Ошибка загрузки бэкапов: ' + (result.error || 'Неизвестная ошибка') + '</div>';
            openErrorModal(result.error || 'Ошибка загрузки списка резервных копий.');
        }
    } catch (e) {
        listDiv.innerHTML = '<div class="text-red-400">Ошибка: ' + e.message + '</div>';
        openErrorModal('Ошибка загрузки списка резервных копий: ' + e.message);
    }
}

function renderBackupCard(file) {
    const date = new Date(file.last_modified * 1000).toLocaleString();
    const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
    const partitionName = extractPartitionFromFilename(file.name);
    
    return `
        <div class="neon-details">
            <div class="details-body flex items-center justify-between">
                <div>
                    <div class="text-neon-400"><b>${escapeHtml(file.name)}</b></div>
                    <div class="text-slate-400 text-sm">${sizeMB} MB | ${date}</div>
                    <div class="text-slate-500 text-xs">${escapeHtml(file.path)}</div>
                    <div class="text-slate-500 text-xs">Раздел: ${partitionName}</div>
                </div>
                <div class="flex items-center gap-2">
                    <button class="neon-button text-xs px-2 py-1 bg-blue-600 hover:bg-blue-700" onclick="restoreBackup('${escapeHtml(file.path)}', '${partitionName}')">Восстановить</button>
                    <button class="neon-button text-xs px-2 py-1" onclick="editBackup('${escapeHtml(file.path)}', '${escapeHtml(file.name)}', ${file.size}, ${file.last_modified})">Изменить</button>
                    <button class="neon-button text-xs px-2 py-1 bg-red-600 hover:bg-red-700" onclick="deleteBackup('${escapeHtml(file.path)}')">Удалить</button>
                </div>
            </div>
        </div>`;
}

function extractPartitionFromFilename(filename) {
    // Пытаемся извлечь название раздела из имени файла
    // Формат: partition_manufacturer_model_timestamp.img или name_partition_timestamp.img
    const parts = filename.split('_');
    if (parts.length >= 2) {
        // Проверяем, является ли первый элемент известным разделом
        const knownPartitions = ['boot', 'recovery', 'system', 'userdata', 'cache', 'vendor'];
        if (knownPartitions.includes(parts[0])) {
            return parts[0];
        }
        // Или второй элемент
        if (parts.length >= 3 && knownPartitions.includes(parts[1])) {
            return parts[1];
        }
    }
    return 'неизвестно';
}

async function startCustomBackup() {
    const partition = document.getElementById('backup-partition-select').value;
    const backupName = document.getElementById('backup-name').value;
    const method = document.getElementById('backup-method-select').value || 'auto';

    if (!partition) {
        openErrorModal('Выберите раздел для бэкапа.');
        return;
    }
    if (!backupName.trim()) {
        openErrorModal('Введите название бэкапа.');
        return;
    }

    closeCustomBackupModal();
    try {
        const result = await eel.create_custom_backup(partition, backupName.trim(), method)();
        handleResult(result, `Бэкап раздела ${partition} завершен.`);
        if (result.ok) {
            loadBackupsList(); // Обновляем список после успешного бэкапа
        }
    } catch (e) {
        openErrorModal('Ошибка при создании бэкапа: ' + e.message);
    }
}

async function restoreBackup(filePath, partitionName) {
    if (!confirm(`Вы уверены, что хотите восстановить раздел "${partitionName}" из файла "${filePath.split('/').pop()}"?`)) {
        return;
    }
    try {
        const result = await eel.perform_restore_partition(partitionName, filePath, 'auto')(); // Метод auto по умолчанию
        handleResult(result, `Восстановление раздела ${partitionName} завершено.`);
    } catch (e) {
        openErrorModal('Ошибка при восстановлении бэкапа: ' + e.message);
    }
}

async function deleteBackup(filePath) {
    if (!confirm(`Вы уверены, что хотите удалить файл бэкапа "${filePath.split('/').pop()}"? Это действие нельзя отменить.`)) {
        return;
    }
    try {
        const result = await eel.delete_file(filePath)();
        if (result.ok) {
            alert('Файл бэкапа успешно удален.');
            loadBackupsList(); // Обновляем список после удаления
        } else {
            openErrorModal('Ошибка удаления файла: ' + (result.error || 'unknown'));
        }
    } catch (e) {
        openErrorModal('Ошибка удаления файла: ' + e.message);
    }
}

function editBackup(filePath, fileName, fileSize, lastModified) {
    currentEditingBackup = {
        path: filePath,
        name: fileName,
        size: fileSize,
        lastModified: lastModified
    };
    
    const modal = document.getElementById('backup-edit-modal');
    const date = new Date(lastModified * 1000).toLocaleString();
    const sizeMB = (fileSize / (1024 * 1024)).toFixed(2);
    
    document.getElementById('edit-backup-filename').textContent = fileName;
    document.getElementById('edit-backup-size').textContent = sizeMB + ' MB';
    document.getElementById('edit-backup-date').textContent = date;
    document.getElementById('edit-backup-path').textContent = filePath;
    
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeBackupEditModal() {
    const modal = document.getElementById('backup-edit-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    currentEditingBackup = null;
}

async function restoreBackupFromEdit() {
    if (!currentEditingBackup) return;
    const partitionName = extractPartitionFromFilename(currentEditingBackup.name);
    closeBackupEditModal();
    await restoreBackup(currentEditingBackup.path, partitionName);
}

async function deleteBackupFromEdit() {
    if (!currentEditingBackup) return;
    closeBackupEditModal();
    await deleteBackup(currentEditingBackup.path);
}

async function checkFastbootStatus() {
    try {
        const result = await eel.check_fastboot_devices()();
        if (result.ok) {
            let message = "=== СТАТУС УСТРОЙСТВ ===\n\n";
            
            message += "ADB устройства:\n";
            if (result.has_adb) {
                message += "✅ Найдены ADB устройства\n";
                message += `Вывод: ${result.adb_output}\n`;
            } else {
                message += "❌ ADB устройства не найдены\n";
                if (result.adb_error) {
                    message += `Ошибка: ${result.adb_error}\n`;
                }
            }
            
            message += "\nFastboot устройства:\n";
            if (result.has_fastboot) {
                message += "✅ Найдены Fastboot устройства\n";
                message += `Вывод: ${result.fastboot_output}\n`;
                if (result.devices && result.devices.length > 0) {
                    message += "Детали:\n";
                    result.devices.forEach(device => {
                        message += `- ${device.id}: ${device.status} ${device.is_fastboot ? '(Fastboot)' : ''}\n`;
                    });
                }
            } else {
                message += "❌ Fastboot устройства не найдены\n";
                message += `Вывод: ${result.fastboot_output}\n`;
                if (result.fastboot_error) {
                    message += `Ошибка: ${result.fastboot_error}\n`;
                }
            }
            
            message += "\n=== РЕКОМЕНДАЦИИ ===\n";
            if (!result.has_adb && !result.has_fastboot) {
                message += "• Подключите устройство USB кабелем\n";
                message += "• Включите отладку по USB в настройках разработчика\n";
                message += "• Установите драйверы ADB/Fastboot\n";
            } else if (result.has_adb && !result.has_fastboot) {
                message += "• Нажмите 'Перезагрузить в Fastboot' для перехода в fastboot режим\n";
                message += "• Или вручную: выключите устройство, зажмите Vol- + Power, подключите USB\n";
            } else if (result.has_fastboot) {
                message += "• Fastboot готов к работе! Можете создавать бэкапы\n";
            }
            
            alert(message);
        } else {
            openErrorModal('Ошибка проверки статуса: ' + (result.error || 'Неизвестная ошибка'));
        }
    } catch (e) {
        openErrorModal('Ошибка проверки статуса: ' + e.message);
    }
}

async function rebootToFastboot() {
    if (!confirm('Перезагрузить устройство в fastboot режим? Убедитесь, что устройство подключено и отладка по USB включена.')) {
        return;
    }
    
    try {
        const result = await eel.reboot_to_fastboot()();
        if (result.ok) {
            alert(result.message + '\n\nПосле перезагрузки нажмите "Проверить Fastboot" для проверки статуса.');
        } else {
            openErrorModal('Ошибка перезагрузки: ' + (result.error || 'Неизвестная ошибка'));
        }
    } catch (e) {
        openErrorModal('Ошибка перезагрузки: ' + e.message);
    }
}

// -------------------- Firmware Browser Logic --------------------
let fwInitialized = false;
let fwShowOnlyFavorites = false;
let fwSelectedMan = '';
let fwSelectedMod = '';
let fwCurrentItems = [];
let fwCurrentCategory = 'recovery';
let fwDownloadTarget = null;
let fwDownloadProgressActive = false;
let fwDownloadProgressName = '';
let fwDownloadProgressTotal = 0;
let fwDownloadProgressTimer = null;


async function fwEnsureDeviceSelection() {
    let man = fwSelectedMan || '';
    let mod = fwSelectedMod || '';
    if (!man && !mod) {
        try {
            const dev = await eel.fw_get_device()();
            if (dev && dev.ok && dev.connected) {
                man = dev.manufacturer;
                mod = dev.model;
                fwSelectedMan = man;
                fwSelectedMod = mod;
            } else {
                openFwDeviceModal();
                return null;
            }
        } catch(_) {
            openFwDeviceModal();
            return null;
        }
    }
    return { man, mod };
}

function fwInitOnce() {
    if (fwInitialized) return;
    fwInitialized = true;
    const deviceInput = document.getElementById('fwm-input');
    const suggList = document.getElementById('fwm-suggestions');
    const cat = document.getElementById('fw-category');
    if (cat) {
        cat.addEventListener('change', () => {
            fwRefresh();
        });
    }
    if (deviceInput && suggList) {
        let lastQuery = '';
        deviceInput.addEventListener('input', async () => {
            const q = deviceInput.value.trim();
            lastQuery = q;
            if (q.length < 2) {
                suggList.classList.add('hidden');
                suggList.innerHTML = '';
                return;
            }
            try {
                const res = await eel.fw_find_device(q)();
                if (!res || !res.ok || lastQuery !== q) return;
                const items = res.items || [];
                if (items.length === 0) {
                    suggList.classList.add('hidden');
                    suggList.innerHTML = '';
                    return;
                }
                suggList.innerHTML = items.map(it => `<div class=\"suggestion-item\" data-man=\"${escapeHtml(it.manufacturer)}\" data-mod=\"${escapeHtml(it.model)}\">${escapeHtml(it.manufacturer)} ${escapeHtml(it.model)}</div>`).join('');
                suggList.classList.remove('hidden');
                suggList.querySelectorAll('.suggestion-item').forEach(el => {
                    el.addEventListener('click', () => {
                        const man = el.getAttribute('data-man') || '';
                        const mod = el.getAttribute('data-mod') || '';
                        deviceInput.value = `${man} ${mod}`.trim();
                        fwSelectedMan = man;
                        fwSelectedMod = mod;
                        suggList.classList.add('hidden');
                    });
                });
            } catch (e) { /* ignore */ }
        });
        document.addEventListener('click', (e) => {
            const modal = document.getElementById('fw-device-modal');
            if (modal && !modal.contains(e.target) && e.target !== deviceInput) {
                suggList.classList.add('hidden');
            }
        });
    }
}

async function fwRefresh() {
    const listDiv = document.getElementById('fw-list');
    const cat = document.getElementById('fw-category')?.value || 'recovery';
    listDiv.innerHTML = '<div class="text-slate-400">Загрузка...</div>';
    let man = fwSelectedMan || '';
    let mod = fwSelectedMod || '';
    if (!man && !mod) {
        try {
            const dev = await eel.fw_get_device()();
            if (dev && dev.ok && dev.connected) {
                man = dev.manufacturer;
                mod = dev.model;
            } else {
                openFwDeviceModal();
            }
        } catch(_) { openFwDeviceModal(); }
    }
    try {
        const favRes = await eel.fw_get_favorites()();
        const favNames = (favRes && favRes.ok ? (favRes.names || []) : []);

        let items = [];
        if (fwShowOnlyFavorites) {
            // В режиме избранного показываем оба раздела, без фильтра по устройству
            const [rec, sys] = await Promise.all([
                eel.fw_list('recovery', null, null)(),
                eel.fw_list('system', null, null)()
            ]);
            const all = [
                ...((rec && rec.ok && rec.items) ? rec.items.map(it => ({ ...it, _category: 'recovery' })) : []),
                ...((sys && sys.ok && sys.items) ? sys.items.map(it => ({ ...it, _category: 'system' })) : [])
            ];
            items = all.filter(it => favNames.includes(String(it.name || '')));
        } else {
            const res = await eel.fw_list(cat, man || null, mod || null)();
            if (!res || !res.ok) {
                listDiv.innerHTML = '<div class="text-red-400">Не удалось загрузить прошивки</div>';
                return;
            }
            items = (res.items || []).map(it => ({ ...it, _category: cat }));
        }

        // Сортируем: совместимые выше несовместимых
        items.sort((a, b) => {
            const ca = isCompatible(a, man, mod) ? 1 : 0;
            const cb = isCompatible(b, man, mod) ? 1 : 0;
            return cb - ca;
        });

        fwCurrentItems = items;
        fwCurrentCategory = cat;

        const rendered = items
            .map((it, idx) => renderFirmwareCard(it, man, mod, favNames, idx))
            .join('');
        listDiv.innerHTML = rendered || '<div class="text-slate-400">Ничего не найдено</div>';
    } catch (e) {
        listDiv.innerHTML = '<div class="text-red-400">Ошибка: ' + e.message + '</div>';
    }
}

function renderFirmwareCard(it, man, mod, favNames, index) {
    const name = String(it.name || '');
    const isFav = favNames.includes(name) || !!it.favorite;
    const starClass = isFav ? 'fw-star fav' : 'fw-star';
    const comp = isCompatible(it, man, mod);
    const rowClass = comp ? '' : 'fw-incompatible';
    const subtitle = `${(it.vendors||[]).join(', ')} · ${(it.models||[]).join(', ')}`;
    return `
        <div class="neon-details ${rowClass}">
            <div class="details-body fw-card">
                <div class="fw-left">
                    <input type="checkbox" class="fw-select" data-name="${escapeHtml(name)}" ${comp? '' : ''} />
                    <div>
                        <div class="text-neon-400 font-semibold">${escapeHtml(name)}</div>
                        <div class="text-slate-400 text-xs">${escapeHtml(subtitle)}</div>
                    </div>
                </div>
                <div class="flex items-center gap-3">
                    <button class="icon-btn" title="Скачать" onclick="openFwDownloadModal(${index})">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M12 3v12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M6 11l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M5 19h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                        </svg>
                    </button>
                    <div class="${starClass}" title="Добавить в избранное" onclick="fwToggleFavorite('${escapeHtml(name)}')">${isFav ? '★' : '☆'}</div>
                </div>
            </div>
        </div>`;
}

function isCompatible(it, man, mod) {
    try {
        if (!man && !mod) return true;
        const vendors = (it.vendors || []).map(v => String(v).toLowerCase());
        const models = (it.models || []).map(m => String(m).toLowerCase());
        const okVendor = vendors.length === 0 || vendors.includes(String(man).toLowerCase());
        const lmod = String(mod || '').toLowerCase();
        const okModel = models.length === 0 || models.some(m => lmod.includes(m));
        return okVendor && okModel;
    } catch(_) { return true; }
}

async function fwToggleFavorite(name) {
    try {
        const res = await eel.fw_toggle_favorite(name)();
        if (res && res.ok) {
            fwRefresh();
        } else {
            openErrorModal('Не удалось изменить избранное');
        }
    } catch (e) {
        openErrorModal('Ошибка: ' + e.message);
    }
}

function fwShowFavorites() {
    fwShowOnlyFavorites = !fwShowOnlyFavorites;
    fwRefresh();
}

function ensureFwDownloadProgress(name) {
    const resolved = name || fwDownloadProgressName || (fwDownloadTarget?.name || '');
    if (!resolved) {
        return '';
    }
    if (!fwDownloadProgressActive || fwDownloadProgressName !== resolved) {
        openFwDownloadProgress(resolved);
    }
    startFwDownloadPolling(resolved);
    return resolved;
}

function openFwDownloadProgress(name) {
    const modal = document.getElementById('fw-download-progress-modal');
    if (!modal) return;
    fwDownloadProgressActive = true;
    fwDownloadProgressName = name || '';
    fwDownloadProgressTotal = 0;
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    const nameEl = document.getElementById('fw-download-progress-name');
    if (nameEl) nameEl.textContent = fwDownloadProgressName;
    updateFwDownloadProgressBar(0, 0);
    setFwDownloadStatus('Подготовка к скачиванию...');
    startFwDownloadPolling(fwDownloadProgressName);
}

function closeFwDownloadProgress() {
    const modal = document.getElementById('fw-download-progress-modal');
    if (!modal) return;
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    fwDownloadProgressActive = false;
    fwDownloadProgressName = '';
    fwDownloadProgressTotal = 0;
    stopFwDownloadPolling();
}

function updateFwDownloadProgressBar(downloaded, total) {
    const bar = document.getElementById('fw-download-progress-bar');
    const percentEl = document.getElementById('fw-download-progress-percent');
    let percent = 0;
    if (total && total > 0) {
        percent = Math.min(100, Math.floor((downloaded / total) * 100));
    } else if (downloaded && downloaded > 0) {
        percent = 100;
    }
    if (bar) {
        bar.style.width = `${percent}%`;
    }
    if (percentEl) {
        if (total && total > 0) {
            percentEl.textContent = `${percent}%`;
        } else if (downloaded && downloaded > 0) {
            percentEl.textContent = '...';
        } else {
            percentEl.textContent = '0%';
        }
    }
    fwDownloadProgressTotal = total || 0;
}

function setFwDownloadStatus(text) {
    const statusEl = document.getElementById('fw-download-progress-status');
    if (statusEl) statusEl.textContent = text || '';
}

function formatBytes(bytes) {
    const value = Number(bytes || 0);
    if (!value || value <= 0) return '0 Б';
    const units = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ'];
    let idx = 0;
    let num = value;
    while (num >= 1024 && idx < units.length - 1) {
        num /= 1024;
        idx += 1;
    }
    const precision = idx === 0 ? 0 : (num >= 100 ? 0 : 1);
    return `${num.toFixed(precision)} ${units[idx]}`;
}

eel.expose(start_fw_download);
function start_fw_download(name, total) {
    const resolved = ensureFwDownloadProgress(name);
    const totalNum = Number(total || 0);
    if (totalNum > 0) {
        updateFwDownloadProgressBar(0, totalNum);
    } else {
        updateFwDownloadProgressBar(0, 0);
    }
    setFwDownloadStatus('Подготовка к скачиванию...');
}

eel.expose(report_fw_download_progress);
function report_fw_download_progress(name, downloaded, total) {
    const resolved = ensureFwDownloadProgress(name);
    const downloadedNum = Number(downloaded || 0);
    const totalNum = Number(total || 0);
    updateFwDownloadProgressBar(downloadedNum, totalNum);
    if (totalNum > 0) {
        setFwDownloadStatus(`Скачано ${formatBytes(downloadedNum)} из ${formatBytes(totalNum)}`);
    } else {
        setFwDownloadStatus(`Скачано ${formatBytes(downloadedNum)}`);
    }
}

eel.expose(finish_fw_download);
function finish_fw_download(name, path, total) {
    const resolved = ensureFwDownloadProgress(name);
    const totalNum = Number(total || fwDownloadProgressTotal || 0);
    const downloadedNum = totalNum > 0 ? totalNum : (fwDownloadProgressTotal || 1);
    updateFwDownloadProgressBar(downloadedNum, totalNum || downloadedNum);
    setFwDownloadStatus('Скачивание завершено');
}

eel.expose(fail_fw_download);
function fail_fw_download(name, error) {
    const resolved = ensureFwDownloadProgress(name);
    setFwDownloadStatus(`Ошибка: ${error || 'Неизвестная ошибка'}`);
}

function startFwDownloadPolling(name) {
    if (!name) {
        return;
    }
    stopFwDownloadPolling();
    fwDownloadProgressTimer = setInterval(() => {
        eel.fw_get_download_progress(name)()
            .then((res) => {
                if (!res || !res.ok) {
                    return;
                }
                const downloaded = Number(res.downloaded || 0);
                const total = Number(res.total || 0);
                updateFwDownloadProgressBar(downloaded, total);
                const status = String(res.status || '').toLowerCase();
                if (status === 'starting') {
                    setFwDownloadStatus('Подготовка к скачиванию...');
                } else if (status === 'downloading') {
                    if (total > 0) {
                        setFwDownloadStatus(`Скачано ${formatBytes(downloaded)} из ${formatBytes(total)}`);
                    } else {
                        setFwDownloadStatus(`Скачано ${formatBytes(downloaded)}`);
                    }
                } else if (status === 'finished') {
                    setFwDownloadStatus('Скачивание завершено');
                    stopFwDownloadPolling();
                } else if (status === 'error') {
                    setFwDownloadStatus(`Ошибка: ${res.error || 'Неизвестная ошибка'}`);
                    stopFwDownloadPolling();
                }
            })
            .catch(() => {});
    }, 500);
}

function stopFwDownloadPolling() {
    if (fwDownloadProgressTimer) {
        clearInterval(fwDownloadProgressTimer);
        fwDownloadProgressTimer = null;
    }
}

function openFwDownloadModal(index) {
    const modal = document.getElementById('fw-download-modal');
    if (!modal) return;
    const item = fwCurrentItems[index];
    if (!item) {
        openErrorModal('Прошивка не найдена. Обновите список.');
        return;
    }
    fwDownloadTarget = item;
    const nameEl = document.getElementById('fw-download-name');
    const partEl = document.getElementById('fw-download-partition');
    const sourceEl = document.getElementById('fw-download-source');
    if (nameEl) nameEl.textContent = String(item.name || '');
    if (partEl) partEl.textContent = String(item.partition || '—');
    if (sourceEl) sourceEl.textContent = String(item.url || '');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeFwDownloadModal() {
    const modal = document.getElementById('fw-download-modal');
    if (!modal) return;
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    fwDownloadTarget = null;
}

async function fwDownloadOnly() {
    if (!fwDownloadTarget) return;
    const target = fwDownloadTarget;
    const targetName = String(target.name || '');
    const device = await fwEnsureDeviceSelection();
    if (!device) return;
    const { man, mod } = device;
    const category = target._category || fwCurrentCategory || (document.getElementById('fw-category')?.value || 'recovery');
    closeFwDownloadModal();
    openFwDownloadProgress(targetName);
    let res = null;
    let err = null;
    try {
        res = await eel.fw_download(category, targetName, man || null, mod || null)();
    } catch (e) {
        err = e;
    } finally {
        closeFwDownloadProgress();
        try { await eel.fw_clear_download_progress(targetName)(); } catch (_) {}
        fwDownloadTarget = null;
    }
    if (err) {
        openErrorModal('Ошибка скачивания: ' + err.message);
        return;
    }
    if (res && res.ok) {
        openInfoModal(`Файл скачан: ${res.path}`);
    } else {
        openErrorModal('Ошибка скачивания: ' + (res ? (res.error || 'Неизвестная ошибка') : 'Неизвестная ошибка'));
    }
}

async function fwDownloadAndInstall() {
    if (!fwDownloadTarget) return;
    const target = fwDownloadTarget;
    const targetName = String(target.name || '');
    const device = await fwEnsureDeviceSelection();
    if (!device) return;
    const { man, mod } = device;
    const category = target._category || fwCurrentCategory || (document.getElementById('fw-category')?.value || 'recovery');
    closeFwDownloadModal();
    openFwDownloadProgress(targetName);
    setFwDownloadStatus('Скачивание прошивки...');

    let downloadRes = null;
    let downloadErr = null;
    try {
        downloadRes = await eel.fw_download(category, targetName, man || null, mod || null)();
    } catch (e) {
        downloadErr = e;
    } finally {
        closeFwDownloadProgress();
        try { await eel.fw_clear_download_progress(targetName)(); } catch (_) {}
    }

    if (downloadErr) {
        fwDownloadTarget = null;
        openErrorModal('Ошибка скачивания: ' + downloadErr.message);
        return;
    }
    if (!downloadRes || !downloadRes.ok) {
        fwDownloadTarget = null;
        openErrorModal('Ошибка скачивания: ' + (downloadRes ? (downloadRes.error || 'Неизвестная ошибка') : 'Неизвестная ошибка'));
        return;
    }

    const pre = {};
    if (downloadRes.path) {
        pre[targetName] = downloadRes.path;
    }

    try {
        let installRes = await eel.fw_install(category, [targetName], man || null, mod || null, 'auto', false, pre)();
        if (installRes && installRes.needs_backup_confirm) {
            if (confirm('Не удалось сделать бэкап. Продолжить без бэкапа?')) {
                const res2 = await eel.fw_install(category, [targetName], man || null, mod || null, 'auto', true, pre)();
                handleResult(res2, 'Установка завершена');
            } else {
                openInfoModal('Установка отменена пользователем');
            }
        } else {
            handleResult(installRes, 'Установка завершена');
        }
    } catch (e) {
        openErrorModal('Ошибка установки: ' + e.message);
    }

    fwDownloadTarget = null;
}

async function fwInstallSelected() {
    const cat = document.getElementById('fw-category')?.value || 'recovery';
    const checkboxes = Array.from(document.querySelectorAll('#firmware .fw-select'));
    const names = checkboxes.filter(ch => ch.checked).map(ch => ch.getAttribute('data-name'));
    if (!names.length) {
        openErrorModal('Выберите прошивки для установки');
        return;
    }
    const device = await fwEnsureDeviceSelection();
    if (!device) return;
    const { man, mod } = device;
    try {
        const res = await eel.fw_install(cat, names, man || null, mod || null, 'auto', false)();
        if (res && res.needs_backup_confirm) {
            // Показать подтверждение продолжить без бэкапа
            if (confirm('Не удалось сделать бэкап. Продолжить без бэкапа?')) {
                const res2 = await eel.fw_install(cat, names, man || null, mod || null, 'auto', true)();
                handleResult(res2, 'Установка завершена');
            } else {
                openInfoModal('Установка отменена пользователем');
            }
            return;
        }
        handleResult(res, 'Установка завершена');
    } catch (e) {
        openErrorModal('Ошибка установки: ' + e.message);
    }
}

function openFwDeviceModal() {
    const modal = document.getElementById('fw-device-modal');
    if (!modal) return;
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    const input = document.getElementById('fwm-input');
    if (input) {
        input.focus();
        input.select();
    }
}

function closeFwDeviceModal() {
    const modal = document.getElementById('fw-device-modal');
    if (!modal) return;
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    const sugg = document.getElementById('fwm-suggestions');
    if (sugg) {
        sugg.classList.add('hidden');
        sugg.innerHTML = '';
    }
}

function saveFwManualDevice() {
    const input = document.getElementById('fwm-input');
    if (!input) return;
    const v = (input.value || '').trim();
    if (!v) {
        openErrorModal('Введите производителя и модель');
        return;
    }
    const parts = v.split(/\s+/);
    fwSelectedMan = parts.shift() || '';
    fwSelectedMod = parts.join(' ');
    if (!fwSelectedMan || !fwSelectedMod) {
        openErrorModal('Введите производителя и модель полностью');
        return;
    }
    closeFwDeviceModal();
    fwRefresh();
}