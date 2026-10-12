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

  function addMessage(role, text, sources = [], mode = '') {
    if (assistantWelcome && assistantWelcome.isConnected) assistantWelcome.remove();
    const message = document.createElement('div');
    message.className = `chat-message ${role}`;
    message.append(textElement('div', 'chat-bubble', text));
    if (role === 'assistant' && sources.length) {
      const sourceRow = document.createElement('div');
      sourceRow.className = 'chat-message-meta';
      sourceRow.textContent = 'Evidence: ';
      sources.slice(0, 4).forEach((source) => {
        sourceRow.append(textElement('span', 'chat-source-mini', `p. ${source.page_number || 1}`));
      });
      message.append(sourceRow);
    } else if (role === 'assistant' && mode) {
      message.append(textElement('div', 'chat-message-meta', mode));
    }
    chatMessages.append(message);
    chatMessages.scrollTop = chatMessages.scrollHeight;
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
    chatInput.disabled = false;
    sendButton.disabled = false;
    document.querySelectorAll('.suggestion-chip').forEach((button) => { button.disabled = false; });
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
      const payload = await api('/api/upload', { method: 'POST', body: formData });
      chatMessages.replaceChildren();
      setPaper(payload.paper, payload.chunk_count);
      const mode = payload.summary && payload.summary.mode ? payload.summary.mode : 'processed';
      setAlert(`Ready: ${payload.paper.title} · ${payload.chunk_count} passages indexed · ${mode}.`, 'success');
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
    addMessage('user', cleanQuestion);
    chatInput.value = '';
    sendButton.disabled = true;
    document.querySelectorAll('.suggestion-chip').forEach((button) => { button.disabled = true; });
    showTyping();
    try {
      const payload = await api(`/api/papers/${encodeURIComponent(activePaper.id)}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: cleanQuestion }),
      });
      $('#typingIndicator')?.remove();
      addMessage('assistant', payload.answer || 'No answer was returned.', payload.sources || [], payload.mode || '');
    } catch (error) {
      $('#typingIndicator')?.remove();
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
      await loadLibrary();
      showToast('Paper removed from this session.');
      $('#dropZone').scrollIntoView({ behavior: 'smooth', block: 'center' });
    } catch (error) {
      showToast(error.message);
    }
  }

  browseButton.addEventListener('click', () => pdfInput.click());
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
  document.querySelectorAll('.suggestion-chip').forEach((button) => {
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

  async function initialize() {
    setPaperSectionsEnabled(false);
    try {
      const health = await api('/api/health');
      maxUploadMb = Number(health.max_upload_mb) || 20;
      const isSupabase = health.database === 'Supabase pgvector';
      $('#connectionPill').dataset.mode = isSupabase ? 'supabase' : 'local';
      $('#connectionLabel').textContent = isSupabase ? 'Supabase connected' : 'Local demo mode';
      $('#footerStatus').textContent = health.llm_available ? `Groq ready · ${health.llm_model}` : 'Preview mode · add a Groq key for generated answers';
      await loadLibrary();
    } catch (error) {
      $('#connectionPill').dataset.mode = 'offline';
      $('#connectionLabel').textContent = 'Server unavailable';
      setAlert(error.message);
    }
  }

  initialize();
})();
