// web/script.js
function showTab(tabId) {
    const tabs = document.querySelectorAll('.tab-content');
    tabs.forEach(tab => {
        tab.classList.remove('active');
    });
    document.getElementById(tabId).classList.add('active');
}

function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const toggleBtn = document.querySelector('.toggle-btn');
    const content = document.querySelector('.content');
    sidebar.classList.toggle('hidden');
    toggleBtn.textContent = sidebar.classList.contains('hidden') ? '❮' : '❯';
}

async function startRoot() {
    const img = document.getElementById('root-boot-path').value || null;
    const method = document.getElementById('root-method').value || 'auto';
    const res = await eel.perform_root(img, method)();
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
            const res2 = await eel.perform_root(img)();
            handleResult(res2, 'Рут завершён');
        }
        return;
    }
    if (res && res.manual_fastboot) {
        const steps = (res.instructions || []).join('\n- ');
        alert('Нужно войти в fastboot вручную:\n- ' + steps);
        const res2 = await eel.perform_root(img, method)();
        handleResult(res2, 'Рут завершён');
        return;
    }
    handleResult(res, 'Рут завершён');
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
    const res = await eel.perform_unlock(method)();
    handleResult(res, 'Разблокировка завершена');
}

async function startFlash() {
    const partition = document.getElementById('flash-partition').value;
    const path = document.getElementById('flash-image-path').value;
    const method = document.getElementById('flash-method').value || 'auto';
    const res = await eel.perform_flash(partition, path, method)();
    handleResult(res, 'Прошивка завершена');
}

function handleResult(res, successMsg) {
    if (!res || !res.ok) {
        alert('Ошибка: ' + (res && res.error ? res.error : 'Неизвестная'));
    } else {
        alert(successMsg);
    }
}