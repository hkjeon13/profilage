const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#company-query");
const statusEl = document.querySelector("#search-status");
const resultList = document.querySelector("#result-list");
const detailPanel = document.querySelector("#detail-panel");

const outlineUrl = "/api/company/get_corp_outline";
const listedUrl = "/api/company/get_krx_listed_item";
const infoUrl = "/api/company/get_company_info";
const stockUrl = "/api/company/get_stock_price";

function normalizeItems(payload) {
  const item = payload?.body?.items?.item;
  if (!item) return [];
  return Array.isArray(item) ? item : [item];
}

function text(value, fallback = "-") {
  return value === undefined || value === null || value === "" ? fallback : value;
}

function formatNumber(value) {
  if (value === undefined || value === null || value === "") return "-";
  const numeric = Number(String(value).replaceAll(",", ""));
  return Number.isFinite(numeric) ? numeric.toLocaleString("ko-KR") : value;
}

function setStatus(message) {
  statusEl.textContent = message;
}

function renderEmpty(message) {
  detailPanel.innerHTML = `
    <div class="empty-state">
      <span class="empty-kicker">Company</span>
      <p>${message}</p>
    </div>
  `;
}

function renderResults(items) {
  resultList.innerHTML = "";
  const fragment = document.createDocumentFragment();

  items.forEach((company, index) => {
    const button = document.createElement("button");
    button.className = "result-card";
    button.type = "button";
    button.dataset.crno = company.crno;
    button.innerHTML = `
      <strong>${text(company.corpNm)}</strong>
      <span>법인등록번호 ${text(company.crno)}</span>
      <span>${company.isListed ? `상장 ${text(company.mrktCtg)} · ${text(company.srtnCd)}` : `${text(company.enpRprFnm, "대표자 정보 없음")} · ${text(company.bzno, "사업자등록번호 없음")}`}</span>
    `;
    button.addEventListener("click", () => selectCompany(company, button));
    fragment.appendChild(button);

    if (index === 0) {
      window.requestAnimationFrame(() => button.click());
    }
  });

  resultList.appendChild(fragment);
}

function firstItem(payload) {
  return normalizeItems(payload)[0] || {};
}

function listedNameCandidates(query) {
  const suffixes = [
    "",
    "전자",
    "전기",
    "물산",
    "SDI",
    "에스디에스",
    "중공업",
    "생명보험",
    "화재해상보험",
    "증권",
    "카드",
    "바이오로직스",
    "하이닉스",
    "화학",
  ];

  return suffixes
    .map((suffix) => `${query}${suffix}`)
    .filter((value, index, values) => value && values.indexOf(value) === index);
}

function mergeCompanyResults(outlineItems, listedItems) {
  const companies = new Map();
  const listedMarketNames = new Set(["유가", "코스닥", "코넥스"]);

  listedItems.forEach((item, index) => {
    const key = item.crno || `${item.itmsNm}-${item.srtnCd}`;
    companies.set(key, {
      ...item,
      corpNm: item.corpNm || item.itmsNm,
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
      corpNm: item.corpNm || existing.corpNm || existing.itmsNm,
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

async function fetchJson(url, params) {
  const endpoint = new URL(url, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      endpoint.searchParams.set(key, value);
    }
  });

  const response = await fetch(endpoint);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "요청에 실패했습니다.");
  }
  return response.json();
}

async function searchCompanies(query) {
  setStatus("검색 중...");
  renderEmpty("검색 결과를 불러오는 중입니다.");
  resultList.innerHTML = "";

  try {
    const listedRequests = listedNameCandidates(query).map((itemName) =>
      fetchJson(listedUrl, {
        item_name: itemName,
        page: 1,
        per_page: 1,
      }).catch(() => null),
    );
    const [outlinePayload, ...listedPayloads] = await Promise.all([
      fetchJson(outlineUrl, {
        company_name: query,
        page: 1,
        per_page: 1000,
      }),
      ...listedRequests,
    ]);
    const items = mergeCompanyResults(
      normalizeItems(outlinePayload),
      listedPayloads.flatMap((payload) => normalizeItems(payload)),
    ).slice(0, 20);

    if (items.length === 0) {
      setStatus("검색 결과가 없습니다.");
      renderEmpty("다른 기업명으로 검색해보세요.");
      return;
    }

    setStatus(`${items.length.toLocaleString("ko-KR")}개 결과`);
    renderResults(items);
  } catch (error) {
    setStatus(error.message);
    renderEmpty("기업 정보를 가져오지 못했습니다.");
  }
}

async function selectCompany(company, selectedButton) {
  document
    .querySelectorAll(".result-card")
    .forEach((button) => button.classList.remove("is-active"));
  selectedButton.classList.add("is-active");

  renderCompanySkeleton(company);

  try {
    const info = await fetchJson(infoUrl, {
      corporate_registration_number: company.crno,
      page: 1,
      per_page: 10,
    });
    const outline = firstItem(info.corp_outline);
    const listed = firstItem(info.krx_listed_item);
    let stock = null;

    if (listed.srtnCd) {
      stock = await fetchJson(stockUrl, {
        stock_code: listed.srtnCd.replace(/^A/, ""),
        exchange: "KRX",
        language: "ko",
        window: "1M",
      }).catch(() => null);
    }

    renderCompanyDetail({
      outline: { ...company, ...outline },
      listed,
      stock,
      affiliateCount: text(info.affiliate?.body?.totalCount, "0"),
      subsidiaryCount: text(info.cons_subs_comp?.body?.totalCount, "0"),
    });
  } catch (error) {
    renderCompanyDetail({
      outline: company,
      listed: {},
      stock: null,
      affiliateCount: "-",
      subsidiaryCount: "-",
      error: error.message,
    });
  }
}

function renderCompanySkeleton(company) {
  detailPanel.innerHTML = `
    <div class="detail-header">
      <h2>${text(company.corpNm)}</h2>
      <p>상세 정보를 불러오는 중입니다.</p>
    </div>
    <div class="empty-state">
      <span class="empty-kicker">Loading</span>
    </div>
  `;
}

function renderCompanyDetail({ outline, listed, stock, affiliateCount, subsidiaryCount, error }) {
  const summary = stock?.summary || {};
  const price = summary.price || summary.extracted_price;
  const change = summary.price_movement?.percentage || summary.price_movement?.value;

  detailPanel.innerHTML = `
    <div class="detail-header">
      <h2>${text(outline.corpNm)}</h2>
      <p>${text(outline.corpEnsnNm, "영문명 정보 없음")}</p>
    </div>
    <div class="detail-body">
      <article class="info-block">
        <h3>기업 개요</h3>
        <dl class="kv">
          <dt>법인등록번호</dt><dd>${text(outline.crno)}</dd>
          <dt>대표자</dt><dd>${text(outline.enpRprFnm)}</dd>
          <dt>사업자번호</dt><dd>${text(outline.bzno)}</dd>
          <dt>설립일</dt><dd>${text(outline.enpEstbDt)}</dd>
        </dl>
      </article>
      <article class="info-block">
        <h3>상장 정보</h3>
        <dl class="kv">
          <dt>종목명</dt><dd>${text(listed.itmsNm)}</dd>
          <dt>단축코드</dt><dd>${text(listed.srtnCd)}</dd>
          <dt>시장</dt><dd>${text(listed.mrktCtg)}</dd>
          <dt>ISIN</dt><dd>${text(listed.isinCd)}</dd>
        </dl>
      </article>
      <article class="info-block">
        <h3>주가</h3>
        <div class="price">${formatNumber(price)}</div>
        <div class="price-meta">${text(change, "변동 정보 없음")}</div>
      </article>
      <article class="info-block">
        <h3>관계 정보</h3>
        <dl class="kv">
          <dt>계열사</dt><dd>${affiliateCount}</dd>
          <dt>종속기업</dt><dd>${subsidiaryCount}</dd>
        </dl>
      </article>
      <article class="info-block full">
        <h3>주소</h3>
        <dl class="kv">
          <dt>도로명</dt><dd>${text(outline.enpBsadr)}</dd>
          <dt>상태</dt><dd>${error ? text(error) : "정상 조회"}</dd>
        </dl>
      </article>
    </div>
  `;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) {
    setStatus("기업명을 입력해주세요.");
    return;
  }
  searchCompanies(query);
});
