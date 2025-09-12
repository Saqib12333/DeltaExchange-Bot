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

// Debug probe: log htmx presence & attach listener to cancel buttons to confirm clicks reach JS layer
window.addEventListener('DOMContentLoaded', () => {
  function showToast(message, type='info', timeout=2200){
    const container = document.getElementById('toast-container');
    if(!container) return;
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = message;
    container.appendChild(el);
    requestAnimationFrame(()=>{ el.classList.add('visible'); });
    setTimeout(()=>{
      el.classList.remove('visible');
      setTimeout(()=> el.remove(), 400);
    }, timeout);
  }
  console.log('[debug] htmx present:', !!window.htmx, 'ws ext:', !!(window.htmx && window.htmx.extensions && window.htmx.extensions.ws));
  document.body.addEventListener('click', (e) => {
    if(e.target && e.target.classList && e.target.classList.contains('order-cancel-btn')){
      console.log('[debug] cancel button clicked (dom)', e.target.getAttribute('value') || e.target.value);
    }
  });
  // Fetch fallback for cancel forms if htmx not sending HX-Request
  document.body.addEventListener('submit', async (e) => {
    const form = e.target;
    if(!(form instanceof HTMLFormElement)) return;
    if(!form.classList.contains('inline-cancel-form')) return;
    // Always intercept to avoid full navigation regardless of htmx presence
    e.preventDefault();
    const formData = new FormData(form);
    try {
      const resp = await fetch(form.action, {
        method: 'POST',
        headers: { 'X-Fetch-Cancel': '1' },
        body: new URLSearchParams([...formData.entries()])
      });
      if(resp.ok){
        const html = await resp.text();
        const ordersEl = document.getElementById('orders');
        if(ordersEl){ ordersEl.innerHTML = html; }
        showToast('Order cancelled', 'success');
      } else {
        console.warn('Cancel fetch failed status', resp.status);
        showToast('Cancel failed', 'error');
      }
    } catch(err){
      console.warn('Cancel fetch exception', err);
      showToast('Cancel error', 'error');
    }
  });
});
