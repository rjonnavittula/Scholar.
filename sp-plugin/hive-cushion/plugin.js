/**
 * HIVE Cushion — plugin entry.
 *
 * SP exposes the plugin API as a global `PluginAPI` inside plugin scripts.
 * We do the minimal thing: register a side-panel/header button whose content
 * is our iframe (index.html does the fetching + rendering, so the plugin
 * stays dumb and the panel works even if API names drift).
 *
 * ⚠ VERIFY: the exact registration method on PluginAPI for your SP version —
 *   grep `packages/plugin-api/src` for `registerSidePanelButton` /
 *   `registerHeaderButton` / `showIndexHtmlAsView`. The fallback chain below
 *   covers the names used across recent releases.
 */
/* global PluginAPI */

(function init() {
  const open = () => {
    if (typeof PluginAPI.showIndexHtmlAsView === 'function') {
      PluginAPI.showIndexHtmlAsView();
    }
  };

  if (typeof PluginAPI.registerSidePanelButton === 'function') {
    PluginAPI.registerSidePanelButton({
      label: 'Cushion',
      icon: 'schedule',
      onClick: open,
    });
  } else if (typeof PluginAPI.registerHeaderButton === 'function') {
    PluginAPI.registerHeaderButton({
      label: 'Cushion',
      icon: 'schedule',
      onClick: open,
    });
  } else {
    console.warn('[hive-cushion] no known button registration API; check PluginAPI surface');
  }
})();
