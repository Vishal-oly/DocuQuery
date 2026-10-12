(() => {
  const $ = (selector) => document.querySelector(selector);

  const summaryFields = [
    ['overall_summary', 'Overview', '✦', true],
    ['objective', 'Research objective', '◎'],
    ['methodology', 'Methodology', '⌘'],
    ['dataset', 'Data & materials', '▤'],
    ['key_findings', 'Key findings', '↗'],
    ['limitations', 'Limitations', '△'],
    ['conclusion', 'Conclusion', '◌'],
  ];

  let papers = [];
  let activePaper = null;
  let toastTimer = null;

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
    try { payload = await response.json(); } catch { payload = {}; }
    if (response.status === 401) {
      if (window.DQAuth) window.DQAuth.clearToken();
      window.location.href = '/login';
      throw new Error('Please sign in to continue.');
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

  function formatSize(bytes) {
    const value = Number(bytes) || 0;
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }

  function renderList() {
    const list = $('#summaryPaperList');
    list.replaceChildren();
    $('#libraryCount').textContent = String(papers.length);
    if (!papers.length) {
      list.append(textElement('div', 'library-empty', 'Upload a paper in the workspace to see summaries here.'));
      return;
    }
    papers.forEach((paper) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = `library-item${activePaper && activePaper.id === paper.id ? ' active' : ''}`;
      item.append(textElement('span', 'library-pdf', 'PDF'));
      const copy = document.createElement('span');
      copy.className = 'library-item-copy';
      copy.append(textElement('span', 'library-item-title', paper.title || paper.filename));
      copy.append(textElement('span', 'library-item-meta', `${paper.page_count || 0} pages · ${paper.filename || 'paper.pdf'}`));
      item.append(copy);
      if (activePaper && activePaper.id === paper.id) item.append(textElement('span', 'library-item-check', '✓'));
      item.addEventListener('click', () => selectPaper(paper.id));
      list.append(item);
    });
  }

  function renderSources(sources) {
    const list = $('#detailSources');
    list.replaceChildren();
    $('#detailSourcesCount').textContent = `${sources.length} passage${sources.length === 1 ? '' : 's'}`;
    if (!sources.length) {
      list.append(textElement('div', 'no-sources', 'No source passages were attached to this summary.'));
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

  function renderSummary(summary = {}) {
    const grid = $('#detailSummaryGrid');
    grid.replaceChildren();
    summaryFields.forEach(([field, label, icon, wide]) => {
      const card = document.createElement('article');
      card.className = `summary-card${wide ? ' summary-card-wide' : ''}`;
      const header = document.createElement('div');
      header.className = 'summary-card-top';
      header.append(textElement('span', 'summary-card-icon', icon));
      header.append(textElement('span', 'summary-card-title', label));
      const body = textElement('p', '', summary[field] || 'Not clearly stated in the retrieved text.');
      card.append(header, body);
      grid.append(card);
    });
    $('#detailMode').textContent = summary.mode || 'Research brief';
    const notice = $('#detailNotice');
    notice.textContent = summary.notice || '';
    notice.hidden = !summary.notice;
    renderSources(summary.sources || []);
  }

  function turl(url) {
    return window.DQAuth ? window.DQAuth.withToken(url) : url;
  }

  function setPaper(paper) {
    activePaper = paper;
    $('#summaryEmpty').hidden = true;
    $('#summaryDetail').hidden = false;
    $('#detailTitle').textContent = paper.title || 'Untitled paper';
    $('#detailFilename').textContent = paper.filename || 'paper.pdf';
    $('#detailPages').textContent = paper.page_count || '—';
    $('#detailSize').textContent = paper.file_size ? formatSize(paper.file_size) : 'file not stored';

    const viewDoc = $('#viewDocButton');
    if (paper.has_file) {
      viewDoc.href = turl(`/api/papers/${encodeURIComponent(paper.id)}/file`);
      viewDoc.classList.remove('disabled');
      viewDoc.removeAttribute('aria-disabled');
    } else {
      viewDoc.href = '#';
      viewDoc.classList.add('disabled');
      viewDoc.setAttribute('aria-disabled', 'true');
    }

    const base = `/api/papers/${encodeURIComponent(paper.id)}/download`;
    $('#downloadMd').href = turl(`${base}?format=md`);
    $('#downloadTxt').href = turl(`${base}?format=txt`);
    $('#downloadJson').href = turl(`${base}?format=json`);

    renderSummary(paper.summary || {});
    renderList();
  }

  async function selectPaper(paperId) {
    try {
      const payload = await api(`/api/papers/${encodeURIComponent(paperId)}`);
      setPaper(payload.paper);
    } catch (error) {
      showToast(error.message);
    }
  }

  async function loadPapers() {
    try {
      const payload = await api('/api/papers');
      papers = payload.papers || [];
      renderList();
      const params = new URLSearchParams(window.location.search);
      const wanted = params.get('paper');
      if (wanted && papers.some((paper) => paper.id === wanted)) {
        await selectPaper(wanted);
      }
    } catch (error) {
      showToast(error.message);
    }
  }

  $('#downloadButton').addEventListener('click', () => {
    const options = $('#downloadOptions');
    options.hidden = !options.hidden;
  });
  document.addEventListener('click', (event) => {
    const menu = document.querySelector('.download-menu');
    if (menu && !menu.contains(event.target)) $('#downloadOptions').hidden = true;
  });

  $('#viewDocButton').addEventListener('click', (event) => {
    if (!activePaper || !activePaper.has_file) {
      event.preventDefault();
      showToast('The original PDF is not stored for this paper.');
    }
  });

  $('#regenButton').addEventListener('click', async () => {
    if (!activePaper) return;
    const button = $('#regenButton');
    button.disabled = true;
    button.textContent = 'Generating…';
    try {
      const payload = await api(`/api/papers/${encodeURIComponent(activePaper.id)}/summarize`, { method: 'POST' });
      activePaper = payload.paper;
      renderSummary(payload.summary || {});
      showToast('Research brief regenerated.');
    } catch (error) {
      showToast(error.message);
    } finally {
      button.disabled = false;
      button.textContent = 'Get summary';
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

  loadPapers();
})();
