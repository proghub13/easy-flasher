(function(){
  if (!window.PluginUI) return;
  // Добавим вкладку с HTML из panel.html (он уже инжектится)
  // Для простоты найдём вставленный panel по id и перенесём его в новую вкладку
  function mount() {
    const panel = document.getElementById('ui-demo-panel');
    if (!panel) { setTimeout(mount, 100); return; }
    window.PluginUI.addTab('ui-demo', 'UI Demo', panel.outerHTML);
    // Добавим пункт в сайдбар
    // Sidebar пункт уже создаётся addTab, но покажем пример ручного добавления:
    // window.PluginUI.addSidebarItem('UI Demo', () => showTab('ui-demo'));
  }
  mount();
})();

