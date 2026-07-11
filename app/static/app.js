const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#company-query");
const statusEl = document.querySelector("#search-status");
const resultList = document.querySelector("#result-list");
const luckySearchButton = document.querySelector("#lucky-search");
const searchSubmitButton = form?.querySelector(".search-submit");
const exampleQueryButtons = Array.from(document.querySelectorAll("[data-example-query]"));
const compareTray = document.querySelector("[data-compare-tray]");
const compareTrayList = document.querySelector("[data-compare-tray-list]");
const compareTrayLink = document.querySelector("[data-compare-tray-link]");
const compareTrayStatus = document.querySelector("[data-compare-tray-status]");
const recentQueryList = document.querySelector("[data-recent-query-list]");
const searchTypeSelect = document.querySelector("#search-type");
const personSearchHelp = document.querySelector("[data-person-search-help]");

const outlineUrl = "/api/company/get_corp_outline";
const listedUrl = "/api/company/get_krx_listed_item";
const COMPARE_STORAGE_KEY = "profilage.compareCompanies";
const MAX_COMPARE_COMPANIES = 5;
const RECENT_SEARCH_STORAGE_KEY = "profilage.recentSearches";
const MAX_RECENT_SEARCHES = 5;
const SEARCH_RESULT_PAGE_SIZE = 20;
const SEARCH_LOAD_MORE_OFFSET = 420;
const searchState = {
  type: "company",
  token: 0,
  query: "",
  items: [],
  listedCrnos: new Set(),
  renderedCount: 0,
  isLoadingMore: false,
  controller: null,
};

function personSessionId() {
  const key = "profilage.personSession";
  let value = sessionStorage.getItem(key);
  if (!value) {
    const bytes = crypto.getRandomValues(new Uint8Array(24));
    value = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
    sessionStorage.setItem(key, value);
  }
  return value;
}

function isPersonMode() {
  return searchState.type === "person";
}

function currentSearchQuery() {
  return queryInput.value.trim();
}

function profileUrl(corporateRegistrationNumber, returnQuery = currentSearchQuery()) {
  const endpoint = new URL("/profile", window.location.origin);
  endpoint.searchParams.set("crno", corporateRegistrationNumber);
  if (returnQuery) {
    endpoint.searchParams.set("return_q", returnQuery);
  }
  return `${endpoint.pathname}${endpoint.search}`;
}

function syncSearchUrl(query) {
  const nextUrl = new URL(window.location.href);
  if (query) {
    nextUrl.searchParams.set("q", query);
  } else {
    nextUrl.searchParams.delete("q");
  }
  window.history.replaceState({}, "", nextUrl);
}

function normalizeItems(payload) {
  if (Array.isArray(payload?.items)) return payload.items;
  const item = payload?.body?.items?.item;
  if (!item) return [];
  return Array.isArray(item) ? item : [item];
}

function text(value, fallback = "-") {
  return value === undefined || value === null || value === "" ? fallback : value;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function attr(value, fallback = "") {
  return escapeHtml(text(value, fallback));
}

function formatResultNumber(value) {
  if (value === undefined || value === null || value === "") return "-";
  const numeric = Number(String(value).replaceAll(",", ""));
  return Number.isFinite(numeric) ? numeric.toLocaleString("ko-KR") : text(value);
}

function compareItems() {
  try {
    const parsed = JSON.parse(localStorage.getItem(COMPARE_STORAGE_KEY) || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item?.crno)
      .filter((item, index, items) => items.findIndex((candidate) => candidate.crno === item.crno) === index)
      .slice(0, MAX_COMPARE_COMPANIES);
  } catch {
    return [];
  }
}

function saveCompareItems(items) {
  localStorage.setItem(
    COMPARE_STORAGE_KEY,
    JSON.stringify(items.slice(0, MAX_COMPARE_COMPANIES)),
  );
}

function compareUrl(items = compareItems()) {
  const endpoint = new URL("/compare", window.location.origin);
  items.forEach((item) => endpoint.searchParams.append("crno", item.crno));
  return `${endpoint.pathname}${endpoint.search}`;
}

function updateCompareControls() {
  const selectedCrnos = new Set(compareItems().map((item) => item.crno));
  document.querySelectorAll("[data-result-compare-add]").forEach((button) => {
    const isSelected = selectedCrnos.has(button.dataset.resultCompareAdd);
    const label = isSelected ? "비교에 추가됨" : "비교 추가";
    button.setAttribute("aria-label", label);
    button.setAttribute("title", label);
    button.innerHTML = `
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        ${isSelected ? '<path d="m6 12 4 4 8-9"></path>' : '<path d="M8 5H5v14h3M16 5h3v14h-3M12 8v8M8 12h8"></path>'}
      </svg>
      <span class="visually-hidden">${label}</span>
    `;
    button.disabled = isSelected;
    button.setAttribute("aria-pressed", String(isSelected));
  });
}

function updateCompareTray(message = "") {
  const items = compareItems();
  document.querySelectorAll("[data-compare-nav-count]").forEach((count) => {
    count.hidden = items.length === 0;
    count.textContent = String(items.length);
  });
  updateCompareControls();
  if (!compareTray || !compareTrayList || !compareTrayLink || !compareTrayStatus) return;

  compareTray.hidden = items.length === 0;
  compareTrayList.innerHTML = items
    .map(
      (item) => `
        <li>
          <span>${escapeHtml(text(item.name, item.crno))}</span>
          <button type="button" data-compare-tray-remove="${attr(item.crno)}" aria-label="${attr(text(item.name, item.crno))} 비교에서 제거">×</button>
        </li>
      `,
    )
    .join("");
  compareTrayStatus.textContent =
    message ||
    (items.length >= 2
      ? `${items.length}개 기업을 비교할 수 있습니다.`
      : "기업을 1개 더 선택하면 비교할 수 있습니다.");
  compareTrayLink.href = compareUrl(items);
  compareTrayLink.setAttribute("aria-disabled", String(items.length < 2));
  compareTrayLink.classList.toggle("is-disabled", items.length < 2);

  compareTrayList.querySelectorAll("[data-compare-tray-remove]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextItems = compareItems().filter((item) => item.crno !== button.dataset.compareTrayRemove);
      saveCompareItems(nextItems);
      updateCompareTray(`${nextItems.length}개 기업이 선택되어 있습니다.`);
    });
  });
}

function addCompareItem(company) {
  const items = compareItems();
  if (items.some((item) => item.crno === company.crno)) {
    updateCompareTray(`${text(company.name, "기업")}은 이미 비교함에 있습니다.`);
    return true;
  }
  if (items.length >= MAX_COMPARE_COMPANIES) {
    updateCompareTray(`최대 ${MAX_COMPARE_COMPANIES}개까지 비교할 수 있습니다. 기존 기업을 제거해주세요.`);
    return false;
  }
  const nextItems = [...items, company];
  saveCompareItems(nextItems);
  updateCompareTray(`${text(company.name, "기업")}을 비교함에 추가했습니다.`);
  return true;
}

function recentSearches() {
  try {
    const parsed = JSON.parse(localStorage.getItem(RECENT_SEARCH_STORAGE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter(Boolean).map(String) : [];
  } catch {
    return [];
  }
}

function saveRecentSearch(query) {
  const normalizedQuery = query.trim();
  if (!normalizedQuery) return;
  try {
    const next = [
      normalizedQuery,
      ...recentSearches().filter((item) => item !== normalizedQuery),
    ].slice(0, MAX_RECENT_SEARCHES);
    localStorage.setItem(RECENT_SEARCH_STORAGE_KEY, JSON.stringify(next));
    renderRecentSearches();
  } catch {
    // Recent searches are a convenience; search should still work if storage is unavailable.
  }
}

function renderRecentSearches() {
  if (!recentQueryList) return;
  const searches = recentSearches();
  recentQueryList.innerHTML = searches
    .map(
      (query) =>
        `<button type="button" data-recent-query="${attr(query)}">${escapeHtml(query)}</button>`,
    )
    .join("");
}

function setStatus(message) {
  statusEl.textContent = message;
}

function setSearchBusy(isBusy) {
  form?.setAttribute("aria-busy", String(isBusy));
  if (searchSubmitButton) searchSubmitButton.disabled = isBusy;
  exampleQueryButtons.forEach((button) => {
    button.disabled = isBusy;
  });
}

function renderSearchMessage(kind, title, message) {
  clearResults();
  const query = searchState.query;
  const canRetry = kind === "error" && query;
  resultList.innerHTML = `
    <article class="search-message search-message-${attr(kind)}">
      <span class="search-message-kicker">${kind === "error" ? "검색 오류" : "검색 결과"}</span>
      <h2>${escapeHtml(title)}</h2>
      <p>${escapeHtml(message)}</p>
      <div class="search-message-actions">
        ${canRetry ? '<button type="button" data-search-retry>다시 시도</button>' : ""}
        <button type="button" data-search-focus>검색어 수정</button>
      </div>
    </article>
  `;
  resultList.querySelector("[data-search-retry]")?.addEventListener("click", () => {
    if (isPersonMode()) searchPeople(query);
    else searchCompanies(query);
  });
  resultList.querySelector("[data-search-focus]")?.addEventListener("click", () => {
    queryInput.focus();
    queryInput.select();
  });
}

function clearResults() {
  resultList.innerHTML = "";
}

function renderSearchSkeleton(count = 5) {
  clearResults();
  const fragment = document.createDocumentFragment();

  Array.from({ length: count }).forEach(() => {
    const card = document.createElement("div");
    card.className = "result-card skeleton-card";
    card.setAttribute("aria-hidden", "true");
    card.innerHTML = `
      <span class="skeleton-line skeleton-title"></span>
      <span class="skeleton-line"></span>
      <span class="skeleton-line skeleton-short"></span>
    `;
    fragment.appendChild(card);
  });

  resultList.appendChild(fragment);
}

function renderResults(items, { append = false } = {}) {
  if (!append) {
    clearResults();
  }
  const fragment = document.createDocumentFragment();
  const selectedCrnos = new Set(compareItems().map((item) => item.crno));

  if (!append) {
    const header = document.createElement("div");
    header.className = "result-list-header";
    header.setAttribute("aria-hidden", "true");
    header.innerHTML = `
      <span>기업</span>
      <span>법인등록번호</span>
      <span>업종</span>
      <span>대표자</span>
      <span>직원 수</span>
      <span>작업</span>
    `;
    fragment.appendChild(header);
  }

  items.forEach((company) => {
    const displayName = company.listedCorpName || company.corpNm || company.itmsNm;
    const market = company.mrktCtg || company.corpRegMrktDcdNm;
    const card = document.createElement("article");
    card.className = "result-card entity-result-row";
    card.dataset.crno = company.crno;
    card.innerHTML = `
      <div class="result-company-cell">
        <div class="result-title-stack" data-label="기업">
          <div class="result-badge-row">
            <span class="entity-type-badge">기업</span>
            <span class="result-market-badge">${escapeHtml(company.isListed ? text(market, "상장") : "비상장/확인 필요")}</span>
          </div>
          <a class="result-title-link" href="${attr(profileUrl(company.crno))}">
            <strong>${escapeHtml(text(displayName, "기업명 정보 없음"))}</strong>
          </a>
          <span class="result-subtitle">${escapeHtml(text(company.corpEnsnNm || company.listedItemName || company.enpRprFnm, "보조 정보 없음"))}</span>
        </div>
        <div class="result-data-badges">
          <span>${company.isListed ? "주가 가능" : "주가 미제공"}</span>
          ${company.isListed ? `<span>${escapeHtml(text(company.srtnCd, "종목코드"))}</span>` : ""}
        </div>
      </div>
      <span class="result-column" data-label="법인등록번호">${escapeHtml(text(company.crno))}</span>
      <span class="result-column" data-label="업종">${escapeHtml(text(company.enpMainBizNm || company.itmsNm, "정보 없음"))}</span>
      <span class="result-column" data-label="대표자">${escapeHtml(text(company.enpRprFnm, "정보 없음"))}</span>
      <span class="result-column" data-label="직원 수">${escapeHtml(formatResultNumber(company.enpEmpeCnt))}</span>
      <div class="result-actions" data-label="작업">
        <a class="result-profile-link result-action-icon" href="${attr(profileUrl(company.crno))}" aria-label="프로필 보기" title="프로필 보기">
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="8" r="3.25"></circle><path d="M5.5 19c.7-3.4 3-5.25 6.5-5.25s5.8 1.85 6.5 5.25"></path></svg>
          <span class="visually-hidden">프로필 보기</span>
        </a>
        <button class="result-action-icon" type="button" data-result-compare-add="${attr(company.crno)}" data-result-name="${attr(displayName)}" aria-label="${selectedCrnos.has(company.crno) ? "비교에 추가됨" : "비교 추가"}" title="${selectedCrnos.has(company.crno) ? "비교에 추가됨" : "비교 추가"}" aria-pressed="${selectedCrnos.has(company.crno) ? "true" : "false"}" ${selectedCrnos.has(company.crno) ? "disabled" : ""}>
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${selectedCrnos.has(company.crno) ? '<path d="m6 12 4 4 8-9"></path>' : '<path d="M8 5H5v14h3M16 5h3v14h-3M12 8v8M8 12h8"></path>'}</svg>
          <span class="visually-hidden">${selectedCrnos.has(company.crno) ? "비교에 추가됨" : "비교 추가"}</span>
        </button>
      </div>
    `;
    fragment.appendChild(card);
  });

  resultList.appendChild(fragment);
  setupResultCompareButtons();
}

function shouldLoadMoreSearchResults() {
  return (
    window.innerHeight + window.scrollY >=
    document.documentElement.scrollHeight - SEARCH_LOAD_MORE_OFFSET
  );
}

async function enrichResultsForRender(items, signal) {
  const crnos = items
    .map((item) => item.crno)
    .filter(
      (crno, index, values) =>
        crno && !searchState.listedCrnos.has(crno) && values.indexOf(crno) === index,
    );

  if (crnos.length === 0) {
    return items;
  }

  const listedByCrnoPayloads = await Promise.all(
    crnos.map((crno) =>
      fetchJson(
        listedUrl,
        {
          corporate_registration_number: crno,
          page: 1,
          per_page: 1,
        },
        { signal },
      ).catch((error) => {
        if (error.name === "AbortError") throw error;
        return null;
      }),
    ),
  );
  const listedItems = listedByCrnoPayloads.flatMap((payload) => normalizeItems(payload));
  listedItems
    .map((item) => item.crno)
    .filter(Boolean)
    .forEach((crno) => searchState.listedCrnos.add(crno));

  return mergeCompanyResults(items, listedItems);
}

async function renderNextSearchResults(token) {
  if (searchState.isLoadingMore || token !== searchState.token) return;
  if (searchState.renderedCount >= searchState.items.length) return;

  searchState.isLoadingMore = true;
  const start = searchState.renderedCount;
  const nextItems = searchState.items.slice(start, start + SEARCH_RESULT_PAGE_SIZE);
  const append = start > 0;

  try {
    if (append) {
      setStatus("더 불러오는 중...");
    }
    const enrichedItems = await enrichResultsForRender(nextItems, searchState.controller?.signal);
    if (token !== searchState.token) return;
    renderResults(enrichedItems, { append });
    searchState.renderedCount += nextItems.length;
    setStatus("");
  } finally {
    searchState.isLoadingMore = false;
  }
}

function maybeLoadMoreSearchResults() {
  if (!shouldLoadMoreSearchResults()) return;
  renderNextSearchResults(searchState.token);
}

function setupResultCompareButtons() {
  document.querySelectorAll("[data-result-compare-add]").forEach((button) => {
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";
    button.addEventListener("click", () => {
      const crno = button.dataset.resultCompareAdd;
      const name = button.dataset.resultName;
      const added = addCompareItem({ crno, name });
      if (!added) return;
      button.setAttribute("aria-label", "비교에 추가됨");
      button.setAttribute("title", "비교에 추가됨");
      button.innerHTML = `
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="m6 12 4 4 8-9"></path>
        </svg>
        <span class="visually-hidden">비교에 추가됨</span>
      `;
      button.disabled = true;
      button.setAttribute("aria-pressed", "true");
    });
  });
}

function mergeCompanyResults(outlineItems, listedItems) {
  const companies = new Map();
  const listedMarketNames = new Set(["유가", "코스닥", "코넥스"]);

  listedItems.forEach((item, index) => {
    const key = item.crno || `${item.itmsNm}-${item.srtnCd}`;
    companies.set(key, {
      ...item,
      corpNm: item.corpNm || item.itmsNm,
      listedCorpName: item.corpNm || item.itmsNm,
      listedItemName: item.itmsNm,
      isListed: true,
      searchRank: index,
    });
  });

  outlineItems.forEach((item) => {
    const key = item.crno || `${item.corpNm}-${item.bzno}`;
    const existing = companies.get(key) || {};
    const isListed =
      Boolean(existing.isListed) || listedMarketNames.has(item.corpRegMrktDcdNm);
    companies.set(key, {
      ...item,
      ...existing,
      corpNm: existing.corpNm || item.corpNm || existing.itmsNm,
      listedCorpName: existing.listedCorpName,
      mrktCtg: existing.mrktCtg || item.corpRegMrktDcdNm,
      isListed,
      searchRank: existing.searchRank ?? 100,
    });
  });

  return Array.from(companies.values()).sort((left, right) => {
    if (left.isListed !== right.isListed) return left.isListed ? -1 : 1;
    if (left.searchRank !== right.searchRank) return left.searchRank - right.searchRank;
    return text(left.corpNm).localeCompare(text(right.corpNm), "ko");
  });
}

async function fetchJson(url, params, { signal } = {}) {
  const endpoint = new URL(url, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      endpoint.searchParams.set(key, value);
    }
  });

  const response = await fetch(endpoint, { signal });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "요청에 실패했습니다.");
  }
  return response.json();
}

async function loadCompanySearchResults(query, signal) {
  const [outlinePayload, listedPayload] = await Promise.all([
    fetchJson(
      outlineUrl,
      {
        company_name: query,
        page: 1,
        per_page: 200,
      },
      { signal },
    ),
    fetchJson(
      listedUrl,
      {
        item_name: query,
        page: 1,
        per_page: 20,
      },
      { signal },
    ).catch((error) => {
      if (error.name === "AbortError") throw error;
      return null;
    }),
  ]);
  const outlineItems = normalizeItems(outlinePayload);
  const listedItems = normalizeItems(listedPayload);
  const listedCrnos = new Set(listedItems.map((item) => item.crno).filter(Boolean));
  return {
    items: mergeCompanyResults(outlineItems, listedItems),
    listedCrnos,
  };
}

async function searchCompanies(query) {
  searchState.controller?.abort();
  const controller = new AbortController();
  const token = searchState.token + 1;
  searchState.token = token;
  searchState.controller = controller;
  searchState.query = query;
  searchState.items = [];
  searchState.listedCrnos = new Set();
  searchState.renderedCount = 0;
  searchState.isLoadingMore = false;
  document.body.classList.remove("is-idle");
  queryInput.value = query;
  saveRecentSearch(query);
  syncSearchUrl(query);
  setSearchBusy(true);
  setStatus("검색 중...");
  renderSearchSkeleton();

  try {
    const { items, listedCrnos } = await loadCompanySearchResults(query, controller.signal);
    if (token !== searchState.token) return;

    if (items.length === 0) {
      setStatus("검색 결과가 없습니다.");
      renderSearchMessage(
        "empty",
        "일치하는 기업을 찾지 못했습니다",
        "기업명 전체 또는 법인등록번호를 확인해 다시 검색해주세요.",
      );
      return;
    }

    searchState.items = items;
    searchState.listedCrnos = listedCrnos;
    clearResults();
    setStatus("");
    await renderNextSearchResults(token);
    maybeLoadMoreSearchResults();
  } catch (error) {
    if (error.name === "AbortError" || token !== searchState.token) return;
    setStatus("기업 정보를 불러오지 못했습니다.");
    renderSearchMessage(
      "error",
      "검색 결과를 불러오지 못했습니다",
      "잠시 후 다시 시도하거나 다른 검색어를 입력해주세요.",
    );
  } finally {
    if (token === searchState.token) {
      setSearchBusy(false);
    }
  }
}

function renderPersonResults(payload) {
  clearResults();
  const notices = Array.isArray(payload.notices) ? payload.notices : [];
  const items = Array.isArray(payload.items) ? payload.items : [];
  if (!items.length) {
    renderSearchMessage("empty", "확인 가능한 인물 후보가 없습니다", "이름과 소속 또는 직책을 함께 입력해 보세요.");
    return;
  }
  resultList.innerHTML = items.map((person) => `
    <article class="result-card person-result-card">
      <div class="person-result-head">
        <div>
          <div class="result-badge-row"><span class="entity-type-badge">인물</span><span class="result-market-badge">${escapeHtml(text(person.identity_status, "확인 필요"))}</span></div>
          <h3>${escapeHtml(text(person.display_name, "이름 미상"))}</h3>
          <p>${escapeHtml(text(person.subtitle, "공개 출처를 확인해 주세요."))}</p>
        </div>
        <span>${(person.source_badges || []).map((badge) => `<span class="result-market-badge">${escapeHtml(badge)}</span>`).join(" ")}</span>
      </div>
      <div class="person-source-list">
        ${(person.pages || []).map((page) => `
          <section class="person-source-card" data-person-source>
            <div class="person-source-head">
              <strong>${escapeHtml(text(page.title, page.domain))}</strong>
              <span>${escapeHtml(text(page.domain))} · ${escapeHtml(text(page.page_type))}</span>
            </div>
            <p>${page.analysis_capability === "external_view_only" ? "플랫폼 권한 정책상 자동 수집하지 않고 링크 후보만 표시합니다." : page.analysis_capability === "policy_review_required" ? "원문 링크는 확인할 수 있지만 서버 분석은 도메인 검토가 필요합니다." : "사용자가 요청할 때 이 공개 페이지 한 건만 분석합니다."}</p>
            <div class="person-source-actions">
              ${page.open_url ? `<a href="${attr(page.open_url)}" target="_blank" rel="noopener noreferrer nofollow">원문 열기</a>` : ""}
              ${page.analysis_capability === "server_public" ? `<button type="button" data-person-page-analyze data-candidate-id="${attr(person.candidate_id)}" data-source-ref="${attr(page.source_ref)}">이 페이지 분석</button>` : ""}
              ${page.analysis_capability === "external_view_only" ? "<span>외부 보기만 가능</span>" : ""}
            </div>
            <div data-person-analysis-result></div>
          </section>
        `).join("")}
      </div>
    </article>
  `).join("");
  resultList.querySelectorAll("[data-person-page-analyze]").forEach((button) => {
    button.addEventListener("click", () => analyzePersonPage(button));
  });
  setStatus(notices.join(" "));
}

async function searchPeople(query) {
  searchState.controller?.abort();
  const controller = new AbortController();
  const token = ++searchState.token;
  searchState.controller = controller;
  searchState.query = query;
  document.body.classList.remove("is-idle");
  setSearchBusy(true);
  setStatus("공개 출처에서 인물 후보를 확인하는 중...");
  renderSearchSkeleton(3);
  try {
    const response = await fetch("/api/person/search", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Profilage-Session": personSessionId()},
      body: JSON.stringify({query, limit: 10, purpose_code: "business_research"}),
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "인물 검색에 실패했습니다.");
    if (token !== searchState.token) return;
    renderPersonResults(payload);
  } catch (error) {
    if (error.name === "AbortError" || token !== searchState.token) return;
    setStatus("인물 후보를 불러오지 못했습니다.");
    renderSearchMessage("error", "인물 검색을 완료하지 못했습니다", error.message || "잠시 후 다시 시도해 주세요.");
  } finally {
    if (token === searchState.token) setSearchBusy(false);
  }
}

async function analyzePersonPage(button) {
  const container = button.closest("[data-person-source]")?.querySelector("[data-person-analysis-result]");
  button.disabled = true;
  button.textContent = "분석 중...";
  if (container) container.innerHTML = '<p class="person-analysis-notice">페이지 한 건을 안전하게 가져와 근거 기반으로 분석하고 있습니다.</p>';
  try {
    const response = await fetch("/api/person/page-analysis", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Profilage-Session": personSessionId()},
      body: JSON.stringify({candidate_id: button.dataset.candidateId, source_ref: button.dataset.sourceRef, purpose_code: "business_research"}),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "페이지 분석에 실패했습니다.");
    const analysis = payload.analysis || {};
    if (container) container.innerHTML = `
      <article class="person-analysis-card">
        <h4>이 페이지의 요약</h4>
        <p>${escapeHtml(text(analysis.summary, "요약 없음"))}</p>
        ${(analysis.topics || []).length ? `<p><strong>다룬 주제</strong> · ${(analysis.topics || []).map(escapeHtml).join(" · ")}</p>` : ""}
        ${(analysis.observable_communication_features || []).length ? `<p><strong>이 페이지의 표현 방식</strong> · ${(analysis.observable_communication_features || []).map(escapeHtml).join(" · ")}</p>` : ""}
        <p class="person-analysis-notice">${escapeHtml((payload.limitations || []).join(" "))} 결과는 ${Math.round((payload.expires_in_seconds || 3600) / 60)}분 후 삭제됩니다.</p>
      </article>`;
    button.textContent = "분석 완료";
  } catch (error) {
    if (container) container.innerHTML = `<p class="person-analysis-notice">${escapeHtml(error.message)}</p>`;
    button.disabled = false;
    button.textContent = "다시 분석";
  }
}

function applySearchMode(type) {
  searchState.type = type === "person" ? "person" : "company";
  const personMode = isPersonMode();
  queryInput.placeholder = personMode ? "인물명과 소속·직책을 함께 입력" : "기업명, 종목코드, 법인등록번호로 검색";
  queryInput.setAttribute("aria-label", personMode ? "인물명과 소속·직책" : "기업명, 종목코드, 법인등록번호");
  personSearchHelp.hidden = !personMode;
  recentQueryList.hidden = personMode;
  compareTray && (compareTray.hidden = personMode || compareItems().length === 0);
  clearResults();
  setStatus("");
  queryInput.value = "";
  if (personMode) syncSearchUrl("");
  else updateCompareTray();
}

window.addEventListener("scroll", maybeLoadMoreSearchResults, { passive: true });

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = currentSearchQuery();
  if (!query) {
    setStatus(isPersonMode() ? "인물명을 입력해주세요." : "기업명을 입력해주세요.");
    clearResults();
    syncSearchUrl("");
    return;
  }
  if (isPersonMode()) searchPeople(query);
  else searchCompanies(query);
});

searchTypeSelect?.addEventListener("change", () => applySearchMode(searchTypeSelect.value));

luckySearchButton?.addEventListener("click", () => {
  queryInput.value = "삼성전자";
  searchCompanies("삼성전자");
});

exampleQueryButtons.forEach((button) => {
  button.addEventListener("click", () => {
    searchCompanies(button.dataset.exampleQuery || "");
  });
});

compareTrayLink?.addEventListener("click", (event) => {
  if (compareTrayLink.getAttribute("aria-disabled") === "true") {
    event.preventDefault();
    compareTrayStatus.textContent = "기업을 1개 더 선택해주세요.";
  }
});

updateCompareTray();

recentQueryList?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-recent-query]");
  if (!button) return;
  searchCompanies(button.dataset.recentQuery || "");
});

renderRecentSearches();

const restoredQuery = new URLSearchParams(window.location.search).get("q");
if (restoredQuery) {
  searchCompanies(restoredQuery);
}
