(function(){
  // Ждём появления PluginUI
  function ready(fn){ if (window.PluginUI) fn(); else setTimeout(()=>ready(fn), 50); }
  ready(() => {
    // Перехватываем applyTheme для отслеживания смены тем
    const originalApplyTheme = window.applyTheme;
    if (originalApplyTheme && !originalApplyTheme._original) {
      // Сохраняем оригинальную функцию
      originalApplyTheme._original = originalApplyTheme;
      
      window.applyTheme = function(theme) {
        // Отмечаем, что пользователь сменил тему (если не custom)
        if (theme !== 'custom') {
          localStorage.setItem('theme_changed_by_user', 'true');
          // Сохраняем резервную копию темы
          localStorage.setItem('app_theme_backup', theme);
        }
        // Вызываем оригинальную функцию
        return originalApplyTheme.call(this, theme);
      };
    }

    // Инжектируем CSS, привязанный к переменным темы, чтобы панели/карточки подстраивались
    try {
      const style = document.createElement('style');
      style.setAttribute('data-plugin-css', 'custom-theme-overrides');
      style.textContent = `
        /* Панели и карточки, зависящие от темы */
        .neon-details {
          background: color-mix(in srgb, var(--bg) 85%, black 15%);
          border: 1px solid color-mix(in srgb, var(--neon) 35%, transparent);
          box-shadow: 0 0 12px color-mix(in srgb, var(--neon) 25%, transparent);
        }
        /* Кнопки выбора тем в модалке: перекрасим кольцо под var(--neon) */
        .theme-option {
          box-shadow: 0 0 0 1px color-mix(in srgb, var(--neon) 60%, transparent);
        }
        .theme-option:hover {
          background-color: color-mix(in srgb, var(--bg) 80%, black 20%);
        }
        /* Плашки и боксы в списке плагинов */
        #plugins .neon-details {
          background: color-mix(in srgb, var(--bg) 88%, black 12%);
          border-color: color-mix(in srgb, var(--neon) 35%, transparent);
          box-shadow: 0 0 14px color-mix(in srgb, var(--neon) 25%, transparent);
        }
      `;
      document.head.appendChild(style);
    } catch (e) { /* ignore */ }

    // Добавим секцию в модальное окно Themes динамически
    const modal = document.getElementById('theme-modal');
    if (!modal) return;
    const container = modal.querySelector('.space-y-3');
    if (!container) return;

    const block = document.createElement('div');
    block.className = 'neon-details';
    block.setAttribute('data-plugin-ui', 'custom-theme');
    block.innerHTML = `
      <div class="details-body">
        <div class="text-neon-400"><b>Custom Theme</b></div>
        <div class="text-slate-300 mb-2">Выберите основной и дополнительный цвета, затем нажмите «Установить».</div>
        <div class="flex items-center gap-3 mb-2">
          <div>
            <label class="text-sm text-slate-300">Primary</label>
            <input id="ctm-primary" type="color" value="#22d3ee" />
          </div>
          <div>
            <label class="text-sm text-slate-300">Secondary</label>
            <input id="ctm-secondary" type="color" value="#a855f7" />
          </div>
          <button class="neon-button" id="ctm-apply">Установить</button>
        </div>
        <div id="ctm-preview" class="text-slate-300 text-sm"></div>
      </div>`;

    container.appendChild(block);

    // список сохранённых тем
    const listWrap = document.createElement('div');
    listWrap.className = 'neon-details';
    listWrap.setAttribute('data-plugin-ui', 'custom-theme');
    listWrap.innerHTML = `
      <div class="details-body">
        <div class="text-neon-400"><b>Saved Custom Themes</b></div>
        <div id="ctm-list" class="mt-2 space-y-2 text-slate-300 text-sm"></div>
      </div>`;
    container.appendChild(listWrap);

    const btnApplyCT = block.querySelector('#ctm-apply');
    const previewCT = block.querySelector('#ctm-preview');
    const listEl = listWrap.querySelector('#ctm-list');
    btnApplyCT.addEventListener('click', async () => {
      const p = block.querySelector('#ctm-primary').value;
      const s = block.querySelector('#ctm-secondary').value;
      const res = await eel.plugin_call('ct_generate_palette', p, s)();
      if (!res || !res.ok) {
        openErrorModal('Ошибка генерации палитры: ' + (res && res.error || 'unknown'));
        return;
      }
      const pal = res.palette || {};
      previewCT.innerHTML = `
        <div class="text-slate-300">neon: <span style="color:${pal.neon}">${pal.neon}</span> · bg: <span style="color:${pal.soft}">${pal.bg}</span> · accent: <span style="color:${pal.accent}">${pal.accent}</span></div>
      `;
      openCTSaveModal({ primary: p, secondary: s, palette: pal }, refreshSavedThemes);
    });

    async function refreshSavedThemes() {
      try {
        console.log('Refreshing saved themes...');
        const res = await eel.plugin_call('ct_list_palettes')();
        console.log('List themes result:', res);
        if (!res || !res.ok) {
          console.error('Failed to get themes:', res);
          listEl.innerHTML = '<div class="text-slate-500">Ошибка загрузки тем</div>';
          return;
        }
        const items = res.themes || [];
        const last = res.last || '';
        console.log('Found themes:', items.length);
        listEl.innerHTML = items.map(t => `
          <div class="flex items-center justify-between gap-2">
            <div>
              <span class="text-slate-100">${escapeHtml(t.name)}</span>
              <span class="text-slate-500">· ${escapeHtml(t.primary)} / ${escapeHtml(t.secondary)}</span>
            </div>
            <div class="flex items-center gap-2">
              <button class="neon-button" data-act="apply" data-name="${escapeHtml(t.name)}">Применить</button>
              <button class="neon-button" data-act="delete" data-name="${escapeHtml(t.name)}">Удалить</button>
            </div>
          </div>
        `).join('') || '<div class="text-slate-500">Сохранённых тем нет</div>';
      } catch (e) {
        console.error('Error refreshing themes:', e);
        listEl.innerHTML = '<div class="text-slate-500">Ошибка загрузки тем</div>';
      }

      listEl.querySelectorAll('button[data-act="apply"]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const name = btn.getAttribute('data-name');
          const data = await eel.plugin_call('ct_list_palettes')();
          const found = (data.themes||[]).find(x => x.name === name);
          if (!found) return;
          if (window.applyCustomTheme) window.applyCustomTheme(found.palette);
          if (window.applyTheme) window.applyTheme('custom');
          // НЕ сохраняем в localStorage - только применяем временно
        });
      });

      listEl.querySelectorAll('button[data-act="delete"]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const name = btn.getAttribute('data-name');
          await eel.plugin_call('ct_delete_palette', name)();
          await refreshSavedThemes();
        });
      });
    }

    // При открытии модалки — загружаем сохранённые темы и восстанавливаем кастомную (если не менялась)
    (async () => {
      try {
        // Проверяем, менял ли пользователь тему после установки кастомной
        const themeChanged = localStorage.getItem('theme_changed_by_user') === 'true';
        const customThemeLast = localStorage.getItem('custom_theme_last');
        
        if (!themeChanged && customThemeLast) {
          try {
            const obj = JSON.parse(customThemeLast);
            if (obj && obj.palette && window.applyCustomTheme && window.applyTheme) {
              window.applyCustomTheme(obj.palette);
              window.applyTheme('custom');
            }
          } catch (e) {
            console.warn('Failed to restore custom theme:', e);
          }
        }
        
        await refreshSavedThemes();
      } catch (e) {
        console.error('Error loading themes:', e);
        await refreshSavedThemes();
      }
    })();

    // Перехватываем открытие модалки, чтобы загружать темы
    const originalOpenThemeModal = window.openThemeModal;
    if (originalOpenThemeModal && !originalOpenThemeModal._original) {
      // Сохраняем оригинальную функцию
      originalOpenThemeModal._original = originalOpenThemeModal;
      
      window.openThemeModal = function() {
        originalOpenThemeModal();
        // Загружаем темы при открытии
        setTimeout(async () => {
          try {
            await refreshSavedThemes();
          } catch (e) {
            console.error('Error refreshing themes on modal open:', e);
          }
        }, 100);
      };
    }
  });
})();

function escapeHtml(s){
  return String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;','\'':'&#39;'}[c]));
}

// Локальное модальное окно сохранения/установки темы (без правок ядра)
function openCTSaveModal(ctx, onSavedList) {
  let wrapper = document.getElementById('ct-save-modal');
  if (!wrapper) {
    wrapper = document.createElement('div');
    wrapper.id = 'ct-save-modal';
    wrapper.className = 'fixed inset-0 bg-black/60 hidden items-center justify-center z-50';
    wrapper.setAttribute('data-plugin-ui', 'custom-theme');
    wrapper.innerHTML = `
      <div class="w-[560px] max-w-[90vw] rounded-xl p-4 modal-panel">
        <h2 class="page-title text-xl mb-3">Сохранение темы</h2>
        <div class="text-slate-300 mb-2">Введите название темы (опционально), затем выберите действие.</div>
        <input id="ctm-name" type="text" class="w-full mt-1 neon-select" placeholder="Custom Theme" />
        <div class="mt-4 flex items-center justify-end gap-2">
          <button id="ctm-cancel" class="neon-button">Отмена</button>
          <button id="ctm-install" class="neon-button">Установить</button>
          <button id="ctm-save-install" class="neon-button">Сохранить и установить</button>
        </div>
      </div>`;
    document.body.appendChild(wrapper);
  }
  const show = () => { wrapper.classList.remove('hidden'); wrapper.classList.add('flex'); };
  const hide = () => { wrapper.classList.add('hidden'); wrapper.classList.remove('flex'); };

  const nameInput = wrapper.querySelector('#ctm-name');
  nameInput.value = '';
  const onCancel = () => { hide(); };
  const onInstall = async () => {
    try {
      if (window.applyCustomTheme) window.applyCustomTheme(ctx.palette);
      if (window.applyTheme) window.applyTheme('custom');
      // Сохраняем для восстановления при перезапуске (если пользователь не сменит тему)
      localStorage.setItem('custom_theme_last', JSON.stringify(ctx));
      localStorage.removeItem('theme_changed_by_user'); // Сбрасываем флаг смены темы
    } finally { hide(); }
  };
  const onSaveInstall = async () => {
    const name = (nameInput.value || 'Custom Theme');
    try {
      const res = await eel.plugin_call('ct_save_palette', name, ctx.primary, ctx.secondary)();
      if (res && res.ok && typeof onSavedList === 'function') await onSavedList();
      // также сохраняем как последнюю локально
      localStorage.setItem('custom_theme_last', JSON.stringify(ctx));
      localStorage.removeItem('theme_changed_by_user'); // Сбрасываем флаг смены темы
      if (window.applyCustomTheme) window.applyCustomTheme(ctx.palette);
      if (window.applyTheme) window.applyTheme('custom');
    } finally { hide(); }
  };

  wrapper.querySelector('#ctm-cancel').onclick = onCancel;
  wrapper.querySelector('#ctm-install').onclick = onInstall;
  wrapper.querySelector('#ctm-save-install').onclick = onSaveInstall;

  show();
}

