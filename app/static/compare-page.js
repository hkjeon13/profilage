const COMPARE_STORAGE_KEY = "profilage.compareCompanies";
const MAX_COMPARE_COMPANIES = 5;
const compareRoot = document.querySelector("#compare-root");
const compareDetail = document.querySelector("#compare-detail");
const infoUrl = compareRoot?.dataset.infoUrl || "/api/company/get_company_info";
const stockUrl = compareRoot?.dataset.stockUrl || "/api/company/get_stock_price";

const metricGroups = [
  {
    title: "기본 정보",
    rows: [
      { label: "시장", key: "market" },
      { label: "업종", key: "industry" },
      { label: "설립일", key: "founded" },
      { label: "직원 수", key: "employees", numeric: true, higherIsBetter: false },
    ],
  },
  {
    title: "재무 요약",
    rows: [
      { label: "자산총계", key: "자산총계", numeric: true, source: "financial" },
      { label: "부채총계", key: "부채총계", numeric: true, source: "financial", higherIsBetter: false },
      { label: "자본총계", key: "자본총계", numeric: true, source: "financial" },
      { label: "매출액", key: "매출액", numeric: true, source: "financial" },
      { label: "영업이익", key: "영업이익", numeric: true, source: "financial" },
      { label: "당기순이익", key: "당기순이익", numeric: true, source: "financial" },
    ],
  },
  {
    title: "비율",
    rows: [
      { label: "부채비율", key: "부채비율", numeric: true, source: "ratio", higherIsBetter: false },
      { label: "영업이익률", key: "영업이익률", numeric: true, source: "ratio" },
      { label: "ROE", key: "ROE", numeric: true, source: "ratio" },
      { label: "ROA", key: "ROA", numeric: true, source: "ratio" },
    ],
  },
  {
    title: "주가",
    rows: [
      { label: "현재가", key: "stockPrice", numeric: true },
      { label: "1개월 수익률", key: "stockReturn1M", numeric: true },
      { label: "6개월 수익률", key: "stockReturn6M", numeric: true },
    ],
  },
];

function normalizeItems(payload) {
  const item = payload?.body?.items?.item;
  if (!item) return [];
  return Array.isArray(item) ? item : [item];
}

function firstItem(payload) {
  return normalizeItems(payload)[0] || {};
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function attr(value) {
  return escapeHtml(value);
}

function text(value, fallback = "-") {
  return value === undefined || value === null || value === "" ? fallback : String(value);
}

function numeric(value) {
  if (value === undefined || value === null || value === "") return null;
  const parsed = Number(String(value).replaceAll(",", "").replaceAll("%", "").trim());
  return Number.isFinite(parsed) ? parsed : null;
}

function compactDate(value) {
  const raw = String(value || "");
  if (/^\d{8}$/.test(raw)) {
    return `${raw.slice(0, 4)}.${raw.slice(4, 6)}.${raw.slice(6, 8)}`;
  }
  return text(value);
}

function formatNumber(value) {
  const parsed = numeric(value);
  if (parsed === null) return text(value);
  return parsed.toLocaleString("ko-KR");
}

function formatFinancialAmount(value, currency) {
  const parsed = numeric(value);
  if (parsed === null) return text(value);
  if (currency && currency !== "KRW") return `${parsed.toLocaleString("ko-KR")} ${currency}`;
  const abs = Math.abs(parsed);
  if (abs >= 1000000000000) return `${(parsed / 1000000000000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}조`;
  if (abs >= 100000000) return `${(parsed / 100000000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}억`;
  return parsed.toLocaleString("ko-KR");
}

async function fetchJson(url, params) {
  const endpoint = new URL(url, window.location.origin);
  Object.entries(params || {}).forEach(([key, value]) => {
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

function compareStorageItems() {
  try {
    const parsed = JSON.parse(localStorage.getItem(COMPARE_STORAGE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function requestedCrnos() {
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.getAll("crno").flatMap((value) => value.split(",")).map((value) => value.trim());
  const fromStorage = compareStorageItems().map((item) => item.crno);
  return Array.from(new Set([...fromUrl, ...fromStorage].filter(Boolean))).slice(0, MAX_COMPARE_COMPANIES);
}

function financialMap(info) {
  const accounts =
    info.dart_latest_annual_financial_accounts?.accounts?.list ||
    info.dart_financial_accounts?.list ||
    [];
  return accounts.reduce((items, account) => {
    if (!items.has(account.account_nm)) items.set(account.account_nm, account);
    return items;
  }, new Map());
}

function ratioMap(info) {
  return (info.dart_insights?.ratios?.items || []).reduce((items, item) => {
    items.set(item.name, item.value);
    return items;
  }, new Map());
}

function stockReturn(stock) {
  const points = stock?.graph || [];
  const first = numeric(points[0]?.price);
  const last = numeric(points.at(-1)?.price);
  if (first === null || last === null || first === 0) return null;
  return ((last - first) / Math.abs(first)) * 100;
}

async function loadStock(listed, crno, windowName) {
  const stockCode = String(listed.srtnCd || "").replace(/^A/, "");
  if (!stockCode) return null;
  return fetchJson(stockUrl, {
    stock_code: stockCode,
    exchange: "KRX",
    language: "ko",
    window: windowName,
    corporate_registration_number: crno,
  }).catch(() => null);
}

async function loadCompany(crno) {
  const info = await fetchJson(infoUrl, {
    corporate_registration_number: crno,
    page: 1,
    per_page: 10,
  });
  const outline = firstItem(info.corp_outline);
  const listed = firstItem(info.krx_listed_item);
  const [stock1M, stock6M] = await Promise.all([
    loadStock(listed, crno, "1M"),
    loadStock(listed, crno, "6M"),
  ]);
  const accounts = financialMap(info);
  const ratios = ratioMap(info);
  const stockSummary = stock1M?.summary || stock6M?.summary || {};
  return {
    crno,
    name: outline.corpNm || listed.itmsNm || "기업명 정보 없음",
    subtitle: outline.corpEnsnNm || listed.isinCd || crno,
    values: {
      market: listed.mrktCtg || outline.corpRegMrktDcdNm,
      industry: outline.enpMainBizNm || outline.sicNm || listed.itmsNm,
      founded: compactDate(outline.enpEstbDt),
      employees: outline.enpEmpeCnt,
      stockPrice: stockSummary.price || stockSummary.extracted_price,
      stockReturn1M: stockReturn(stock1M),
      stockReturn6M: stockReturn(stock6M),
    },
    financialValues: accounts,
    ratioValues: ratios,
    basis:
      info.dart_latest_annual_financial_accounts?.selected ||
      info.dart_insights?.basis ||
      null,
  };
}

function metricValue(company, row) {
  if (row.source === "financial") {
    return company.financialValues.get(row.key)?.thstrm_amount;
  }
  if (row.source === "ratio") {
    return company.ratioValues.get(row.key);
  }
  return company.values[row.key];
}

function formattedMetricValue(company, row) {
  const value = metricValue(company, row);
  if (row.source === "financial") {
    const account = company.financialValues.get(row.key);
    return formatFinancialAmount(value, account?.currency);
  }
  if (row.key === "stockReturn1M" || row.key === "stockReturn6M") {
    const parsed = numeric(value);
    if (parsed === null) return "-";
    const sign = parsed > 0 ? "+" : "";
    return `${sign}${parsed.toFixed(1)}%`;
  }
  return row.numeric ? formatNumber(value) : text(value);
}

function bestCompanyCrnos(companies, row) {
  if (!row.numeric) return new Set();
  const scored = companies
    .map((company) => ({ crno: company.crno, value: numeric(metricValue(company, row)) }))
    .filter((item) => item.value !== null);
  if (!scored.length) return new Set();
  const best = row.higherIsBetter === false
    ? Math.min(...scored.map((item) => item.value))
    : Math.max(...scored.map((item) => item.value));
  return new Set(scored.filter((item) => item.value === best).map((item) => item.crno));
}

function renderCompanyChips(companies) {
  return `
    <div class="compare-company-chips">
      ${companies
        .map(
          (company) => `
            <a class="compare-company-chip" href="/profile?crno=${encodeURIComponent(company.crno)}">
              <strong>${escapeHtml(company.name)}</strong>
              <span>${escapeHtml(company.subtitle)}</span>
            </a>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderCompareTable(companies) {
  return metricGroups
    .map(
      (group) => `
        <article class="info-block compare-block">
          <div class="block-heading">
            <h3>${escapeHtml(group.title)}</h3>
          </div>
          <div class="compare-table-wrap">
            <table class="compare-table">
              <thead>
                <tr>
                  <th>항목</th>
                  ${companies.map((company) => `<th>${escapeHtml(company.name)}</th>`).join("")}
                </tr>
              </thead>
              <tbody>
                ${group.rows
                  .map((row) => {
                    const bestCrnos = bestCompanyCrnos(companies, row);
                    return `
                      <tr>
                        <th>${escapeHtml(row.label)}</th>
                        ${companies
                          .map(
                            (company) => `
                              <td class="${bestCrnos.has(company.crno) ? "compare-best" : ""}">
                                ${escapeHtml(formattedMetricValue(company, row))}
                              </td>
                            `,
                          )
                          .join("")}
                      </tr>
                    `;
                  })
                  .join("")}
              </tbody>
            </table>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderComparePage(companies) {
  if (companies.length < 2) {
    compareDetail.innerHTML = `
      <article class="info-block compare-empty">
        <h3>비교할 기업을 더 추가해주세요</h3>
        <p>최소 2개 기업을 선택하면 비교표가 표시됩니다.</p>
        <a class="primary-link-button" href="/">기업 검색하기</a>
      </article>
    `;
    return;
  }
  compareDetail.innerHTML = `
    <section class="compare-toolbar info-block">
      <div>
        <h3>선택한 기업 ${companies.length}개</h3>
        <p>재무 수치는 최근 사업보고서 또는 DART 정기보고서 기준입니다. 기준 보고서가 다르면 수치 해석에 주의하세요.</p>
      </div>
      <a class="primary-link-button" href="/">기업 추가</a>
    </section>
    ${renderCompanyChips(companies)}
    ${renderCompareTable(companies)}
  `;
}

async function loadComparePage() {
  const crnos = requestedCrnos();
  if (!crnos.length) {
    renderComparePage([]);
    return;
  }
  compareDetail.innerHTML = `
    <div class="empty-state">
      <span class="empty-kicker">Loading</span>
      <p>비교할 기업 ${crnos.length}개를 불러오는 중입니다.</p>
    </div>
  `;
  try {
    const companies = (await Promise.all(crnos.map((crno) => loadCompany(crno).catch(() => null)))).filter(Boolean);
    renderComparePage(companies);
  } catch (error) {
    compareDetail.innerHTML = `<article class="info-block compare-empty"><p>${escapeHtml(error.message || "비교 정보를 불러오지 못했습니다.")}</p></article>`;
  }
}

loadComparePage();
