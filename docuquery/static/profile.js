(() => {
  const $ = (selector) => document.querySelector(selector);

  let toastTimer = null;
  function showToast(message) {
    const toast = $('#toast');
    toast.textContent = message;
    toast.hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => { toast.hidden = true; }, 3600);
  }

  function setAlert(message, kind = 'error') {
    const alertBox = $('#profileAlert');
    alertBox.textContent = message;
    alertBox.classList.toggle('success', kind === 'success');
    alertBox.hidden = !message;
  }

  function setFieldError(input, errorId, message) {
    const error = $(`#${errorId}`);
    if (message) {
      input.classList.add('invalid');
      error.textContent = message;
      error.hidden = false;
    } else {
      input.classList.remove('invalid');
      error.textContent = '';
      error.hidden = true;
    }
  }

  async function api(url, options = {}) {
    const fetchFn = window.DQAuth ? window.DQAuth.apiFetch : fetch;
    const response = await fetchFn(url, options);
    let payload;
    try { payload = await response.json(); } catch { payload = {}; }
    if (response.status === 401) {
      if (window.DQAuth) window.DQAuth.clearToken();
      window.location.href = '/login';
      throw new Error('Please sign in to continue.');
    }
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
  }

  function turl(url) {
    return window.DQAuth ? window.DQAuth.withToken(url) : url;
  }

  function textElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text || '';
    return element;
  }

  function formatSize(bytes) {
    const value = Number(bytes) || 0;
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatDate(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    } catch {
      return iso;
    }
  }

  function renderUser(user) {
    $('#profileName').textContent = user.name || '—';
    $('#profileEmail').textContent = user.email || '—';
    $('#profileJoined').textContent = `Member since ${formatDate(user.created_at)}`;
    $('#profileAvatar').textContent = (user.name || 'U').trim().charAt(0).toUpperCase();
    $('#nameInput').value = user.name || '';
  }

  function renderFiles(papers) {
    const list = $('#filesList');
    list.replaceChildren();
    $('#filesCount').textContent = String(papers.length);
    if (!papers.length) {
      list.append(textElement('div', 'library-empty', 'Papers you upload will appear here.'));
      return;
    }
    papers.forEach((paper) => {
      const row = document.createElement('article');
      row.className = 'file-row';

      const icon = textElement('span', 'library-pdf', 'PDF');
      const copy = document.createElement('div');
      copy.className = 'file-copy';
      copy.append(textElement('strong', '', paper.title || paper.filename));
      copy.append(textElement('span', 'file-meta',
        `${paper.filename || 'paper.pdf'} · ${paper.page_count || 0} pages · ${paper.file_size ? formatSize(paper.file_size) : 'not stored'} · ${formatDate(paper.created_at)}`));

      const actions = document.createElement('div');
      actions.className = 'file-actions';

      const brief = document.createElement('a');
      brief.className = 'btn btn-outline-soft';
      brief.href = turl(`/summaries?paper=${encodeURIComponent(paper.id)}`);
      brief.textContent = 'Brief';
      actions.append(brief);

      const view = document.createElement('a');
      view.className = 'btn btn-outline-soft';
      view.href = paper.has_file ? turl(`/api/papers/${encodeURIComponent(paper.id)}/file`) : '#';
      view.target = '_blank';
      view.rel = 'noopener';
      view.textContent = 'View file';
      if (!paper.has_file) {
        view.classList.add('disabled');
        view.addEventListener('click', (event) => {
          event.preventDefault();
          showToast('The original PDF is not stored for this paper.');
        });
      }
      actions.append(view);

      const remove = document.createElement('button');
      remove.className = 'btn btn-outline-soft file-delete';
      remove.type = 'button';
      remove.textContent = 'Delete';
      remove.addEventListener('click', async () => {
        if (!window.confirm(`Remove “${paper.title || paper.filename}”?`)) return;
        try {
          await api(`/api/papers/${encodeURIComponent(paper.id)}`, { method: 'DELETE' });
          showToast('Paper removed.');
          await loadFiles();
        } catch (error) {
          showToast(error.message);
        }
      });
      actions.append(remove);

      row.append(icon, copy, actions);
      list.append(row);
    });
  }

  async function loadFiles() {
    try {
      const payload = await api('/api/papers');
      renderFiles(payload.papers || []);
    } catch (error) {
      showToast(error.message);
    }
  }

  async function loadStatus() {
    try {
      const health = await api('/api/health');
      $('#settingDatabase').textContent = health.database || '—';
      $('#settingLlm').textContent = health.llm_available ? `${health.llm_model} (Groq ready)` : 'Preview mode (no Groq key)';
      $('#settingEmbedding').textContent = health.embedding_backend || '—';
      $('#settingUpload').textContent = `${health.max_upload_mb || 20} MB`;
      $('#footerStatus').textContent = health.llm_available ? `Groq ready · ${health.llm_model}` : 'Preview mode · add a Groq key for generated answers';
    } catch (error) {
      showToast(error.message);
    }
  }

  $('#nameForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const name = $('#nameInput').value.trim();
    if (name.length < 2 || name.length > 60) {
      setFieldError($('#nameInput'), 'nameError', 'Enter your name (2-60 characters).');
      return;
    }
    setFieldError($('#nameInput'), 'nameError', '');
    try {
      const payload = await api('/api/me', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      renderUser(payload.user);
      const chipName = $('#userChip .user-chip-name');
      if (chipName) chipName.textContent = payload.user.name;
      const chipAvatar = $('#userChip .user-chip-avatar');
      if (chipAvatar) chipAvatar.textContent = (payload.user.name || 'U').trim().charAt(0).toUpperCase();
      setAlert('Profile updated successfully.', 'success');
    } catch (error) {
      setAlert(error.message);
    }
  });

  $('#passwordForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const currentInput = $('#currentPassword');
    const newInput = $('#newPassword');
    let ok = true;
    if (!currentInput.value) {
      setFieldError(currentInput, 'currentPasswordError', 'Enter your current password.');
      ok = false;
    } else setFieldError(currentInput, 'currentPasswordError', '');
    if (newInput.value.length < 6) {
      setFieldError(newInput, 'newPasswordError', 'New password must be at least 6 characters.');
      ok = false;
    } else setFieldError(newInput, 'newPasswordError', '');
    if (!ok) return;

    try {
      await api('/api/me/password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: currentInput.value, new_password: newInput.value }),
      });
      currentInput.value = '';
      newInput.value = '';
      setAlert('Password updated successfully.', 'success');
    } catch (error) {
      setAlert(error.message);
    }
  });

  const logoutButton = $('#logoutButton');
  if (logoutButton) {
    logoutButton.addEventListener('click', async () => {
      try { await fetch('/api/logout', { method: 'POST' }); } catch { /* ignore */ }
      if (window.DQAuth) window.DQAuth.clearToken();
      window.location.href = '/';
    });
  }

  async function initialize() {
    try {
      const payload = await api('/api/me');
      renderUser(payload.user);
    } catch (error) {
      showToast(error.message);
      return;
    }
    await loadFiles();
    await loadStatus();
  }

  // Buttons/Enter keys work even where native form submission is blocked (sandboxed iframes).
  if (window.DQAuth && window.DQAuth.bindForm) {
    window.DQAuth.bindForm('#nameForm', '#saveNameButton', ['#nameInput']);
    window.DQAuth.bindForm('#passwordForm', '#updatePasswordButton', ['#currentPassword', '#newPassword']);
  }

  initialize();
})();
