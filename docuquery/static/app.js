(() => {
  const $ = (selector) => document.querySelector(selector);
  const pdfInput = $('#pdfInput');
  const dropZone = $('#dropZone');
  const browseButton = $('#browseButton');
  const uploadProgress = $('#uploadProgress');
  const uploadProgressBar = $('#uploadProgressBar');
  const uploadProgressLabel = $('#uploadProgressLabel');
  const pageAlert = $('#pageAlert');
  const emptyState = $('#emptyState');
  const resultsPanel = $('#resultsPanel');
  const chatInput = $('#chatInput');
  const sendButton = $('#sendButton');
  const chatForm = $('#chatForm');
  const chatMessages = $('#chatMessages');
  const assistantWelcome = $('#assistantWelcome');
  const sectionLinks = [...document.querySelectorAll('.section-link')];
  const paperOnlyLinks = document.querySelectorAll('.section-link.requires-paper');
  const summaryFields = [
    ['overall_summary', 'Overview', '✦', true],
    ['objective', 'Research objective', '◎'],
    ['methodology', 'Methodology', '⌘'],
    ['dataset', 'Data & materials', '▤'],
    ['key_findings', 'Key findings', '↗'],
    ['limitations', 'Limitations', '△'],
    ['conclusion', 'Conclusion', '◌'],
  ];
  let activePaper = null;
  let maxUploadMb = 20;
  let toastTimer = null;
  let uploadTimer = null;
  let uploadInProgress = false;
  let chatEpoch = 0;

  function setActiveSection(sectionName) {
    sectionLinks.forEach((link) => {
      const active = link.dataset.section === sectionName;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
  }

  function setPaperSectionsEnabled(enabled) {
    paperOnlyLinks.forEach((link) => {
      link.setAttribute('aria-disabled', String(!enabled));
    });
  }

  function setAlert(message, kind = 'error') {
    pageAlert.textContent = message;
    pageAlert.classList.toggle('success', kind === 'success');
    pageAlert.hidden = !message;
  }

  function showToast(message) {
    const toast = $('#toast');
    toast.textContent = message;
    toast.hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => { toast.hidden = true; }, 3600);
  }

  async function api(url, options = {}) {
    const fetchFn = window.DQAuth ? window.DQAuth.apiFetch : fetch;
    const response = await fetchFn(url, options);
    let payload;
    try { payload = await response.json(); }
    catch { payload = {}; }
    if (response.status === 401 && !url.startsWith('/api/login') && !url.startsWith('/api/register')) {
      if (window.DQAuth) window.DQAuth.clearToken();
      window.location.href = '/login';
      throw new Error(payload.error || 'Please sign in to continue.');
    }
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
  }

  function textElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text || '';
    return element;
  }

  function renderSummary(summary = {}) {
    const grid = $('#summaryGrid');
    grid.replaceChildren();
    summaryFields.forEach(([field, label, icon, wide]) => {
      const card = document.createElement('article');
      card.className = `summary-card${wide ? ' summary-card-wide' : ''}`;
      card.dataset.field = field;
      const header = document.createElement('div');
      header.className = 'summary-card-top';
      header.append(textElement('span', 'summary-card-icon', icon));
      header.append(textElement('span', 'summary-card-title', label));
      const body = textElement('p', '', summary[field] || 'Not clearly stated in the retrieved text.');
      card.append(header, body);
      grid.append(card);
    });

    $('#summaryMode').textContent = summary.mode || 'Research brief';
    const notice = $('#summaryNotice');
    notice.textContent = summary.notice || '';
    notice.hidden = !summary.notice;
    renderSources(summary.sources || [], '#summarySources', '#sourcesCount');
  }

  function renderSources(sources, targetSelector, countSelector) {
    const list = $(targetSelector);
    list.replaceChildren();
    if (countSelector) $(countSelector).textContent = `${sources.length} passage${sources.length === 1 ? '' : 's'}`;
    if (!sources.length) {
      list.append(textElement('div', 'no-sources', 'No source passages were attached to this response.'));
      return;
    }
    sources.forEach((source) => {
      const item = document.createElement('article');
      item.className = 'source-item';
      const head = document.createElement('div');
      head.className = 'source-item-head';
      head.append(textElement('span', 'source-page', `PAGE ${source.page_number || 1}`));
      head.append(textElement('span', 'source-section', source.section || 'Paper excerpt'));
      item.append(head, textElement('p', '', source.excerpt || ''));
      list.append(item);
    });
  }

  function updateChatContext(paper) {
    const context = $('#chatContext');
    context.replaceChildren();
    context.append(textElement('span', 'context-icon', '⌕'));
    const title = paper ? (paper.title || paper.filename) : 'Upload a paper to start asking';
    context.append(textElement('span', '', title));
  }

  let chatLog = [];
  let restoringChat = false;

  function chatStorageKey() {
    return activePaper ? `dqChat:${activePaper.id}` : '';
  }

  function persistChat() {
    if (restoringChat) return;
    const key = chatStorageKey();
    if (!key) return;
    try {
      localStorage.setItem(key, JSON.stringify(chatLog.slice(-40)));
    } catch (error) { /* storage may be full or blocked */ }
  }

  function restoreChat(paper) {
    chatLog = [];
    chatMessages.replaceChildren();
    if (assistantWelcome) chatMessages.append(assistantWelcome);
    if (!paper) return;
    let saved = null;
    try {
      saved = JSON.parse(localStorage.getItem(`dqChat:${paper.id}`) || 'null');
    } catch (error) { saved = null; }
    if (!Array.isArray(saved) || !saved.length) return;
    restoringChat = true;
    saved.forEach((entry) => {
      chatLog.push(entry);
      addMessage(entry.role, entry.text, entry.sources || [], entry.mode || '');
    });
    restoringChat = false;
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function addMessage(role, text, sources = [], mode = '') {
    if (assistantWelcome && assistantWelcome.isConnected) assistantWelcome.remove();    const message = document.createElement('div');
    message.className = `chat-message ${role}`;
    message.append(textElement('div', 'chat-bubble', text));
    if (role === 'assistant' && sources.length) {
      const sourceRow = document.createElement('div');
      sourceRow.className = 'chat-message-meta';
      sourceRow.append(textElement('span', 'meta-label', 'Evidence:'));
      const pages = [...new Set(sources.map((source) => source.page_number || 1))].slice(0, 4);
      const token = window.DQAuth ? window.DQAuth.getToken() : '';
      pages.forEach((page) => {
        if (activePaper && token) {
          const link = document.createElement('a');
          link.className = 'chat-source-mini';
          link.href = `/api/papers/${encodeURIComponent(activePaper.id)}/file?token=${encodeURIComponent(token)}#page=${page}`;
          link.target = '_blank';
          link.rel = 'noopener';
          link.title = `Open page ${page} in the PDF`;
          link.textContent = `p. ${page}`;
          sourceRow.append(link);
        } else {
          sourceRow.append(textElement('span', 'chat-source-mini', `p. ${page}`));
        }
      });
      message.append(sourceRow);
    } else if (role === 'assistant' && mode) {
      message.append(textElement('div', 'chat-message-meta', mode));
    }
    chatMessages.append(message);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    if (!restoringChat) {
      chatLog.push({ role, text, sources, mode });
      persistChat();
    }
    return message;
  }

  function setPaper(paper, chunkCount = null) {
    activePaper = paper;
    setAlert('');
    setPaperSectionsEnabled(true);
    setActiveSection('brief');
    emptyState.hidden = true;
    resultsPanel.hidden = false;
    $('#paperTitle').textContent = paper.title || 'Untitled paper';
    $('#paperFilename').textContent = paper.filename || 'paper.pdf';
    $('#paperPageCount').textContent = paper.page_count || '—';
    $('#paperChunkCount').textContent = chunkCount || '—';
    renderSummary(paper.summary || {});
    updateChatContext(paper);
    restoreChat(paper);
    chatInput.disabled = false;
    sendButton.disabled = false;
    document.querySelectorAll('.suggestion-chip[data-question]').forEach((button) => { button.disabled = false; });
    loadLibrary();
  }

  function renderLibrary(papers) {
    const library = $('#libraryList');
    library.replaceChildren();
    $('#libraryCount').textContent = String(papers.length);
    if (!papers.length) {
      library.append(textElement('div', 'library-empty', 'Papers you upload will appear here.'));
      return;
    }
    papers.forEach((paper) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = `library-item${activePaper && activePaper.id === paper.id ? ' active' : ''}`;
      item.setAttribute('aria-label', `Open ${paper.title || paper.filename}`);
      item.append(textElement('span', 'library-pdf', 'PDF'));
      const copy = document.createElement('span');
      copy.className = 'library-item-copy';
      copy.append(textElement('span', 'library-item-title', paper.title || paper.filename));
      copy.append(textElement('span', 'library-item-meta', `${paper.page_count || 0} pages · ${paper.filename || 'paper.pdf'}`));
      item.append(copy);
      if (activePaper && activePaper.id === paper.id) item.append(textElement('span', 'library-item-check', '✓'));
      item.addEventListener('click', () => selectPaper(paper.id));
      library.append(item);
    });
  }

  async function loadLibrary() {
    try {
      const payload = await api('/api/papers');
      renderLibrary(payload.papers || []);
    } catch (error) {
      console.warn('Could not load paper library:', error.message);
    }
  }

  async function selectPaper(paperId) {
    try {
      const payload = await api(`/api/papers/${encodeURIComponent(paperId)}`);
      chatMessages.replaceChildren();
      if (assistantWelcome) chatMessages.append(assistantWelcome);
      activePaper = null;
      setPaper(payload.paper);
      resultsPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      showToast(error.message);
    }
  }

  function setUploading(isUploading) {
    uploadInProgress = isUploading;
    browseButton.disabled = isUploading;
    uploadProgress.hidden = !isUploading;
    if (isUploading) {
      uploadProgressBar.style.width = '12%';
      uploadProgressLabel.textContent = 'Reading pages and indexing passages…';
      let progress = 12;
      window.clearInterval(uploadTimer);
      uploadTimer = window.setInterval(() => {
        progress = Math.min(progress + 7, 88);
        uploadProgressBar.style.width = `${progress}%`;
        if (progress > 65) uploadProgressLabel.textContent = 'Preparing your evidence-grounded brief…';
      }, 520);
    } else {
      window.clearInterval(uploadTimer);
      uploadProgressBar.style.width = '100%';
      window.setTimeout(() => { uploadProgressBar.style.width = '8%'; }, 450);
    }
  }

  async function uploadFile(file) {
    if (!file || uploadInProgress) return;
    setAlert('');
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setAlert('Please select a PDF file.');
      return;
    }
    if (file.size > maxUploadMb * 1024 * 1024) {
      setAlert(`This PDF is larger than ${maxUploadMb} MB. Choose a smaller file.`);
      return;
    }
    const formData = new FormData();
    formData.append('pdf', file);
    setUploading(true);
    try {
      const payload = await api('/api/upload', { method: 'POST', body: formData, timeoutMs: 300000 });
      chatMessages.replaceChildren();
      setPaper(payload.paper, payload.chunk_count);
      const mode = payload.summary && payload.summary.mode ? payload.summary.mode : 'processed';
      const extras = [];
      if (payload.table_chunks) extras.push(`${payload.table_chunks} table${payload.table_chunks === 1 ? '' : 's'}`);
      if (payload.ocr_pages) extras.push(`${payload.ocr_pages} OCR page${payload.ocr_pages === 1 ? '' : 's'}`);
      const extraText = extras.length ? ` · ${extras.join(' · ')}` : '';
      setAlert(`Ready: ${payload.paper.title} · ${payload.chunk_count} passages indexed${extraText} · ${mode}.`, 'success');
      $('#footerStatus').textContent = `${payload.chunk_count} passages indexed`;
      showToast('Research brief is ready.');
      resultsPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      setAlert(error.message);
    } finally {
      setUploading(false);
      pdfInput.value = '';
    }
  }

  function answerDetail() {
    const select = $('#answerDetail');
    const value = select ? select.value : 'balanced';
    try { localStorage.setItem('dqAnswerDetail', value); } catch (error) { /* storage may be blocked */ }
    return value;
  }

  function restoreAnswerDetail() {
    const select = $('#answerDetail');
    if (!select) return;
    try {
      const saved = localStorage.getItem('dqAnswerDetail');
      if (saved && select.querySelector(`option[value="${saved}"]`)) select.value = saved;
    } catch (error) { /* ignore */ }
  }

  function showTyping() {
    const wrapper = document.createElement('div');
    wrapper.className = 'chat-message assistant';
    wrapper.id = 'typingIndicator';
    const dots = document.createElement('div');
    dots.className = 'chat-bubble typing-dots';
    for (let i = 0; i < 3; i += 1) dots.append(document.createElement('span'));
    wrapper.append(dots);
    chatMessages.append(wrapper);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  async function sendQuestion(question) {
    const cleanQuestion = String(question || '').trim();
    if (!cleanQuestion || !activePaper) return;
    const epoch = chatEpoch;
    addMessage('user', cleanQuestion);
    chatInput.value = '';
    sendButton.disabled = true;
    document.querySelectorAll('.suggestion-chip[data-question]').forEach((button) => { button.disabled = true; });
    showTyping();
    try {
      const payload = await api(`/api/papers/${encodeURIComponent(activePaper.id)}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: cleanQuestion, detail: answerDetail() }),
        timeoutMs: 300000,
      });
      $('#typingIndicator')?.remove();
      if (epoch !== chatEpoch) return; // chat was cleared while the answer was loading
      addMessage('assistant', payload.answer || 'No answer was returned.', payload.sources || [], payload.mode || '');
    } catch (error) {
      $('#typingIndicator')?.remove();
      if (epoch !== chatEpoch) return;
      addMessage('assistant', `I couldn't complete that request: ${error.message}`);
    } finally {
      sendButton.disabled = !activePaper;
      document.querySelectorAll('.suggestion-chip').forEach((button) => { button.disabled = !activePaper; });
      chatInput.focus();
    }
  }

  async function deleteActivePaper() {
    if (!activePaper) return;
    const paperToDelete = activePaper;
    try {
      await api(`/api/papers/${encodeURIComponent(paperToDelete.id)}`, { method: 'DELETE' });
      activePaper = null;
      setPaperSectionsEnabled(false);
      setActiveSection('upload');
      resultsPanel.hidden = true;
      emptyState.hidden = false;
      chatMessages.replaceChildren();
      chatMessages.append(assistantWelcome);
      chatInput.disabled = true;
      sendButton.disabled = true;
      updateChatContext(null);
      $('#footerStatus').textContent = 'Ready when you are';
      await refreshModelChip();
      await loadLibrary();
      showToast('Paper removed from this session.');
      $('#dropZone').scrollIntoView({ behavior: 'smooth', block: 'center' });
    } catch (error) {
      showToast(error.message);
    }
  }

  browseButton.addEventListener('click', () => pdfInput.click());

  // Clear the chat conversation (keeps the paper + its brief, only wipes messages).
  const clearChatButton = $('#clearChatButton');
  if (clearChatButton) {
    clearChatButton.addEventListener('click', () => {
      chatEpoch += 1;
      $('#typingIndicator')?.remove();
      chatMessages.replaceChildren();
      chatLog = [];
      if (activePaper) {
        try { localStorage.removeItem(`dqChat:${activePaper.id}`); } catch (error) { /* ignore */ }
      }
      if (assistantWelcome) chatMessages.append(assistantWelcome);
      document.querySelectorAll('.suggestion-chip[data-question]').forEach((button) => {
        button.disabled = !activePaper;
      });
      sendButton.disabled = !activePaper;
      showToast(activePaper ? 'Chat history cleared.' : 'Chat is already empty.');
    });
  }
  pdfInput.addEventListener('change', (event) => uploadFile(event.target.files[0]));
  dropZone.addEventListener('dragover', (event) => { event.preventDefault(); dropZone.classList.add('is-dragging'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('is-dragging'));
  dropZone.addEventListener('drop', (event) => {
    event.preventDefault();
    dropZone.classList.remove('is-dragging');
    uploadFile(event.dataTransfer.files[0]);
  });
  chatForm.addEventListener('submit', (event) => { event.preventDefault(); sendQuestion(chatInput.value); });
  if (window.DQAuth && window.DQAuth.bindForm) {
    window.DQAuth.bindForm('#chatForm', '#sendButton', ['#chatInput']);
  }
  const modelChip = $('#modelChip');
  if (modelChip) {
    modelChip.addEventListener('click', (event) => {
      event.stopPropagation();
      const menu = $('#modelMenu');
      if (!menu) return;
      const open = menu.hidden;
      menu.hidden = !open;
      modelChip.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('click', (event) => {
      const menu = $('#modelMenu');
      if (!menu || menu.hidden) return;
      if (!menu.contains(event.target) && event.target !== modelChip) {
        menu.hidden = true;
        modelChip.setAttribute('aria-expanded', 'false');
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        const menu = $('#modelMenu');
        if (menu && !menu.hidden) {
          menu.hidden = true;
          modelChip.setAttribute('aria-expanded', 'false');
        }
      }
    });
  }

  const moreToggle = $('#moreQuestionsToggle');
  if (moreToggle) {
    moreToggle.addEventListener('click', () => {
      const extra = $('#moreQuestionChips');
      if (!extra) return;
      const open = extra.hidden;
      extra.hidden = !open;
      moreToggle.setAttribute('aria-expanded', String(open));
      moreToggle.textContent = open ? 'Show less' : '+ 6 more';
    });
  }
  document.querySelectorAll('.suggestion-chip[data-question]').forEach((button) => {
    button.disabled = true;
    button.addEventListener('click', () => sendQuestion(button.dataset.question));
  });
  $('#deletePaperButton').addEventListener('click', deleteActivePaper);
  const logoutButton = $('#logoutButton');
  if (logoutButton) {
    logoutButton.addEventListener('click', async () => {
      try { await api('/api/logout', { method: 'POST' }); } catch { /* ignore */ }
      if (window.DQAuth) window.DQAuth.clearToken();
      window.location.href = '/';
    });
  }
  sectionLinks.forEach((link) => {
    link.addEventListener('click', (event) => {
      if (link.getAttribute('aria-disabled') === 'true') {
        event.preventDefault();
        setActiveSection('upload');
        setAlert('Upload a PDF or open one from your Paper Library to use this section.');
        dropZone.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
      }
      setActiveSection(link.dataset.section);
      if (link.dataset.section === 'upload') setAlert('');
    });
  });

  /* ---- model chip: show which local model is answering, and switch it ---- */

  function shortModelName(label) {
    return String(label || 'Local model')
      .replace(/Qwen2\.5\s*/i, 'Qwen2.5 ')
      .replace(/\s*Instruct/i, '')
      .replace(/\s*GGUF/i, '')
      .replace(/\s*\(not loaded\)/i, '')
      .trim()
      .slice(0, 26);
  }

  function renderModelMenu(payload) {
    const menu = $('#modelMenu');
    if (!menu) return;
    menu.replaceChildren();
    const options = payload.options || [];
    const presets = options.filter((option) => option.kind === 'preset');
    const files = options.filter((option) => option.kind !== 'preset');
    const addGroup = (title, items) => {
      if (!items.length) return;
      menu.append(textElement('div', 'model-menu-title', title));
      items.forEach((option) => {
        const isCurrent = option.id === payload.selected_id;
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'model-menu-item' + (isCurrent ? ' is-current' : '');
        item.dataset.modelId = option.id;
        item.setAttribute('role', 'option');
        item.setAttribute('aria-selected', String(Boolean(isCurrent)));
        const top = document.createElement('span');
        top.className = 'model-menu-name';
        top.textContent = option.label || option.id;
        const meta = document.createElement('span');
        meta.className = 'model-menu-meta';
        const bits = [];
        if (option.size_mb) bits.push(`${option.size_mb} MB`);
        if (option.source && option.kind !== 'preset') bits.push(option.source);
        if (option.kind === 'preset') bits.push(option.downloaded ? 'downloaded' : 'needs download');
        if (isCurrent) bits.push('in use');
        meta.textContent = bits.join(' · ');
        item.append(top, meta);
        item.addEventListener('click', () => selectModel(option, item));
        menu.append(item);
      });
    };
    addGroup('Recommended presets', presets);
    addGroup('GGUF files on this laptop', files);
    const foot = document.createElement('a');
    foot.className = 'model-menu-foot';
    foot.href = '/profile';
    foot.textContent = 'Add or download more models →';
    menu.append(foot);
  }

  async function selectModel(option, item) {
    const menu = $('#modelMenu');
    item.disabled = true;
    try {
      const result = await api('/api/models/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: option.id }),
      });
      $('#modelChipLabel').textContent = shortModelName(option.label || option.id);
      showToast(result.message || 'Model saved.');
      if (result.managed) {
        window.setTimeout(refreshModelChip, 6000);
      }
    } catch (error) {
      showToast(error.message);
    } finally {
      item.disabled = false;
      if (menu) menu.hidden = true;
      const chip = $('#modelChip');
      if (chip) chip.setAttribute('aria-expanded', 'false');
    }
  }

  async function refreshModelChip() {
    try {
      const payload = await api('/api/models');
      const options = payload.options || [];
      const current = options.find((option) => option.id === payload.selected_id);
      const label = (current && current.label) || (payload.current && payload.current.model) || 'Local model';
      const running = Boolean(payload.current && payload.current.available);
      const chipLabel = $('#modelChipLabel');
      const chipSub = $('#modelChipSub');
      const dot = $('#modelChipDot');
      if (chipLabel) chipLabel.textContent = shortModelName(label);
      if (chipSub) {
        chipSub.textContent = running ? 'running · offline' : 'not loaded · start.bat';
      }
      if (dot) dot.dataset.state = running ? 'on' : 'off';
      const chip = $('#modelChip');
      if (chip) chip.title = running
        ? `${label} is answering your questions`
        : `${label} is selected but not running yet — start it with start.bat`;
      renderModelMenu(payload);
    } catch (error) {
      const chipLabel = $('#modelChipLabel');
      if (chipLabel) chipLabel.textContent = 'Model unavailable';
    }
  }

  async function initialize() {
    setPaperSectionsEnabled(false);
    try {
      const health = await api('/api/health');
      maxUploadMb = Number(health.max_upload_mb) || 20;
      $('#connectionPill').dataset.mode = 'local';
      $('#connectionLabel').textContent = 'Local SQLite';
      $('#footerStatus').textContent = health.llm_available
        ? `${health.llm_label || 'Local model'} ready · ${health.llm_model || 'default model'}`
        : 'Preview mode · no local model is running';
      const notice = $('#modelNotice');
      const noticeText = $('#modelNoticeText');
      if (notice && noticeText && !health.llm_available) {
        const missing = [];
        if (health.ocr_available === false) missing.push('OCR add-on');
        if (health.tables_available === false) missing.push('table reader');
        noticeText.innerHTML = '<strong>Local model is not running yet.</strong> '
          + 'Answers will be exact quotes from the PDF instead of written text. '
          + 'Start it with <code>start.bat</code> (or <code>python local_ai.py</code>).'
          + (missing.length ? ` Optional extras not installed: ${missing.join(', ')}.` : '');
        notice.hidden = false;
      } else if (notice) {
        notice.hidden = true;
      }
      await refreshModelChip();
      await loadLibrary();
    } catch (error) {
      $('#connectionPill').dataset.mode = 'offline';
      $('#connectionLabel').textContent = 'Server unavailable';
      setAlert(error.message);
    }
  }

  restoreAnswerDetail();
  initialize();
})();
