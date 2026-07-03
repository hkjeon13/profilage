const profileTitle = document.querySelector("#profile-title");
const profileSubtitle = document.querySelector("#profile-subtitle");
const profileDetail = document.querySelector("#profile-detail");
const profileCard = document.querySelector(".company-profile-card");

const infoUrl = "/api/company/get_company_info";
const stockUrl = "/api/company/get_stock_price";
const financialReportOptions = [
  ["11011", "사업보고서"],
  ["11012", "반기보고서"],
  ["11013", "1분기보고서"],
  ["11014", "3분기보고서"],
];
const financialStatementOptions = [
  ["CFS", "연결재무제표"],
  ["OFS", "별도재무제표"],
];

function normalizeItems(payload) {
  const item = payload?.body?.items?.item;
  if (!item) return [];
  return Array.isArray(item) ? item : [item];
}

function firstItem(payload) {
  return normalizeItems(payload)[0] || {};
}

function text(value, fallback = "-") {
  return value === undefined || value === null || value === "" ? fallback : value;
}

function initials(value) {
  const source = text(value, "P").replace(/\(.*?\)/g, "").trim();
  const koreanInitials = Array.from(source).filter((char) => /[가-힣A-Za-z0-9]/.test(char));
  return (koreanInitials.slice(0, 2).join("") || "P").toUpperCase();
}

function itemCount(payload) {
  return normalizeItems(payload).length;
}

function compactDate(value) {
  if (!value) return "-";
  const raw = String(value).replaceAll("-", "");
  if (/^\d{8}$/.test(raw)) {
    return `${raw.slice(0, 4)}.${raw.slice(4, 6)}.${raw.slice(6, 8)}`;
  }
  return value;
}

function homepageUrl(value) {
  const url = text(value, "");
  if (!url) return "";
  return /^https?:\/\//i.test(url) ? url : `https://${url}`;
}

function formatNumber(value) {
  if (value === undefined || value === null || value === "") return "-";
  const numeric = Number(String(value).replaceAll(",", ""));
  return Number.isFinite(numeric) ? numeric.toLocaleString("ko-KR") : value;
}

function formatFinancialAmount(value, currency = "KRW") {
  if (value === undefined || value === null || value === "") return "-";
  const amount = Number(String(value).replaceAll(",", ""));
  if (!Number.isFinite(amount)) return value;
  const normalizedCurrency = (currency || "KRW").toUpperCase();

  if (normalizedCurrency !== "KRW") {
    try {
      return new Intl.NumberFormat("ko-KR", {
        notation: "compact",
        maximumFractionDigits: 1,
        style: "currency",
        currency: normalizedCurrency,
        currencyDisplay: "narrowSymbol",
      }).format(amount);
    } catch {
      return `${normalizedCurrency} ${new Intl.NumberFormat("ko-KR", {
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(amount)}`;
    }
  }

  const sign = amount < 0 ? "-" : "";
  const absolute = Math.abs(amount);
  const jo = Math.floor(absolute / 1_000_000_000_000);
  const eok = Math.floor((absolute % 1_000_000_000_000) / 100_000_000);
  const man = Math.floor((absolute % 100_000_000) / 10_000);

  if (jo > 0) {
    return `${sign}${jo.toLocaleString("ko-KR")}조${eok > 0 ? ` ${eok.toLocaleString("ko-KR")}억원` : "원"}`;
  }
  if (eok > 0) {
    return `${sign}${eok.toLocaleString("ko-KR")}억${man > 0 ? ` ${man.toLocaleString("ko-KR")}만원` : "원"}`;
  }
  if (man > 0) {
    return `${sign}${man.toLocaleString("ko-KR")}만원`;
  }
  return `${sign}${absolute.toLocaleString("ko-KR")}원`;
}

function formatChartDate(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toLocaleDateString("ko-KR", {
      month: "numeric",
      day: "numeric",
    });
  }
  return String(value).split(",")[0];
}

function formatTooltipDate(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toLocaleDateString("ko-KR", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }
  return String(value).split(",")[0];
}

function latestBusinessYear() {
  return String(new Date().getFullYear() - 1);
}

function financialYearOptions(selectedYear) {
  const latest = new Date().getFullYear();
  const years = Array.from({ length: 10 }, (_, index) => String(latest - index));
  if (selectedYear && !years.includes(selectedYear)) {
    years.unshift(selectedYear);
  }
  return years;
}

function getSelectedFinancialQuery(searchParams) {
  return {
    businessYear: searchParams.get("business_year") || latestBusinessYear(),
    reportCode: searchParams.get("report_code") || "11011",
    fsDivision: searchParams.get("fs_division") || "CFS",
  };
}

function optionLabel(options, value) {
  return options.find(([optionValue]) => optionValue === value)?.[1] || value;
}

function financialDetailUrl(crno, selected) {
  const endpoint = new URL("/profile", window.location.origin);
  endpoint.searchParams.set("crno", crno);
  endpoint.searchParams.set("view", "financials");
  if (selected?.business_year) {
    endpoint.searchParams.set("business_year", selected.business_year);
  }
  if (selected?.report_code) {
    endpoint.searchParams.set("report_code", selected.report_code);
  }
  if (selected?.fs_division) {
    endpoint.searchParams.set("fs_division", selected.fs_division);
  }
  return `${endpoint.pathname}${endpoint.search}`;
}

function renderStockChart(stock) {
  const points = (stock?.graph || [])
    .map((point) => ({
      price: Number(point.price),
      date: point.date,
      volume: Number(point.volume),
    }))
    .filter((point) => Number.isFinite(point.price));

  if (points.length < 2) return "";

  const width = 640;
  const height = 180;
  const paddingX = 14;
  const paddingY = 18;
  const prices = points.map((point) => point.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const chartWidth = width - paddingX * 2;
  const chartHeight = height - paddingY * 2;
  const coordinates = points.map((point, index) => {
    const x =
      paddingX + (index / Math.max(points.length - 1, 1)) * chartWidth;
    const y = paddingY + ((max - point.price) / range) * chartHeight;
    return { x, y, price: point.price, date: point.date };
  });
  const interactionPoints = coordinates.map((point, index) => ({
    index,
    x: Number(point.x.toFixed(2)),
    y: Number(point.y.toFixed(2)),
    price: point.price,
    date: point.date,
    volume: points[index].volume,
  }));
  const linePath = coordinates
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
  const areaPath = `${linePath} L ${coordinates.at(-1).x.toFixed(2)} ${height - paddingY} L ${coordinates[0].x.toFixed(2)} ${height - paddingY} Z`;
  const trendClass =
    coordinates.at(-1).price >= coordinates[0].price ? "is-up" : "is-down";

  return `
    <div class="stock-chart" aria-label="1개월 주가 차트" data-chart-points="${encodeURIComponent(JSON.stringify(interactionPoints))}" data-chart-width="${width}" data-chart-last-index="${points.length - 1}">
      <div class="stock-chart-tooltip" role="status" aria-live="polite">
        <strong>${formatChartDate(points.at(-1).date)}</strong>
        <span>${formatNumber(points.at(-1).price)} KRW</span>
      </div>
      <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="1개월 주가 추이" tabindex="0">
        <path class="stock-chart-grid" d="M ${paddingX} ${height / 2} H ${width - paddingX}" />
        <path class="stock-chart-area ${trendClass}" d="${areaPath}" />
        <path class="stock-chart-line ${trendClass}" d="${linePath}" />
        <line class="stock-chart-guide" x1="${coordinates.at(-1).x.toFixed(2)}" y1="${paddingY}" x2="${coordinates.at(-1).x.toFixed(2)}" y2="${height - paddingY}" />
        <circle class="stock-chart-dot ${trendClass}" cx="${coordinates.at(-1).x.toFixed(2)}" cy="${coordinates.at(-1).y.toFixed(2)}" r="4" />
        <rect class="stock-chart-hit-area" x="0" y="0" width="${width}" height="${height}" />
      </svg>
      <div class="stock-chart-meta">
        <span class="stock-chart-meta-start">${formatChartDate(points[0].date)}</span>
        <span>${formatNumber(min)} - ${formatNumber(max)}</span>
        <span class="stock-chart-meta-end">${formatChartDate(points.at(-1).date)}</span>
      </div>
    </div>
  `;
}

function updateStockChartSelection(chart, point) {
  const tooltip = chart.querySelector(".stock-chart-tooltip");
  const guide = chart.querySelector(".stock-chart-guide");
  const dot = chart.querySelector(".stock-chart-dot");
  if (!tooltip || !guide || !dot) return;

  const chartWidth = Number(chart.dataset.chartWidth || 640);
  const tooltipPosition = Math.min(Math.max((point.x / chartWidth) * 100, 15), 85);
  const volumeText = Number.isFinite(point.volume)
    ? `<small>거래량 ${formatNumber(point.volume)}</small>`
    : "";

  tooltip.style.left = `${tooltipPosition}%`;
  tooltip.innerHTML = `
    <strong>${formatTooltipDate(point.date)}</strong>
    <span>${formatNumber(point.price)} KRW</span>
    ${volumeText}
  `;
  guide.setAttribute("x1", point.x);
  guide.setAttribute("x2", point.x);
  dot.setAttribute("cx", point.x);
  dot.setAttribute("cy", point.y);
  chart.classList.add("is-active");
  chart.classList.toggle("is-start-selected", point.index === 0);
  chart.classList.toggle(
    "is-end-selected",
    point.index === Number(chart.dataset.chartLastIndex),
  );
}

function setupStockChartInteractions() {
  document.querySelectorAll(".stock-chart").forEach((chart) => {
    const svg = chart.querySelector("svg");
    if (!svg || !chart.dataset.chartPoints) return;

    const points = JSON.parse(decodeURIComponent(chart.dataset.chartPoints));
    if (!points.length) return;

    const selectNearestPoint = (clientX) => {
      if (!Number.isFinite(clientX)) return;
      const rect = svg.getBoundingClientRect();
      const chartWidth = Number(chart.dataset.chartWidth || 640);
      const x = ((clientX - rect.left) / rect.width) * chartWidth;
      const nearest = points.reduce((current, point) =>
        Math.abs(point.x - x) < Math.abs(current.x - x) ? point : current,
      );
      updateStockChartSelection(chart, nearest);
    };
    const selectFromTouch = (event) => {
      selectNearestPoint(event.touches?.[0]?.clientX);
    };

    updateStockChartSelection(chart, points.at(-1));

    chart.addEventListener("pointermove", (event) => {
      selectNearestPoint(event.clientX);
    });
    chart.addEventListener("pointerdown", (event) => {
      try {
        chart.setPointerCapture?.(event.pointerId);
      } catch {
        // Synthetic and some mobile browser pointer events cannot be captured.
      }
      selectNearestPoint(event.clientX);
    });
    chart.addEventListener("mousemove", (event) => {
      selectNearestPoint(event.clientX);
    });
    chart.addEventListener("mousedown", (event) => {
      selectNearestPoint(event.clientX);
    });
    chart.addEventListener("click", (event) => {
      selectNearestPoint(event.clientX);
    });
    chart.addEventListener("touchstart", selectFromTouch, { passive: true });
    chart.addEventListener("touchmove", selectFromTouch, { passive: true });
    svg.addEventListener("focus", () => {
      updateStockChartSelection(chart, points.at(-1));
    });
    svg.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const activeX = Number(chart.querySelector(".stock-chart-dot")?.getAttribute("cx"));
      const currentIndex = points.findIndex((point) => point.x === activeX);
      const fallbackIndex = points.length - 1;
      const nextIndex =
        event.key === "ArrowLeft"
          ? Math.max((currentIndex < 0 ? fallbackIndex : currentIndex) - 1, 0)
          : Math.min((currentIndex < 0 ? fallbackIndex : currentIndex) + 1, points.length - 1);
      updateStockChartSelection(chart, points[nextIndex]);
    });
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

function renderProfileSkeleton() {
  profileCard?.classList.add("is-loading");
  profileTitle.innerHTML = `<span class="skeleton-line skeleton-hero-title"></span>`;
  profileSubtitle.innerHTML = `<span class="skeleton-line skeleton-hero-subtitle"></span>`;
  profileDetail.innerHTML = `
    <div class="company-overview-grid" aria-hidden="true">
      <div class="company-main-column">
        <article class="info-block skeleton-block">
          <span class="skeleton-line skeleton-section-title"></span>
          <span class="skeleton-line"></span>
          <span class="skeleton-line"></span>
          <span class="skeleton-line skeleton-wide"></span>
        </article>
        <article class="info-block skeleton-block">
          <span class="skeleton-line skeleton-section-title"></span>
          <span class="skeleton-line skeleton-price"></span>
          <span class="skeleton-line skeleton-short"></span>
          <span class="skeleton-chart"></span>
        </article>
      </div>
      <aside class="company-side-panel">
      ${Array.from({ length: 2 })
        .map(
          () => `
            <article class="info-block skeleton-block">
              <span class="skeleton-line skeleton-section-title"></span>
              <span class="skeleton-line"></span>
              <span class="skeleton-line"></span>
              <span class="skeleton-line skeleton-short"></span>
            </article>
          `,
        )
        .join("")}
      </aside>
    </div>
  `;
}

function renderError(message) {
  profileCard?.classList.remove("is-loading");
  profileTitle.textContent = "기업 프로필을 열 수 없습니다";
  profileSubtitle.textContent = message;
  profileDetail.innerHTML = `
    <div class="empty-state">
      <span class="empty-kicker">Error</span>
      <p>${message}</p>
    </div>
  `;
  setupStockChartInteractions();
}

function renderDartDisclosures(disclosures) {
  const items = (disclosures?.list || []).slice(0, 5);
  if (!items.length) return "";
  const crno = new URLSearchParams(window.location.search).get("crno");

  return `
    <article class="info-block full">
      <div class="block-heading">
        <h3>최근 공시</h3>
        <a href="/profile?crno=${encodeURIComponent(crno)}&view=disclosures">더보기</a>
      </div>
      <ul class="disclosure-list">
        ${items
          .map(
            (item) => `
              <li>
                <a href="${text(item.viewer_url, "#")}" target="_blank" rel="noreferrer">${text(item.report_nm)}</a>
                <span>${text(item.rcept_dt)} · ${text(item.flr_nm || item.corp_name)}</span>
              </li>
            `,
          )
          .join("")}
      </ul>
    </article>
  `;
}

function financialSummaryItems(accounts) {
  const preferred = new Set(["매출액", "영업이익", "당기순이익", "자산총계", "부채총계", "자본총계"]);
  return Array.from(
    (accounts?.list || [])
      .filter((item) => preferred.has(item.account_nm))
      .reduce((itemsByName, item) => {
        if (!itemsByName.has(item.account_nm)) {
          itemsByName.set(item.account_nm, item);
        }
        return itemsByName;
      }, new Map())
      .values(),
  ).slice(0, 6);
}

function renderFinancialSummaryPanel({ report, key, isActive }) {
  const selected = report?.selected;
  const accounts = report?.accounts;
  const items = financialSummaryItems(accounts);
  if (!items.length) return "";
  const crno = new URLSearchParams(window.location.search).get("crno");
  const subtitle = selected
    ? `${selected.business_year} · ${selected.report_name} · ${optionLabel(financialStatementOptions, selected.fs_division)}`
    : "재무정보";

  return `
    <div class="financial-summary-panel ${isActive ? "is-active" : ""}" data-financial-panel="${key}" ${isActive ? "" : "hidden"}>
      <p class="financial-summary-meta">${subtitle}</p>
      <dl class="kv">
        ${items
          .map(
            (item) => `
              <dt>${text(item.account_nm)}</dt>
              <dd>${formatFinancialAmount(item.thstrm_amount, item.currency)}</dd>
            `,
          )
          .join("")}
      </dl>
      <a class="text-link" href="${financialDetailUrl(crno, selected)}">더보기</a>
    </div>
  `;
}

function renderDartFinancialAccounts(info) {
  const quarterReport = info.dart_latest_quarter_financial_accounts;
  const annualReport =
    info.dart_latest_annual_financial_accounts || {
      selected: null,
      accounts: info.dart_financial_accounts,
    };
  const hasQuarter = Boolean(quarterReport?.accounts?.list?.length);
  const hasAnnual = Boolean(annualReport?.accounts?.list?.length);
  if (!hasQuarter && !hasAnnual) return "";
  const activeKey = hasQuarter ? "quarter" : "annual";
  const crno = new URLSearchParams(window.location.search).get("crno");

  return `
    <article class="info-block financial-summary">
      <div class="block-heading">
        <h3>재무 요약</h3>
      </div>
      <div class="summary-tabs" role="tablist" aria-label="재무제표 기간">
        <button type="button" class="${activeKey === "quarter" ? "is-active" : ""}" data-financial-tab="quarter" ${hasQuarter ? "" : "disabled"}>
          분기
        </button>
        <button type="button" class="${activeKey === "annual" ? "is-active" : ""}" data-financial-tab="annual" ${hasAnnual ? "" : "disabled"}>
          연간
        </button>
      </div>
      ${renderFinancialSummaryPanel({ report: quarterReport, key: "quarter", isActive: activeKey === "quarter" })}
      ${renderFinancialSummaryPanel({ report: annualReport, key: "annual", isActive: activeKey === "annual" })}
    </article>
  `;
}

function setupFinancialSummaryTabs() {
  document.querySelectorAll(".financial-summary").forEach((summary) => {
    const tabs = Array.from(summary.querySelectorAll("[data-financial-tab]"));
    const panels = Array.from(summary.querySelectorAll("[data-financial-panel]"));
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const key = tab.dataset.financialTab;
        tabs.forEach((item) => item.classList.toggle("is-active", item === tab));
        panels.forEach((panel) => {
          const isActive = panel.dataset.financialPanel === key;
          panel.classList.toggle("is-active", isActive);
          panel.hidden = !isActive;
        });
      });
    });
  });
}

function renderSubpageHeader({ kicker, title, subtitle, crno }) {
  profileTitle.textContent = title;
  profileSubtitle.textContent = subtitle;
  return `
    <div class="detail-header subpage-header">
      <a class="back-link" href="/profile?crno=${encodeURIComponent(crno)}">기업 프로필로 돌아가기</a>
      <p>${kicker}</p>
      <h2>${title}</h2>
      <span>${subtitle}</span>
    </div>
  `;
}

function renderFinancialControls({ crno, selected }) {
  return `
    <form class="subpage-controls" action="/profile" method="get">
      <input type="hidden" name="crno" value="${text(crno, "")}" />
      <input type="hidden" name="view" value="financials" />
      <label>
        <span>사업연도</span>
        <select name="business_year" onchange="this.form.submit()">
          ${financialYearOptions(selected.businessYear)
            .map(
              (year) => `
                <option value="${year}" ${year === selected.businessYear ? "selected" : ""}>${year}</option>
              `,
            )
            .join("")}
        </select>
      </label>
      <label>
        <span>보고서</span>
        <select name="report_code" onchange="this.form.submit()">
          ${financialReportOptions
            .map(
              ([value, label]) => `
                <option value="${value}" ${value === selected.reportCode ? "selected" : ""}>${label}</option>
              `,
            )
            .join("")}
        </select>
      </label>
      <label>
        <span>기준</span>
        <select name="fs_division" onchange="this.form.submit()">
          ${financialStatementOptions
            .map(
              ([value, label]) => `
                <option value="${value}" ${value === selected.fsDivision ? "selected" : ""}>${label}</option>
              `,
            )
            .join("")}
        </select>
      </label>
    </form>
  `;
}

function renderFinancialsPage({ accountsPayload, outline, crno, selected }) {
  const accounts = accountsPayload?.list || [];
  const grouped = accounts.reduce((groups, item) => {
    const key = item.sj_nm || "재무제표";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
    return groups;
  }, new Map());

  profileDetail.innerHTML = `
    ${renderSubpageHeader({
      kicker: "DART 재무정보",
      title: `${text(outline.corpNm, "기업")} 재무제표`,
      subtitle: `${selected.businessYear} · ${optionLabel(financialReportOptions, selected.reportCode)} · ${optionLabel(financialStatementOptions, selected.fsDivision)}`,
      crno,
    })}
    <div class="detail-body subpage-body">
      <article class="info-block full controls-block">
        ${renderFinancialControls({ crno, selected })}
      </article>
      ${Array.from(grouped.entries())
        .map(
          ([statementName, items]) => `
            <article class="info-block full">
              <h3>${statementName}</h3>
              <dl class="kv financial-list">
                ${items
                  .map(
                    (item) => `
                      <dt>${text(item.account_nm)}</dt>
                      <dd>
                        <strong>${formatFinancialAmount(item.thstrm_amount, item.currency)}</strong>
                        <span>${text(item.thstrm_nm)} · ${text(item.currency)}</span>
                      </dd>
                    `,
                  )
                  .join("")}
              </dl>
            </article>
          `,
        )
        .join("") || `
          <article class="info-block full">
            <h3>재무정보</h3>
            <p class="empty-copy">표시할 재무제표 항목이 없습니다.</p>
          </article>
        `}
    </div>
  `;
}

function renderDisclosuresPage({ disclosures, outline, crno }) {
  const items = disclosures?.list || [];
  profileDetail.innerHTML = `
    ${renderSubpageHeader({
      kicker: "DART 공시",
      title: `${text(outline.corpNm, "기업")} 공시`,
      subtitle: `${items.length.toLocaleString("ko-KR")}개 공시`,
      crno,
    })}
    <div class="detail-body subpage-body">
      <article class="info-block full">
        <h3>공시 목록</h3>
        <ul class="disclosure-list disclosure-list-large">
          ${items
            .map(
              (item) => `
                <li>
                  <a href="${text(item.viewer_url, "#")}" target="_blank" rel="noreferrer">${text(item.report_nm)}</a>
                  <span>${text(item.rcept_dt)} · ${text(item.flr_nm || item.corp_name)} · ${text(item.rcept_no)}</span>
                </li>
              `,
            )
            .join("") || `<li><span>표시할 공시가 없습니다.</span></li>`}
        </ul>
      </article>
    </div>
  `;
}

function renderCompanyDetail({ info, outline, listed, stock }) {
  const summary = stock?.summary || {};
  const price = summary.price || summary.extracted_price;
  const change = summary.price_movement?.percentage || summary.price_movement?.value;
  const crno = new URLSearchParams(window.location.search).get("crno");
  const homepage = homepageUrl(outline.enpHmpgUrl);
  const affiliateCount = itemCount(info.affiliate);
  const subsidiaryCount = itemCount(info.cons_subs_comp);
  const market = text(listed.mrktCtg || outline.corpRegMrktDcdNm, "비상장/정보 없음");
  const logo = document.querySelector(".company-logo-box");

  profileTitle.textContent = text(outline.corpNm, "기업 프로필");
  profileSubtitle.textContent = text(outline.corpEnsnNm, "영문명 정보 없음");
  profileCard?.classList.remove("is-loading");
  if (logo) {
    logo.textContent = initials(outline.corpNm);
  }

  profileDetail.innerHTML = `
    <div class="company-overview-grid">
      <div class="company-main-column">
        <article class="info-block company-about-card">
          <div class="block-heading">
            <h3>기업 개요</h3>
            ${homepage ? `<a href="${homepage}" target="_blank" rel="noreferrer">홈페이지</a>` : ""}
          </div>
          <p class="company-summary">
            ${text(outline.corpNm, "이 기업")}은 ${market} 시장 정보와 공공데이터 기업개요를 기준으로 정리된 프로필입니다.
            법인등록번호, 대표자, 설립일, DART 공시와 KRX 종목 정보를 한 화면에서 확인할 수 있습니다.
          </p>
          <dl class="company-facts">
            <div><dt>대표자</dt><dd>${text(outline.enpRprFnm)}</dd></div>
            <div><dt>설립일</dt><dd>${compactDate(outline.enpEstbDt)}</dd></div>
            <div><dt>법인등록번호</dt><dd>${text(outline.crno || crno)}</dd></div>
            <div><dt>사업자번호</dt><dd>${text(outline.bzno)}</dd></div>
          </dl>
        </article>

        <article class="info-block company-market-card">
          <div class="block-heading">
            <h3>상장 및 주가</h3>
            <span class="market-pill">${market}</span>
          </div>
          <div class="price-row">
            <div>
              <span class="price-label">${text(listed.itmsNm || outline.corpNm, "종목")}</span>
              <div class="price">${formatNumber(price)}</div>
            </div>
            <div class="price-meta">${text(change, "변동 정보 없음")}</div>
          </div>
          ${renderStockChart(stock)}
        </article>

        ${renderDartFinancialAccounts(info)}
        ${renderDartDisclosures(info.dart_disclosures)}

        <article class="info-block company-address-card">
          <h3>주소</h3>
          <p>${text(outline.enpBsadr, "주소 정보 없음")}</p>
        </article>
      </div>

      <aside class="company-side-panel" aria-label="기업 요약">
        <article class="info-block company-side-card">
          <h3>핵심 정보</h3>
          <dl class="side-list">
            <div><dt>시장</dt><dd>${market}</dd></div>
            <div><dt>단축코드</dt><dd>${text(listed.srtnCd)}</dd></div>
            <div><dt>ISIN</dt><dd>${text(listed.isinCd)}</dd></div>
            <div><dt>업종</dt><dd>${text(outline.enpMainBizNm || listed.itmsNm, "정보 없음")}</dd></div>
          </dl>
        </article>

        <article class="info-block company-side-card">
          <h3>관계 회사</h3>
          <div class="network-row">
            <strong>${affiliateCount.toLocaleString("ko-KR")}</strong>
            <span>계열회사</span>
          </div>
          <div class="network-row">
            <strong>${subsidiaryCount.toLocaleString("ko-KR")}</strong>
            <span>연결대상 종속기업</span>
          </div>
        </article>

      </aside>
    </div>
  `;
  setupStockChartInteractions();
  setupFinancialSummaryTabs();
}

async function loadProfile() {
  const searchParams = new URLSearchParams(window.location.search);
  const crno = searchParams.get("crno");
  const view = searchParams.get("view");
  if (!crno) {
    renderError("법인등록번호가 필요합니다.");
    return;
  }

  renderProfileSkeleton();

  try {
    const info = await fetchJson(infoUrl, {
      corporate_registration_number: crno,
      page: 1,
      per_page: 10,
    });
    const outline = firstItem(info.corp_outline);
    const listed = firstItem(info.krx_listed_item);
    let stock = null;

    if (view === "financials") {
      const selected = getSelectedFinancialQuery(searchParams);
      const corpCode = info.dart_corp_code?.match?.corp_code;
      const accountsPayload = corpCode
        ? await fetchJson("/api/company/get_dart_financial_accounts", {
            corp_code: corpCode,
            business_year: selected.businessYear,
            report_code: selected.reportCode,
            fs_division: selected.fsDivision,
          }).catch(() => info.dart_financial_accounts)
        : info.dart_financial_accounts;
      renderFinancialsPage({ accountsPayload, outline, crno, selected });
      return;
    }

    if (view === "disclosures") {
      const corpCode = info.dart_corp_code?.match?.corp_code;
      const disclosures = corpCode
        ? await fetchJson("/api/company/get_dart_disclosures", {
            corp_code: corpCode,
            page: 1,
            per_page: 30,
          }).catch(() => info.dart_disclosures)
        : info.dart_disclosures;
      renderDisclosuresPage({ disclosures, outline, crno });
      return;
    }

    if (listed.srtnCd) {
      stock = await fetchJson(stockUrl, {
        stock_code: listed.srtnCd.replace(/^A/, ""),
        exchange: "KRX",
        language: "ko",
        window: "1M",
        corporate_registration_number: crno,
      }).catch(() => null);
    }

    renderCompanyDetail({
      info,
      outline,
      listed,
      stock,
    });
  } catch (error) {
    renderError(error.message);
  }
}

loadProfile();
