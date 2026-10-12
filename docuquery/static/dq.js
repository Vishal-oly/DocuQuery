/* DocuQuery auth-token helper.
   Cookies are blocked in sandboxed/third-party iframe previews, so the app
   carries a signed auth token in localStorage and on internal links instead. */
window.DQAuth = (() => {
  const STORAGE_KEY = 'docuquery_token';
  let memoryToken = '';

  function getToken() {
    if (memoryToken) return memoryToken;
    try {
      memoryToken = window.localStorage.getItem(STORAGE_KEY) || '';
    } catch {
      memoryToken = '';
    }
    return memoryToken;
  }

  function setToken(token) {
    memoryToken = token || '';
    try {
      if (token) window.localStorage.setItem(STORAGE_KEY, token);
      else window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* localStorage may be unavailable; the in-memory value still works */
    }
  }

  function clearToken() {
    setToken('');
  }

  function withToken(url) {
    const token = getToken();
    if (!token || String(url).includes('token=')) return url;
    return url + (String(url).includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token);
  }

  function captureUrlToken() {
    try {
      const params = new URLSearchParams(window.location.search);
      const token = params.get('token');
      if (token) {
        setToken(token);
        params.delete('token');
        const query = params.toString();
        const clean = window.location.pathname + (query ? `?${query}` : '') + window.location.hash;
        window.history.replaceState(null, '', clean);
      }
    } catch {
      /* ignore */
    }
    return getToken();
  }

  function rewriteLinks() {
    try {
      document.querySelectorAll('a[href^="/"]').forEach((anchor) => {
        const href = anchor.getAttribute('href');
        if (href && !href.includes('token=')) anchor.setAttribute('href', withToken(href));
      });
    } catch {
      /* ignore */
    }
  }

  async function apiFetch(url, options = {}) {
    const token = getToken();
    const headers = { ...(options.headers || {}) };
    if (token && !headers.Authorization) headers.Authorization = `Bearer ${token}`;
    // Send the token in the URL too: some preview proxies strip the Authorization
    // header, and the server accepts either source.
    return fetch(withToken(url), { ...options, headers });
  }

  /* Bind a form so its button clicks and Enter keys work even in sandboxed
     iframes, where the browser blocks native form submission (and never fires
     the submit event) unless the sandbox has the 'allow-forms' permission. */
  function bindForm(formSelector, buttonSelector, inputSelectors) {
    const form = document.querySelector(formSelector);
    const button = document.querySelector(buttonSelector);
    if (!form || !button) return;
    const fire = (event) => {
      if (event) event.preventDefault();
      form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    };
    button.addEventListener('click', fire);
    (inputSelectors || []).forEach((selector) => {
      const input = document.querySelector(selector);
      if (input) {
        input.addEventListener('keydown', (event) => {
          if (event.key === 'Enter') fire(event);
        });
      }
    });
  }

  /* Initialise as soon as this script loads. */
  captureUrlToken();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', rewriteLinks);
  } else {
    rewriteLinks();
  }

  return { getToken, setToken, clearToken, withToken, captureUrlToken, rewriteLinks, apiFetch, bindForm };
})();
