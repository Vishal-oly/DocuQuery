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
      $('#settingLlm').textContent = health.llm_available
        ? `${health.llm_model || 'default model'} (${health.llm_label || 'local model'} ready)`
        : 'Preview mode (local model unavailable)';
      $('#settingEmbedding').textContent = health.embedding_backend || '—';
      $('#settingUpload').textContent = `${health.max_upload_mb || 20} MB`;
      $('#footerStatus').textContent = health.llm_available
        ? `${health.llm_label || 'Local model'} ready · ${health.llm_model || 'default model'}`
        : 'Preview mode · no local model is running';
    } catch (error) {
      showToast(error.message);
    }
  }

  let modelState = null;

  function renderModels(payload) {
    modelState = payload;
    const ram = payload.ram_gb ? `${payload.ram_gb} GB RAM` : 'memory unknown';
    const recommended = payload.recommended_label ? ` · recommended: ${payload.recommended_label}` : '';
    $('#modelHardware').textContent =
      `${ram}${recommended}${payload.managed ? ' · switching is automatic' : ''}`;
    const list = $('#modelOptions');
    list.replaceChildren();
    (payload.options || []).forEach((option) => {
      const label = document.createElement('label');
      label.className = 'model-option';
      const radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = 'modelChoice';
      radio.value = option.id;
      radio.checked = option.id === payload.selected_id;
      const copy = document.createElement('span');
      copy.className = 'model-option-copy';
      const title = document.createElement('strong');
      title.textContent = option.label;
      const meta = document.createElement('span');
      const parts = [];
      if (option.size_mb) parts.push(`${option.size_mb} MB`);
      if (option.source) parts.push(option.source);
      if (option.recommended) parts.push('recommended');
      if (option.kind === 'preset' && !option.downloaded) parts.push('downloads when you pick it');
      meta.textContent = parts.join(' · ');
      copy.append(title, meta);
      label.append(radio, copy);
      radio.addEventListener('change', () => { $('#modelApply').disabled = false; });
      list.append(label);
    });
    $('#modelApply').disabled = true;
    const folder = $('#modelFolder');
    if (folder) {
      folder.textContent = payload.models_dir || 'models folder';
      folder.title = payload.models_dir || '';
    }
    const space = $('#modelSpace');
    if (space) {
      const free = Number(payload.free_space_mb || 0);
      space.textContent = free
        ? `${(free / 1024).toFixed(1)} GB free in that folder. Any other .gguf you drop there appears in this list.`
        : 'Any other .gguf you drop in that folder appears in this list.';
    }
    const current = payload.current || {};
    const anyDownloaded = (payload.options || []).some((option) => option.downloaded);
    $('#modelNote').textContent = current.available
      ? `In use now: ${current.model || 'model'} (${current.label})`
      : anyDownloaded
        ? 'Model is downloaded but not answering yet — it starts within a few seconds of a download.'
        : 'No model downloaded yet. Pick a preset above and press "Use selected model" to fetch it (internet needed once).';
  }

  async function loadModels() {
    try {
      renderModels(await api('/api/models'));
    } catch (error) {
      $('#modelHardware').textContent = 'Could not read the local model list.';
    }
  }

  $('#modelApply').addEventListener('click', async () => {
    const picked = document.querySelector('input[name="modelChoice"]:checked');
    if (!picked) return;
    $('#modelApply').disabled = true;
    try {
      const result = await api('/api/models/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: picked.value }),
      });
      $('#modelNote').textContent = result.message || 'Saved.';
      const chosen = ((modelState && modelState.options) || []).find((option) => option.id === picked.value);
      if (chosen && chosen.kind === 'preset' && !chosen.downloaded) {
        await startModelDownload(chosen, picked.value);
        return;
      }
      if (result.managed) {
        setTimeout(loadStatus, 6000);
        setTimeout(loadModels, 6000);
      }
    } catch (error) {
      $('#modelNote').textContent = error.message;
      $('#modelApply').disabled = false;
    }
  });

  function watchDownload(note, label, onFinish) {
    let timer = null;
    const stop = () => {
      if (timer !== null) window.clearInterval(timer);
      timer = null;
    };
    timer = window.setInterval(async () => {
      try {
        const status = await api('/api/models/download');
        if (status.state === 'downloading') {
          const done = status.received_mb || 0;
          const total = status.total_mb || 0;
          const percent = status.percent === null || status.percent === undefined
            ? `${done} MB`
            : `${status.percent}%${total ? ` of ${total} MB` : ''}`;
          note.textContent = `Downloading ${label} — ${percent}`;
          return;
        }
        stop();
        if (status.state === 'done') {
          note.textContent = `${status.label || label} is saved and selected. It is listed under AI model above.`;
          showToast(`${status.label || label} is ready.`);
          await loadModels();
          await loadStatus();
        } else if (status.state === 'error') {
          note.textContent = status.error || 'Download failed. Check your internet connection.';
        }
        if (onFinish) onFinish(status);
      } catch (error) {
        stop();
        note.textContent = error.message;
        if (onFinish) onFinish({ state: 'error', error: error.message });
      }
    }, 1500);
    return stop;
  }

  async function startLinkDownload(url) {
    const note = $('#modelLinkNote');
    const input = $('#modelLinkInput');
    const button = $('#modelLinkButton');
    note.textContent = 'Starting the download…';
    button.disabled = true;
    input.disabled = true;
    try {
      await api('/api/models/download-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      note.textContent = 'Downloading — this needs internet only this once.';
      input.value = '';
      watchDownload(note, 'the model', () => { button.disabled = false; input.disabled = false; });
    } catch (error) {
      note.textContent = error.message;
      button.disabled = false;
      input.disabled = false;
    }
  }

  const linkForm = $('#modelLinkForm');
  if (linkForm) {
    linkForm.addEventListener('submit', (event) => {
      event.preventDefault();
      const input = $('#modelLinkInput');
      const url = input.value.trim();
      if (!/^https?:\/\//i.test(url)) {
        $('#modelLinkNote').textContent = 'Paste a link that starts with https:// — the direct .gguf file link.';
        input.focus();
        return;
      }
      startLinkDownload(url);
    });
  }

  const revealButton = $('#modelReveal');
  if (revealButton) {
    revealButton.addEventListener('click', async () => {
      try {
        const result = await api('/api/models/reveal', { method: 'POST' });
        $('#modelSpace').textContent = result.ok
          ? 'Folder opened — drop any .gguf into it and reload this page.'
          : `Open this folder yourself: ${result.path}`;
      } catch (error) {
        showToast(error.message);
      }
    });
  }

  async function startModelDownload(option, id) {
    const note = $('#modelNote');
    note.textContent = `Downloading ${option.label} — internet is needed only this once…`;
    try {
      await api('/api/models/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id }),
      });
    } catch (error) {
      note.textContent = error.message;
      $('#modelApply').disabled = false;
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const status = await api('/api/models/download');
        if (status.state === 'downloading') {
          const percent = status.percent === null || status.percent === undefined
            ? `${status.received_mb || 0} MB`
            : `${status.percent}%`;
          note.textContent = `Downloading ${option.label} — ${percent}`;
          return;
        }
        window.clearInterval(timer);
        if (status.state === 'done') {
          note.textContent = `${option.label} is ready and selected.`;
          await loadModels();
          await loadStatus();
        } else if (status.state === 'error') {
          note.textContent = status.error || 'Download failed. Check your internet connection.';
          $('#modelApply').disabled = false;
        }
      } catch (error) {
        window.clearInterval(timer);
        note.textContent = error.message;
        $('#modelApply').disabled = false;
      }
    }, 2000);
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

  // Clear history: two-click confirm (works even where browser dialogs are blocked).
  const clearHistoryButton = $('#clearHistoryButton');
  if (clearHistoryButton) {
    let armed = false;
    let armTimer = null;
    clearHistoryButton.addEventListener('click', async () => {
      if (!armed) {
        armed = true;
        clearHistoryButton.textContent = 'Click again to confirm';
        clearHistoryButton.classList.add('armed');
        armTimer = window.setTimeout(() => {
          armed = false;
          clearHistoryButton.textContent = 'Clear all history';
          clearHistoryButton.classList.remove('armed');
        }, 5000);
        return;
      }
      window.clearTimeout(armTimer);
      armed = false;
      clearHistoryButton.disabled = true;
      clearHistoryButton.textContent = 'Clearing…';
      try {
        const payload = await api('/api/me/clear-history', { method: 'POST' });
        showToast(`History cleared — ${payload.deleted} paper(s) removed.`);
        setAlert(`History cleared. ${payload.deleted} paper(s) deleted.`, 'success');
        window.setTimeout(() => window.location.reload(), 1200);
      } catch (error) {
        setAlert(error.message);
        clearHistoryButton.disabled = false;
        clearHistoryButton.textContent = 'Clear all history';
        clearHistoryButton.classList.remove('armed');
      }
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
    await loadModels();
  }

  // Buttons/Enter keys work even where native form submission is blocked (sandboxed iframes).
  if (window.DQAuth && window.DQAuth.bindForm) {
    window.DQAuth.bindForm('#nameForm', '#saveNameButton', ['#nameInput']);
    window.DQAuth.bindForm('#passwordForm', '#updatePasswordButton', ['#currentPassword', '#newPassword']);
  }

  initialize();
})();
