(() => {
  const $ = (selector) => document.querySelector(selector);

  // ------------------------------------------------------------------
  // Landing page: logout link (when already signed in)
  // ------------------------------------------------------------------
  const landingLogout = $('#landingLogout');
  if (landingLogout) {
    landingLogout.addEventListener('click', async (event) => {
      event.preventDefault();
      try { await fetch('/api/logout', { method: 'POST' }); } catch { /* ignore */ }
      if (window.DQAuth) window.DQAuth.clearToken();
      window.location.reload();
    });
  }

  // ------------------------------------------------------------------
  // Forgot-password page (two-step: request code → reset password)
  // ------------------------------------------------------------------
  const forgotForm = $('#forgotForm');
  if (forgotForm) {
    const resetForm = $('#resetForm');
    const authAlertBox = $('#authAlert');
    const resetCodePanel = $('#resetCodePanel');

    function showAlert(message, kind = 'error') {
      authAlertBox.textContent = message;
      authAlertBox.classList.toggle('success', kind === 'success');
      authAlertBox.hidden = !message;
    }
    function busy(button, isBusy) {
      button.disabled = isBusy;
      button.querySelector('.submit-busy').hidden = !isBusy;
      button.querySelector('.submit-label').hidden = isBusy;
    }

    forgotForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const email = $('#emailInput').value.trim();
      const emailError = $('#emailError');
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
        $('#emailInput').classList.add('invalid');
        emailError.textContent = 'Enter a valid email address.';
        emailError.hidden = false;
        return;
      }
      $('#emailInput').classList.remove('invalid');
      emailError.hidden = true;

      const button = $('#requestCodeButton');
      busy(button, true);
      try {
        const response = await fetch('/api/forgot', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          showAlert(payload.error || `Request failed (${response.status}).`);
          return;
        }
        showAlert(payload.notice || 'Reset code generated.', 'success');
        if (payload.reset_token) {
          $('#resetTokenValue').textContent = payload.reset_token;
          resetCodePanel.hidden = false;
          $('#tokenInput').value = payload.reset_token;
        }
        resetForm.hidden = false;
      } catch (error) {
        showAlert(`Could not reach the server: ${error.message}`);
      } finally {
        busy(button, false);
      }
    });

    resetForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const token = $('#tokenInput').value.trim();
      const newPassword = $('#newPasswordInput').value;
      let ok = true;
      if (!token) {
        $('#tokenInput').classList.add('invalid');
        $('#tokenError').textContent = 'Enter the reset code.';
        $('#tokenError').hidden = false;
        ok = false;
      }
      if (newPassword.length < 6) {
        $('#newPasswordInput').classList.add('invalid');
        $('#newPasswordError').textContent = 'New password must be at least 6 characters.';
        $('#newPasswordError').hidden = false;
        ok = false;
      }
      if (!ok) return;

      const button = $('#resetButton');
      busy(button, true);
      try {
        const response = await fetch('/api/reset', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token, new_password: newPassword }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          showAlert(payload.error || `Request failed (${response.status}).`);
          return;
        }
        showAlert('Password reset successful. Redirecting to login…', 'success');
        window.setTimeout(() => { window.location.href = '/login'; }, 900);
      } catch (error) {
        showAlert(`Could not reach the server: ${error.message}`);
      } finally {
        busy(button, false);
      }
    });

    if (window.DQAuth && window.DQAuth.bindForm) {
      window.DQAuth.bindForm('#forgotForm', '#requestCodeButton', ['#emailInput']);
      window.DQAuth.bindForm('#resetForm', '#resetButton', ['#tokenInput', '#newPasswordInput']);
    }
    return;
  }

  // ------------------------------------------------------------------
  // Login / register page
  // ------------------------------------------------------------------
  const authForm = $('#authForm');
  if (!authForm) return;

  const state = {
    mode: 'login',
    busy: false,
  };

  const nameField = $('#nameField');
  const nameInput = $('#nameInput');
  const emailInput = $('#emailInput');
  const passwordInput = $('#passwordInput');
  const authAlert = $('#authAlert');
  const authTitle = $('#authTitle');
  const authSubtitle = $('#authSubtitle');
  const authSubmit = $('#authSubmit');
  const authSwitch = $('#authSwitch');

  const toast = $('#toast');
  let toastTimer = null;
  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => { toast.hidden = true; }, 3600);
  }

  function setAlert(message, kind = 'error') {
    authAlert.textContent = message;
    authAlert.classList.toggle('success', kind === 'success');
    authAlert.hidden = !message;
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

  function setMode(mode) {
    state.mode = mode === 'register' ? 'register' : 'login';
    const isRegister = state.mode === 'register';

    $('#tabLogin').classList.toggle('active', !isRegister);
    $('#tabRegister').classList.toggle('active', isRegister);
    $('#tabLogin').setAttribute('aria-selected', String(!isRegister));
    $('#tabRegister').setAttribute('aria-selected', String(isRegister));

    nameField.hidden = !isRegister;
    passwordInput.setAttribute('autocomplete', isRegister ? 'new-password' : 'current-password');
    authTitle.textContent = isRegister ? 'Create your account' : 'Login to DocuQuery';
    authSubtitle.textContent = isRegister
      ? 'Create a free account to save your papers and research briefs.'
      : 'Enter your credentials to continue to your workspace.';
    authSubmit.querySelector('.submit-label').textContent = isRegister ? 'Create account' : 'Login';
    authSwitch.innerHTML = isRegister
      ? 'Already have an account? <a href="#" id="switchToLogin">Sign in</a>'
      : 'New to DocuQuery? <a href="#" id="switchToRegister">Create an account</a>';
    bindSwitchLinks();
    setAlert('');
    setFieldError(nameInput, 'nameError', '');
    setFieldError(emailInput, 'emailError', '');
    setFieldError(passwordInput, 'passwordError', '');
  }

  function bindSwitchLinks() {
    const toRegister = $('#switchToRegister');
    const toLogin = $('#switchToLogin');
    if (toRegister) toRegister.addEventListener('click', (event) => { event.preventDefault(); setMode('register'); });
    if (toLogin) toLogin.addEventListener('click', (event) => { event.preventDefault(); setMode('login'); });
  }

  $('#tabLogin').addEventListener('click', () => setMode('login'));
  $('#tabRegister').addEventListener('click', () => setMode('register'));
  bindSwitchLinks();

  const forgotLink = $('#forgotLink');
  if (forgotLink) {
    forgotLink.addEventListener('click', (event) => {
      event.preventDefault();
      window.location.href = '/forgot';
    });
  }

  function validate() {
    let ok = true;
    if (state.mode === 'register') {
      const name = nameInput.value.trim();
      if (name.length < 2 || name.length > 60) {
        setFieldError(nameInput, 'nameError', 'Enter your name (2-60 characters).');
        ok = false;
      } else setFieldError(nameInput, 'nameError', '');
    }
    const email = emailInput.value.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setFieldError(emailInput, 'emailError', 'Enter a valid email address.');
      ok = false;
    } else setFieldError(emailInput, 'emailError', '');

    const password = passwordInput.value;
    if (password.length < 6) {
      setFieldError(passwordInput, 'passwordError', 'Password must be at least 6 characters.');
      ok = false;
    } else setFieldError(passwordInput, 'passwordError', '');

    return ok;
  }

  function setBusy(busy) {
    state.busy = busy;
    authSubmit.disabled = busy;
    authSubmit.querySelector('.submit-busy').hidden = !busy;
    authSubmit.querySelector('.submit-label').hidden = busy;
  }

  authForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (state.busy) return;
    setAlert('');
    if (!validate()) return;

    setBusy(true);
    try {
      const body = {
        email: emailInput.value.trim(),
        password: passwordInput.value,
      };
      if (state.mode === 'register') body.name = nameInput.value.trim();

      const endpoint = state.mode === 'register' ? '/api/register' : '/api/login';
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      let payload = {};
      try { payload = await response.json(); } catch { /* ignore */ }

      if (!response.ok) {
        setAlert(payload.error || `Request failed (${response.status}).`);
        return;
      }

      if (payload.token && window.DQAuth) window.DQAuth.setToken(payload.token);
      setAlert(state.mode === 'register' ? 'Account created. Opening your workspace…' : 'Login successful. Opening your workspace…', 'success');
      const next = (window.DOCUQUERY_AUTH && window.DOCUQUERY_AUTH.next) || '';
      const target = next && next.startsWith('/') ? next : '/workspace';
      window.setTimeout(() => {
        window.location.href = window.DQAuth ? window.DQAuth.withToken(target) : target;
      }, 350);
    } catch (error) {
      setAlert(`Could not reach the server: ${error.message}`);
    } finally {
      setBusy(false);
    }
  });

  // Initial mode from the query string (?mode=register).
  const initialMode = (window.DOCUQUERY_AUTH && window.DOCUQUERY_AUTH.mode) || 'login';
  setMode(initialMode);

  // Buttons/Enter keys work even where native form submission is blocked (sandboxed iframes).
  if (window.DQAuth && window.DQAuth.bindForm) {
    window.DQAuth.bindForm('#authForm', '#authSubmit', ['#nameInput', '#emailInput', '#passwordInput']);
  }
})();
