// Sesión con Firebase Auth en el navegador. Mantiene la cookie pb_token
// con un token válido para que el servidor Python sepa quién eres.
const page = document.body.dataset.page;          // app | login | wait | logout
const DEV = document.body.dataset.dev === '1';
const SECURE = location.protocol === 'https:' ? '; secure' : '';
const setTok = tok => { document.cookie = 'pb_token=' + tok + '; path=/; max-age=3600; samesite=lax' + SECURE };
const clearTok = () => { document.cookie = 'pb_token=; path=/; max-age=0; samesite=lax' + SECURE };

if (DEV) {
  window.pbFresh = async () => {};
  if (page === 'login') document.getElementById('dev-in').onclick = () => { setTok('dev'); location.href = '/' };
  if (page === 'logout') { clearTok(); location.href = '/login' }
  if (page === 'wait') location.href = '/login';
} else {
  const B = 'https://www.gstatic.com/firebasejs/10.12.2/';
  const [{ initializeApp }, A] = await Promise.all([import(B + 'firebase-app.js'), import(B + 'firebase-auth.js')]);
  const app = initializeApp(JSON.parse(document.body.dataset.fb));
  const auth = A.getAuth(app);
  const tr = JSON.parse(document.getElementById('i18n')?.textContent || '{}');

  // Antes de enviar un formulario, asegurar que el token no ha caducado
  window.pbFresh = async () => { const u = auth.currentUser; if (u) setTok(await u.getIdToken()) };
  window.pbCall = async (name, data) => { const F = await import(B + 'firebase-functions.js'); return (await F.httpsCallable(F.getFunctions(app, 'europe-west1'), name)(data || {})).data };
  document.addEventListener('submit', async e => {
    const f = e.target; if (f.dataset.fresh === '1' || f.method === 'dialog' || page !== 'app' || (f.dataset.confirm && !f.dataset.ok)) return;
    e.preventDefault(); try { await window.pbFresh() } catch (x) {} f.dataset.fresh = '1'; f.requestSubmit ? f.requestSubmit(e.submitter) : f.submit();
  }, true);

  A.onIdTokenChanged(auth, async u => {
    if (u) {
      setTok(await u.getIdToken());
      if (page === 'login') location.href = '/';
      if (page === 'wait') {
        const n = +(sessionStorage.getItem('pb-wait') || 0);
        if (n < 3) { sessionStorage.setItem('pb-wait', n + 1); setTok(await u.getIdToken(true)); location.reload() }
        else { sessionStorage.removeItem('pb-wait'); sessionStorage.setItem('pb-why', document.body.dataset.why || 'token'); await A.signOut(auth) }
      } else sessionStorage.removeItem('pb-wait');
    } else {
      clearTok();
      if (page === 'app' || page === 'wait') location.href = '/login';
      if (page === 'logout') location.href = '/login';
    }
  });
  if (page === 'logout') A.signOut(auth);

  if (page === 'login') {
    const $ = s => document.querySelector(s), err = $('#auth-err');
    const why = sessionStorage.getItem('pb-why'); if (why) { sessionStorage.removeItem('pb-why'); err.textContent = (tr.w_session || '') + ' (' + why + ')' }
    let mode = 'login';
    const E = c => ({ 'auth/invalid-credential': 'e_invalid', 'auth/wrong-password': 'e_invalid', 'auth/user-not-found': 'e_invalid', 'auth/invalid-email': 'e_email', 'auth/email-already-in-use': 'e_exists', 'auth/weak-password': 'e_weak', 'auth/network-request-failed': 'e_net', 'auth/too-many-requests': 'e_many', 'auth/popup-closed-by-user': 'e_popup', 'auth/popup-blocked': 'e_popup', 'auth/unauthorized-domain': 'e_domain' }[c] || 'e_generic');
    const showErr = k => { err.textContent = tr[k] || k; err.className = 'err' };
    const setMode = m => {
      mode = m; $('#seg-login').classList.toggle('on', m === 'login'); $('#seg-reg').classList.toggle('on', m === 'reg');
      $('#a-name-wrap').classList.toggle('hidden', m === 'login'); $('#a-hint').classList.toggle('hidden', m === 'login');
      $('#a-submit').textContent = tr[m === 'login' ? 'a_submit_login' : 'a_submit_reg']; err.textContent = '';
    };
    $('#seg-login').onclick = () => setMode('login'); $('#seg-reg').onclick = () => setMode('reg'); { const m = err.textContent; setMode('login'); err.textContent = m }
    $('#auth-form').onsubmit = async e => {
      e.preventDefault(); err.textContent = '';
      const email = $('#a-email').value.trim(), pass = $('#a-pass').value, name = $('#a-name').value.trim();
      await A.setPersistence(auth, $('#a-remember').checked ? A.browserLocalPersistence : A.browserSessionPersistence);
      try {
        if (mode === 'reg') {
          if (!name) return showErr('e_name');
          const c = await A.createUserWithEmailAndPassword(auth, email, pass);
          try { await A.updateProfile(c.user, { displayName: name }); await A.sendEmailVerification(c.user) } catch (x) {}
          setTok(await c.user.getIdToken(true));
        } else await A.signInWithEmailAndPassword(auth, email, pass);
      } catch (x) { showErr(E(x.code)) }
    };
    $('#a-google').onclick = async () => {
      err.textContent = '';
      const pr = new A.GoogleAuthProvider();
      try { await A.signInWithPopup(auth, pr) } catch (x) {
        if (x.code === 'auth/popup-blocked' || x.code === 'auth/operation-not-supported-in-this-environment') { try { await A.signInWithRedirect(auth, pr); return } catch (y) {} }
        showErr(E(x.code));
      }
    };
    $('#a-forgot').onclick = async () => {
      const email = $('#a-email').value.trim(); if (!email) return showErr('a_need_email');
      try { await A.sendPasswordResetEmail(auth, email); err.textContent = tr.a_reset_sent; err.className = 'okm' } catch (x) { showErr(E(x.code)) }
    };
  }

  // Perfil: cambiar contraseña y reenviar verificación
  const pp = document.getElementById('p-pass');
  if (pp) pp.onclick = async () => { const u = auth.currentUser; if (!u) return; try { await A.sendPasswordResetEmail(auth, u.email); document.getElementById('p-msg').textContent = tr.w_pass_sent } catch (x) {} };
  const pr = document.getElementById('p-resend');
  if (pr) pr.onclick = async () => { const u = auth.currentUser; if (!u) return; try { await A.sendEmailVerification(u); document.getElementById('p-msg').textContent = tr.p_verif_sent } catch (x) {} };
}
