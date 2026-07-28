const root = document.querySelector("[data-person-profile-root]");
const personId = new URLSearchParams(location.search).get("person_id");

function escapePersonHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

function personSessionId() {
  const key = "profilage.personSession";
  let value = sessionStorage.getItem(key);
  if (!value) { const bytes = crypto.getRandomValues(new Uint8Array(24)); value = Array.from(bytes, b => b.toString(16).padStart(2, "0")).join(""); sessionStorage.setItem(key, value); }
  return value;
}

async function getJson(url, options) {
  const response = await fetch(url, options); const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "정보를 불러오지 못했습니다."); return payload;
}

async function loadPersonProfile() {
  if (!/^per_[a-f0-9]{24}$/.test(personId || "")) throw new Error("유효한 인물 프로필 주소가 아닙니다.");
  const profile = await getJson(`/api/person/${encodeURIComponent(personId)}`);
  document.querySelector("[data-person-name]").textContent = profile.display_name;
  document.querySelector("[data-person-subtitle]").textContent = profile.subtitle || "";
  document.querySelector("[data-person-meta]").textContent = `처리 범위: 공개 역할 · 마지막 확인 ${profile.last_verified_at || "-"}`;
  document.querySelector("[data-person-evidence]").innerHTML = (profile.evidence || []).map(item => `<article class="person-evidence-card"><p>${escapePersonHtml(item.text)}</p><small>근거 ID ${escapePersonHtml(item.evidence_id)}</small></article>`).join("") || "<p>표시할 근거가 없습니다.</p>";
  document.querySelector("[data-person-sources]").innerHTML = (profile.sources || []).map(source => `<article class="person-source-card"><strong>${escapePersonHtml(source.title || source.domain)}</strong><p>${escapePersonHtml(source.domain)} · ${escapePersonHtml(source.source_type)}</p>${source.open_url ? `<a href="${escapePersonHtml(source.open_url)}" target="_blank" rel="noopener noreferrer nofollow">원문 열기</a>` : ""}</article>`).join("");
  loadPersonSummary();
}

async function loadPersonSummary() {
  const target = document.querySelector("[data-person-summary]");
  try { const payload = await getJson(`/api/person/${encodeURIComponent(personId)}/summary`); const summary = payload.summary || {}; target.innerHTML = `<h3>${escapePersonHtml(summary.headline || "공개 근거 요약")}</h3><p>${escapePersonHtml(summary.overview || "")}</p>${(summary.verified_facts || []).length ? `<ul>${summary.verified_facts.map(item => `<li>${escapePersonHtml(typeof item === "string" ? item : JSON.stringify(item))}</li>`).join("")}</ul>` : ""}<p class="person-analysis-notice">${escapePersonHtml((summary.limitations || []).join(" "))}</p>`; }
  catch (error) { target.textContent = error.message; }
}

document.querySelector("[data-person-rights-form]")?.addEventListener("submit", async event => {
  event.preventDefault(); const form = new FormData(event.currentTarget); const status = document.querySelector("[data-person-rights-status]");
  try { const payload = await getJson(`/api/person/${encodeURIComponent(personId)}/correction`, {method:"POST", headers:{"Content-Type":"application/json", "X-Profilage-Session":personSessionId()}, body:JSON.stringify({kind:form.get("kind"), detail:form.get("detail")})}); status.textContent = `접수되었습니다. 요청 번호: ${payload.request_id}`; event.currentTarget.reset(); }
  catch (error) { status.textContent = error.message; }
});

loadPersonProfile().catch(error => { root.innerHTML = `<section class="search-message search-message-error"><h1>프로필을 표시할 수 없습니다</h1><p>${escapePersonHtml(error.message)}</p><a href="/">검색으로 돌아가기</a></section>`; });
