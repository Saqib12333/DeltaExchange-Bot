// Minimal client-side WS updater as a fallback if HTMX ws extension isn't active.
(function(){
  function connectAndRender(elId, url){
    const el = document.getElementById(elId);
    if(!el) return;
    try {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const wsUrl = url.startsWith('ws') ? url : `${proto}://${location.host}${url}`;
      let ws = new WebSocket(wsUrl);
      ws.onmessage = (evt) => {
        // Server sends HTML partials; swap directly
        el.innerHTML = evt.data;
      };
      ws.onclose = () => {
        // Reconnect with backoff
        setTimeout(() => connectAndRender(elId, url), 1000);
      };
    } catch (e) {
      console.warn('WS fallback connect failed for', url, e);
    }
  }
  // If HTMX ws extension isn't present, use fallback for known sections
  function isHtmxWsActive(){
    try { return !!(window.htmx && window.htmx.extensions && window.htmx.extensions.ws); } catch { return false; }
  }
  function boot(){
    if(!isHtmxWsActive()){
      connectAndRender('mark', '/ws/mark');
      connectAndRender('balances', '/ws/balances');
      connectAndRender('positions', '/ws/positions');
      connectAndRender('orders', '/ws/orders');
    }
  }
  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', boot);
  } else { boot(); }

  // Optional: log htmx ws errors if used
  document.addEventListener('htmx:wsError', (e) => {
    console.warn('HTMX WebSocket error on', e.detail ? e.detail.socketWrapper.url : 'unknown');
  });
})();
