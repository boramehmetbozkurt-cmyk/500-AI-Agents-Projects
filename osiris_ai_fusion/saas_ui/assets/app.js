(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { mode: "login", token: localStorage.getItem("osiris_session") || "", lastKey: "" };
  const els = {
    modal: $("modal"), account: $("accountBtn"), start: $("startBtn"), close: $("closeModal"), authView: $("authView"), dash: $("dashboardView"),
    loginTab: $("loginTab"), signupTab: $("signupTab"), form: $("authForm"), nameLabel: $("nameLabel"), orgLabel: $("orgLabel"), name: $("nameInput"), org: $("orgInput"), email: $("emailInput"), password: $("passwordInput"), submit: $("authSubmit"), authError: $("authError"),
    workspace: $("workspaceName"), plan: $("planBadge"), usage: $("usageText"), meter: $("usageMeter"), keys: $("keys"), keyCount: $("keyCount"), newKey: $("newKeyBtn"), reveal: $("newKeyReveal"), rawKey: $("rawKey"), copy: $("copyKeyBtn"), launch: $("launchBtn"), logout: $("logoutBtn"), dashError: $("dashError"), plans: $("planGrid")
  };

  function headers(json = false) { const h = {}; if (state.token) h.Authorization = `Bearer ${state.token}`; if (json) h["Content-Type"] = "application/json"; return h; }
  async function api(path, options = {}) { const res = await fetch(path, {...options, headers: {...headers(Boolean(options.body)), ...(options.headers || {})}}); const text = await res.text(); let data = {}; try { data = text ? JSON.parse(text) : {}; } catch { data = {detail: text}; } if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`); return data; }
  function openModal() { els.modal.classList.remove("hidden"); els.modal.setAttribute("aria-hidden", "false"); if (state.token) loadDashboard(); else showAuth(); }
  function closeModal() { els.modal.classList.add("hidden"); els.modal.setAttribute("aria-hidden", "true"); }
  function showAuth() { els.authView.classList.remove("hidden"); els.dash.classList.add("hidden"); }
  function setMode(mode) { state.mode = mode; const signup = mode === "signup"; els.loginTab.classList.toggle("active", !signup); els.signupTab.classList.toggle("active", signup); els.nameLabel.classList.toggle("hidden", !signup); els.orgLabel.classList.toggle("hidden", !signup); els.submit.textContent = signup ? "Ücretsiz hesap oluştur" : "Giriş yap"; els.password.autocomplete = signup ? "new-password" : "current-password"; els.authError.textContent = ""; }
  function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]); }

  async function loadPlans() {
    try {
      const data = await api("/saas/plans");
      const order = ["free", "pro", "team"];
      els.plans.innerHTML = order.map((id) => { const p = data.plans[id]; const featured = id === "pro"; return `<article class="plan-card ${featured ? "featured" : ""}">${featured ? '<span class="tag">POPULAR</span>' : ""}<small>${escapeHtml(p.label).toUpperCase()}</small><div class="price">$${p.price_usd_month}<small>/ay</small></div><p>${id === "free" ? "Ürünü dene ve ilk araştırmalarını yap." : id === "pro" ? "Yoğun bireysel araştırma ve API kullanımı." : "Ekipler ve yüksek hacimli OSINT iş akışları."}</p><ul><li>${p.investigations_per_month.toLocaleString()} araştırma / ay</li><li>${p.watchlists} watchlist</li><li>${p.api_keys} API anahtarı</li><li>Provider federation + evidence ledger</li></ul><button class="${featured ? "primary" : "secondary"} wide plan-cta" data-plan="${id}">${id === "free" ? "Ücretsiz başla" : "Planı seç"}</button></article>`; }).join("");
      document.querySelectorAll(".plan-cta").forEach((btn) => btn.addEventListener("click", () => { if (btn.dataset.plan === "free" || !state.token) openModal(); else checkout(btn.dataset.plan); }));
    } catch (err) { els.plans.innerHTML = `<p class="error">Planlar yüklenemedi: ${escapeHtml(err.message)}</p>`; }
  }

  async function loadDashboard() {
    try {
      const [me, usage, keys] = await Promise.all([api("/saas/me"), api("/saas/usage"), api("/saas/api-keys")]);
      els.authView.classList.add("hidden"); els.dash.classList.remove("hidden");
      els.workspace.textContent = me.tenant.name || me.tenant.id; els.plan.textContent = String(me.tenant.plan || "free").toUpperCase();
      const used = usage.usage.investigations || 0; const max = usage.limits.investigations_per_month || 1; els.usage.textContent = `${used.toLocaleString()} / ${max.toLocaleString()}`; els.meter.style.width = `${Math.min(100, used / max * 100)}%`;
      renderKeys(keys); els.dashError.textContent = ""; els.account.textContent = me.user.name || me.user.email;
    } catch (err) { if (/Authentication/i.test(err.message)) { localStorage.removeItem("osiris_session"); state.token = ""; showAuth(); } els.dashError.textContent = err.message; }
  }
  function renderKeys(keys) { els.keyCount.textContent = String(keys.length); els.keys.innerHTML = keys.length ? keys.map(k => `<div class="key-row"><div><b>${escapeHtml(k.name)}</b><br><small>••••${escapeHtml(k.last4)}</small></div><button data-id="${escapeHtml(k.id)}">İptal</button></div>`).join("") : '<p class="error" style="color:#6f7c87">Henüz API anahtarı yok.</p>'; els.keys.querySelectorAll("button[data-id]").forEach(b => b.addEventListener("click", async () => { try { await api(`/saas/api-keys/${encodeURIComponent(b.dataset.id)}`, {method:"DELETE"}); await loadDashboard(); } catch(e) { els.dashError.textContent = e.message; } })); }
  async function createKey() { try { const data = await api("/saas/api-keys", {method:"POST", body:JSON.stringify({name:"Command Center"})}); state.lastKey = data.api_key; els.rawKey.textContent = data.api_key; els.reveal.classList.remove("hidden"); sessionStorage.setItem("fusion_api_key", data.api_key); await loadDashboard(); els.reveal.classList.remove("hidden"); } catch(err) { els.dashError.textContent = err.message; } }
  async function checkout(plan) { try { const data = await api("/saas/billing/checkout", {method:"POST", body:JSON.stringify({plan})}); if (!data.checkout_url) throw new Error("Checkout URL oluşturulamadı"); window.location.assign(data.checkout_url); } catch(err) { els.dashError.textContent = err.message; openModal(); } }

  els.form.addEventListener("submit", async (event) => { event.preventDefault(); els.submit.disabled = true; els.authError.textContent = ""; try { const payload = {email:els.email.value, password:els.password.value}; if (state.mode === "signup") { payload.name = els.name.value; payload.organization = els.org.value; } const data = await api(state.mode === "signup" ? "/saas/signup" : "/saas/login", {method:"POST", body:JSON.stringify(payload)}); state.token = data.token; localStorage.setItem("osiris_session", state.token); await loadDashboard(); } catch(err) { els.authError.textContent = err.message; } finally { els.submit.disabled = false; } });
  els.loginTab.addEventListener("click", () => setMode("login")); els.signupTab.addEventListener("click", () => setMode("signup")); els.start.addEventListener("click", () => { setMode("signup"); openModal(); }); els.account.addEventListener("click", openModal); els.close.addEventListener("click", closeModal); els.modal.addEventListener("click", e => { if (e.target === els.modal) closeModal(); });
  els.newKey.addEventListener("click", createKey); els.copy.addEventListener("click", async () => { if (state.lastKey) await navigator.clipboard.writeText(state.lastKey); }); els.launch.addEventListener("click", () => { if (state.lastKey) sessionStorage.setItem("fusion_api_key", state.lastKey); window.location.assign("/app"); });
  els.logout.addEventListener("click", async () => { try { await api("/saas/logout", {method:"POST"}); } catch {} localStorage.removeItem("osiris_session"); sessionStorage.removeItem("fusion_api_key"); state.token = ""; state.lastKey = ""; els.account.textContent = "Giriş"; setMode("login"); showAuth(); });
  document.querySelectorAll(".upgrade").forEach(b => b.addEventListener("click", () => checkout(b.dataset.plan)));

  const billing = new URLSearchParams(location.search).get("billing"); if (billing === "success" && state.token) setTimeout(openModal, 100);
  loadPlans(); if (state.token) api("/saas/me").then(me => { els.account.textContent = me.user.name || me.user.email; }).catch(() => { localStorage.removeItem("osiris_session"); state.token = ""; });
})();
