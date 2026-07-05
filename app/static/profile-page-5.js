const profileTitle = document.querySelector("#profile-title");
const profileSubtitle = document.querySelector("#profile-subtitle");
const profileDetail = document.querySelector("#profile-detail");
const profileCard = document.querySelector(".company-profile-card");
const backLink = document.querySelector(".back-link");

const infoUrl = "/api/company/get_company_info";
const stockUrl = "/api/company/get_stock_price";
const summaryUrl = "/api/company/get_dart_disclosure_summary";
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
const DISCLOSURE_PAGE_SIZE = 30;
const OWNERSHIP_BAR_MAX_HOLDERS = 5;
const COMPARE_STORAGE_KEY = "profilage.compareCompanies";
const MAX_COMPARE_COMPANIES = 5;
const STOCK_WINDOWS = ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"];
const DISCLOSURE_FILTERS = [
  ["", "전체"],
  ["A", "정기공시"],
  ["B", "주요사항"],
  ["C", "발행공시"],
  ["D", "지분공시"],
  ["E", "기타공시"],
];
const DISCLOSURE_EVENT_LABELS = {
  periodic: "정기보고서",
  ownership: "지분/최대주주",
  executive: "임원",
  capital: "자본",
  dividend: "배당",
  audit: "감사/회계",
  other: "기타",
};
const STOCK_MARKER_EVENT_CATEGORIES = new Set(["periodic", "ownership", "capital", "dividend", "audit"]);

function normalizeItems(payload) {
  const item = payload?.body?.items?.item;
  if (!item) return [];
  return Array.isArray(item) ? item : [item];
}

function firstItem(payload) {
  return normalizeItems(payload)[0] || {};
}

function firstCompanyValue(payload, keys) {
  for (const item of normalizeItems(payload)) {
    for (const key of keys) {
      const value = item?.[key];
      if (value !== undefined && value !== null && value !== "") return value;
    }
  }
  return "";
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

function compareItems() {
  try {
    const parsed = JSON.parse(localStorage.getItem(COMPARE_STORAGE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveCompareItems(items) {
  localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(items.slice(0, MAX_COMPARE_COMPANIES)));
}

function addCompanyToCompare(company) {
  if (!company.crno) return [];
  const items = compareItems().filter((item) => item.crno !== company.crno);
  const nextItems = [company, ...items].slice(0, MAX_COMPARE_COMPANIES);
  saveCompareItems(nextItems);
  return nextItems;
}

function compareUrl(items = compareItems()) {
  const endpoint = new URL("/compare", window.location.origin);
  items.slice(0, MAX_COMPARE_COMPANIES).forEach((item) => endpoint.searchParams.append("crno", item.crno));
  return `${endpoint.pathname}${endpoint.search}`;
}

function setupReturnSearchLink(searchParams) {
  const returnQuery = searchParams.get("return_q");
  if (returnQuery && backLink) {
    backLink.href = `/?q=${encodeURIComponent(returnQuery)}`;
  }
}

function initials(value) {
  const source = text(value, "P").replace(/\(.*?\)/g, "").trim();
  const koreanInitials = Array.from(source).filter((char) => /[가-힣A-Za-z0-9]/.test(char));
  return (koreanInitials.slice(0, 2).join("") || "P").toUpperCase();
}

function compactDate(value) {
  if (!value) return "-";
  const raw = String(value).replaceAll("-", "");
  if (/^\d{8}$/.test(raw)) {
    return `${raw.slice(0, 4)}.${raw.slice(4, 6)}.${raw.slice(6, 8)}`;
  }
  return value;
}

function formatDateTime(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
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

function shortFinancialAmount(value) {
  const amount = Number(String(value || "").replaceAll(",", ""));
  if (!Number.isFinite(amount)) return "-";
  const absolute = Math.abs(amount);
  const sign = amount < 0 ? "-" : "";
  if (absolute >= 1_000_000_000_000) return `${sign}${(absolute / 1_000_000_000_000).toFixed(1)}조`;
  if (absolute >= 100_000_000) return `${sign}${(absolute / 100_000_000).toFixed(0)}억`;
  return `${sign}${absolute.toLocaleString("ko-KR")}`;
}

function companySummaryText({ info, outline, listed, market }) {
  const corpName = text(outline.corpNm, "이 기업");
  const industry = firstCompanyValue(info.corp_outline, ["enpMainBizNm", "sicNm"]);
  const listedName = text(listed.itmsNm || outline.enpPbanCmpyNm, "상장 종목");
  const ticker = listed.srtnCd ? `(${text(listed.srtnCd)})` : "";
  const representative = outline.enpRprFnm ? ` 대표자는 ${text(outline.enpRprFnm)}입니다.` : "";
  const isListed = Boolean(listed.srtnCd || listed.mrktCtg);

  if (!isListed) {
    if (industry) {
      return `${corpName}은 ${text(industry)}을 중심으로 하는 기업입니다.${representative}`;
    }
    return `${corpName}의 상장 정보는 확인되지 않았습니다.${representative}`;
  }

  if (industry) {
    return `${corpName}은 ${text(industry)}을 중심으로 하는 ${market} 상장 기업입니다. ${listedName}${ticker} 종목으로 거래됩니다.${representative}`;
  }

  return `${corpName}은 ${market} 시장에 상장된 ${listedName}${ticker} 기업입니다.${representative}`;
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

function formatChartAxisNumber(value) {
  if (!Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("ko-KR", {
    maximumFractionDigits: value >= 1000 ? 0 : 2,
  }).format(value);
}

function formatChartTime(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime()) && /T|\d{2}:\d{2}/.test(String(value))) {
    return parsed.toLocaleTimeString("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  return formatChartDate(value);
}

function dateKey(value) {
  if (!value) return null;
  const raw = String(value).trim();
  const compact = raw.replaceAll("-", "");
  if (/^\d{8}$/.test(compact)) return Number(compact);
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return null;
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return Number(`${year}${month}${day}`);
}

function disclosureEventLabel(category) {
  return DISCLOSURE_EVENT_LABELS[category] || DISCLOSURE_EVENT_LABELS.other;
}

function disclosureEventMeta(event) {
  return [compactDate(event.date), disclosureEventLabel(event.category), event.corp_name]
    .filter(Boolean)
    .join(" · ");
}

function disclosureEventToViewerItem(event) {
  return {
    report_nm: event.title,
    rcept_dt: event.date,
    corp_name: event.corp_name,
    rcept_no: event.receipt_no,
    viewer_url: event.viewer_url,
  };
}

function findSameOrNextTradingPoint(eventDate, pricePoints) {
  const eventKey = dateKey(eventDate);
  if (!eventKey) return null;
  return (
    pricePoints.find((point) => {
      const pointKey = dateKey(point.date);
      return pointKey !== null && pointKey >= eventKey;
    }) || null
  );
}

function mapDisclosureEventsToPricePoints(events, pricePoints) {
  return (events || [])
    .filter((event) => STOCK_MARKER_EVENT_CATEGORIES.has(event.category))
    .map((event) => {
      const point = findSameOrNextTradingPoint(event.date, pricePoints);
      if (!point) return null;
      return { ...event, x: point.x, y: point.y, price: point.price };
    })
    .filter(Boolean);
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

function selectedStockWindow(searchParams) {
  const requested = (searchParams.get("stock_window") || "1D").toUpperCase();
  return STOCK_WINDOWS.includes(requested) ? requested : "1D";
}

function selectedDisclosureType(searchParams) {
  const requested = searchParams.get("disclosure_type") || "";
  return DISCLOSURE_FILTERS.some(([value]) => value === requested) ? requested : "";
}

function renderSourceMeta(items) {
  const visibleItems = items.filter((item) => item?.value);
  if (!visibleItems.length) return "";
  return `
    <dl class="source-meta">
      ${visibleItems
        .map(
          (item) => `
            <div>
              <dt>${escapeHtml(item.label)}</dt>
              <dd>${escapeHtml(item.value)}</dd>
            </div>
          `,
        )
        .join("")}
    </dl>
  `;
}

function stockUpdatedLabel(stock) {
  const fetchedAt = formatDateTime(stock?._meta?.fetched_at);
  const expiresAt = formatDateTime(stock?._meta?.expires_at);
  if (fetchedAt && expiresAt) return `갱신 ${fetchedAt} · 캐시 만료 ${expiresAt}`;
  if (fetchedAt) return `갱신 ${fetchedAt}`;
  return "갱신 시각 정보 없음";
}

function renderStockChart(stock, activeWindow = "1D", statusText = stockUpdatedLabel(stock), disclosureEvents = []) {
  const tabs = `
    <div class="stock-range-tabs" role="tablist" aria-label="주가 기간">
      ${STOCK_WINDOWS
        .map((rangeLabel) => `<button type="button" class="${rangeLabel === activeWindow ? "is-active" : ""}" role="tab" data-stock-window="${rangeLabel}" ${rangeLabel === activeWindow ? 'aria-selected="true"' : 'aria-selected="false"'}>${rangeLabel}</button>`)
        .join("")}
    </div>
    <p class="stock-window-status" role="status">
      ${escapeHtml(statusText)}
    </p>
  `;
  const points = (stock?.graph || [])
    .map((point) => ({
      price: Number(point.price),
      date: point.date,
      volume: Number(point.volume),
    }))
    .filter((point) => Number.isFinite(point.price));

  if (points.length < 2) return tabs;

  const width = 640;
  const height = 220;
  const paddingX = 8;
  const paddingY = 18;
  const prices = points.map((point) => point.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const mid = min + (max - min) / 2;
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
  const eventMarkers = mapDisclosureEventsToPricePoints(disclosureEvents, interactionPoints);
  const linePath = coordinates
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
  const areaBase = height - paddingY;
  const areaPath = `${linePath} L ${coordinates.at(-1).x.toFixed(2)} ${areaBase} L ${coordinates[0].x.toFixed(2)} ${areaBase} Z`;
  const axisLabels = [max, mid, min].map(formatChartAxisNumber);
  const xLabels = [
    formatChartDate(points[0].date),
    formatChartDate(points[Math.floor((points.length - 1) / 2)].date),
    formatChartDate(points.at(-1).date),
  ];

  return `
    ${tabs}
    <div class="stock-chart" aria-label="${activeWindow} 주가 차트" data-chart-points="${encodeURIComponent(JSON.stringify(interactionPoints))}" data-chart-width="${width}" data-chart-last-index="${points.length - 1}">
      <div class="stock-chart-tooltip" role="status" aria-live="polite">
        <strong>${formatChartDate(points.at(-1).date)}</strong>
        <span>${formatNumber(points.at(-1).price)} KRW</span>
      </div>
      <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${activeWindow} 주가 추이" tabindex="0">
        <path class="stock-chart-grid" d="M ${paddingX} ${paddingY} H ${width - paddingX} M ${paddingX} ${height / 2} H ${width - paddingX} M ${paddingX} ${height - paddingY} H ${width - paddingX}" />
        <path class="stock-chart-area" d="${areaPath}" />
        <path class="stock-chart-line stock-chart-line-primary" d="${linePath}" />
        <rect class="stock-chart-hit-area" x="0" y="0" width="${width}" height="${height}" />
        <line class="stock-chart-guide" x1="${coordinates.at(-1).x.toFixed(2)}" y1="${paddingY}" x2="${coordinates.at(-1).x.toFixed(2)}" y2="${height - paddingY}" />
        ${eventMarkers
          .map(
            (event) => `
              <circle
                class="stock-chart-event-marker stock-chart-event-marker-${attr(event.category)}"
                cx="${Number(event.x).toFixed(2)}"
                cy="${Math.max(paddingY + 7, Number(event.y) - 10).toFixed(2)}"
                r="5"
                tabindex="0"
                role="button"
                aria-label="${attr(`${disclosureEventLabel(event.category)} ${event.title}`)}"
                data-disclosure-event-marker
                data-disclosure-viewer="${attr(event.viewer_url || "")}"
                data-disclosure-title="${attr(event.title)}"
                data-disclosure-meta="${attr(disclosureEventMeta(event))}"
              ></circle>
            `,
          )
          .join("")}
        <circle class="stock-chart-dot" cx="${coordinates.at(-1).x.toFixed(2)}" cy="${coordinates.at(-1).y.toFixed(2)}" r="4" />
      </svg>
      <div class="stock-chart-axis-labels" aria-hidden="true">
        ${axisLabels.map((label) => `<span>${label}</span>`).join("")}
      </div>
      <div class="stock-chart-meta" aria-hidden="true">
        <span class="stock-chart-meta-start">${xLabels[0]}</span>
        <span>${xLabels[1]}</span>
        <span class="stock-chart-meta-end">${xLabels[2]}</span>
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
  const volumeText = Number.isFinite(point.volume)
    ? `<small>거래량 ${formatNumber(point.volume)}</small>`
    : "";

  tooltip.innerHTML = `
    <strong>${formatTooltipDate(point.date)}</strong>
    <span>${formatNumber(point.price)} KRW</span>
    ${volumeText}
  `;
  const tooltipPosition = getTooltipLeftPercent(chart, tooltip, point.x, chartWidth);
  tooltip.style.left = `${tooltipPosition}%`;
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

function getTooltipLeftPercent(chart, tooltip, pointX, chartWidth) {
  const chartPixelWidth = chart.clientWidth;
  if (!chartPixelWidth || !chartWidth) {
    return Math.min(Math.max((pointX / chartWidth) * 100, 15), 85);
  }

  const pointPixelX = (pointX / chartWidth) * chartPixelWidth;
  const tooltipHalfWidth = tooltip.offsetWidth / 2 + 8;
  const minPixelX = Math.min(tooltipHalfWidth, chartPixelWidth / 2);
  const maxPixelX = Math.max(minPixelX, chartPixelWidth - tooltipHalfWidth);
  const clampedPixelX = Math.min(Math.max(pointPixelX, minPixelX), maxPixelX);
  return (clampedPixelX / chartPixelWidth) * 100;
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

function updateStockWindowUrl(nextWindow) {
  const nextParams = new URLSearchParams(window.location.search);
  nextParams.set("stock_window", nextWindow);
  window.history.replaceState({}, "", `${window.location.pathname}?${nextParams.toString()}`);
}

function updateStockSummary(card, stock) {
  const summary = stock?.summary || {};
  const price = summary.price || summary.extracted_price;
  const change = summary.price_movement?.percentage || summary.price_movement?.value;
  const priceElement = card.querySelector(".price");
  const priceRow = card.querySelector(".price-row");
  const existingMeta = card.querySelector(".price-meta");

  if (priceElement) {
    priceElement.textContent = formatNumber(price);
  }
  if (existingMeta) {
    existingMeta.remove();
  }
  if (change && priceRow) {
    priceRow.insertAdjacentHTML("beforeend", `<div class="price-meta">${text(change)}</div>`);
  }
}

function setupStockWindowTabs() {
  document.querySelectorAll("[data-stock-window]").forEach((button) => {
    if (button.dataset.stockWindowBound === "true") return;
    button.dataset.stockWindowBound = "true";
    button.addEventListener("click", async () => {
      const card = button.closest(".company-market-card");
      const chartShell = card?.querySelector(".stock-chart-shell");
      const status = card?.querySelector(".stock-window-status");
      const nextWindow = button.dataset.stockWindow;
      if (!card || !chartShell || !nextWindow || button.classList.contains("is-active")) return;

      card.classList.add("is-loading-stock");
      if (status) {
        status.textContent = "주가 정보를 불러오는 중입니다.";
      }
      try {
        const stock = await fetchJson(stockUrl, {
          stock_code: card.dataset.stockCode,
          exchange: card.dataset.stockExchange,
          language: card.dataset.stockLanguage,
          window: nextWindow,
          corporate_registration_number: card.dataset.crno,
        });
        updateStockSummary(card, stock);
        const disclosureEvents = JSON.parse(card.dataset.disclosureEvents || "[]");
        chartShell.innerHTML = renderStockChart(stock, nextWindow, stockUpdatedLabel(stock), disclosureEvents);
        updateStockWindowUrl(nextWindow);
        setupStockChartInteractions();
        setupStockWindowTabs();
        setupDisclosureViewer();
      } catch (error) {
        if (status) {
          status.textContent = error.message || "주가 정보를 불러오지 못했습니다.";
        }
        chartShell.insertAdjacentHTML(
          "beforeend",
          `<p class="stock-chart-error">${escapeHtml(error.message || "주가 정보를 불러오지 못했습니다.")}</p>`,
        );
      } finally {
        card.classList.remove("is-loading-stock");
      }
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

function disclosureMeta(item, includeReceiptNo = false) {
  return [item.rcept_dt, item.flr_nm || item.corp_name, includeReceiptNo ? item.rcept_no : ""]
    .filter(Boolean)
    .map((value) => text(value))
    .join(" · ");
}

function renderDisclosureViewerTrigger(item) {
  const viewerUrl = text(item.viewer_url, "");
  const title = text(item.report_nm);
  const meta = disclosureMeta(item);
  if (!viewerUrl || viewerUrl === "#") {
    return `<span class="disclosure-title">${escapeHtml(title)}</span>`;
  }
  return `
    <button
      type="button"
      class="disclosure-viewer-trigger"
      data-disclosure-viewer="${attr(viewerUrl)}"
      data-disclosure-title="${attr(title)}"
      data-disclosure-meta="${attr(meta)}"
    >
      ${escapeHtml(title)}
    </button>
  `;
}

function renderDisclosureSummaryButton(item) {
  const viewerUrl = text(item.viewer_url, "");
  const receiptNo = text(item.rcept_no || item.receipt_no, "");
  const title = text(item.report_nm || item.title, "");
  if (!viewerUrl || viewerUrl === "#" || !receiptNo) return "";
  return `
    <button
      type="button"
      class="disclosure-summary-button"
      data-disclosure-summary
      data-disclosure-receipt-no="${attr(receiptNo)}"
      data-disclosure-viewer-url="${attr(viewerUrl)}"
      data-disclosure-title="${attr(title)}"
    >요약</button>
  `;
}

function ensureDisclosureSummaryModal() {
  const existing = document.querySelector(".disclosure-summary-modal");
  if (existing) return existing;
  document.body.insertAdjacentHTML(
    "beforeend",
    `
      <div class="disclosure-summary-modal" hidden>
        <button type="button" class="disclosure-summary-backdrop" data-disclosure-summary-close aria-label="닫기"></button>
        <section class="disclosure-summary-dialog" role="dialog" aria-modal="true" aria-labelledby="disclosure-summary-title">
          <header class="disclosure-summary-header">
            <div>
              <p id="disclosure-summary-meta">DART 공시</p>
              <h2 id="disclosure-summary-title">공시 요약</h2>
            </div>
            <button type="button" class="disclosure-summary-close" data-disclosure-summary-close>닫기</button>
          </header>
          <div class="disclosure-summary-body" data-disclosure-summary-body></div>
        </section>
      </div>
    `,
  );
  const modal = document.querySelector(".disclosure-summary-modal");
  modal.querySelectorAll("[data-disclosure-summary-close]").forEach((button) => {
    button.addEventListener("click", closeDisclosureSummaryModal);
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) closeDisclosureSummaryModal();
  });
  return modal;
}

function closeDisclosureSummaryModal() {
  const modal = document.querySelector(".disclosure-summary-modal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("has-disclosure-summary-open");
}

function renderDisclosureSummaryPayload(payload) {
  const summary = payload?.summary || {};
  const section = (title, items) => `
    <section>
      <h3>${escapeHtml(title)}</h3>
      ${
        items?.length
          ? `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
          : `<p class="empty-copy">표시할 내용이 없습니다.</p>`
      }
    </section>
  `;
  return `
    ${section("핵심 요약", summary.bullets || [])}
    ${section("리스크/확인사항", summary.risks || [])}
    ${section("변동사항", summary.changes || [])}
    ${section("한계", summary.limitations || [])}
    <p class="disclosure-summary-source">OpenAI 요약 · 원문에 없는 내용은 포함하지 않도록 생성됩니다.</p>
  `;
}

async function openDisclosureSummary(button) {
  const modal = ensureDisclosureSummaryModal();
  modal.hidden = false;
  document.body.classList.add("has-disclosure-summary-open");
  modal.querySelector("#disclosure-summary-title").textContent =
    button.dataset.disclosureTitle || "공시 요약";
  modal.querySelector("[data-disclosure-summary-body]").innerHTML =
    `<p class="empty-copy">요약을 생성하는 중입니다.</p>`;
  try {
    const payload = await fetchJson(summaryUrl, {
      receipt_no: button.dataset.disclosureReceiptNo,
      viewer_url: button.dataset.disclosureViewerUrl,
      title: button.dataset.disclosureTitle,
    });
    modal.querySelector("[data-disclosure-summary-body]").innerHTML =
      renderDisclosureSummaryPayload(payload);
  } catch (error) {
    modal.querySelector("[data-disclosure-summary-body]").innerHTML =
      `<p class="empty-copy">${escapeHtml(error.message || "요약을 생성하지 못했습니다.")}</p>`;
  }
}

function setupDisclosureSummaryButtons() {
  ensureDisclosureSummaryModal();
  document.querySelectorAll("[data-disclosure-summary]").forEach((button) => {
    if (button.dataset.disclosureSummaryBound === "true") return;
    button.dataset.disclosureSummaryBound = "true";
    button.addEventListener("click", () => openDisclosureSummary(button));
  });
}

function ensureDisclosureViewerModal() {
  const existing = document.querySelector(".disclosure-viewer-modal");
  if (existing) return existing;

  document.body.insertAdjacentHTML(
    "beforeend",
    `
      <div class="disclosure-viewer-modal" hidden>
        <div class="disclosure-viewer-backdrop" data-disclosure-viewer-close></div>
        <section class="disclosure-viewer-dialog" role="dialog" aria-modal="true" aria-labelledby="disclosure-viewer-title">
          <header class="disclosure-viewer-header">
            <div>
              <p id="disclosure-viewer-meta"></p>
              <h2 id="disclosure-viewer-title">공시</h2>
            </div>
            <div class="disclosure-viewer-actions">
              <a class="disclosure-viewer-external" href="#" target="_blank" rel="noreferrer">DART에서 열기</a>
              <button type="button" class="disclosure-viewer-close" data-disclosure-viewer-close>닫기</button>
            </div>
          </header>
          <iframe class="disclosure-viewer-frame" title="DART 공시 뷰어" loading="lazy" referrerpolicy="no-referrer"></iframe>
        </section>
      </div>
    `,
  );

  const modal = document.querySelector(".disclosure-viewer-modal");
  modal.querySelectorAll("[data-disclosure-viewer-close]").forEach((control) => {
    control.addEventListener("click", closeDisclosureViewer);
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) closeDisclosureViewer();
  });
  return modal;
}

function closeDisclosureViewer() {
  const modal = document.querySelector(".disclosure-viewer-modal");
  if (!modal) return;
  const frame = modal.querySelector(".disclosure-viewer-frame");
  modal.hidden = true;
  document.body.classList.remove("has-disclosure-viewer-open");
  if (frame) frame.removeAttribute("src");
}

function openDisclosureViewer(control) {
  const url = control.dataset.disclosureViewer;
  if (!url) return;
  const modal = ensureDisclosureViewerModal();
  const frame = modal.querySelector(".disclosure-viewer-frame");
  const title = modal.querySelector("#disclosure-viewer-title");
  const meta = modal.querySelector("#disclosure-viewer-meta");
  const external = modal.querySelector(".disclosure-viewer-external");
  const close = modal.querySelector(".disclosure-viewer-close");

  title.textContent = control.dataset.disclosureTitle || "공시";
  meta.textContent = control.dataset.disclosureMeta || "DART 공시";
  external.href = url;
  frame.src = url;
  modal.hidden = false;
  document.body.classList.add("has-disclosure-viewer-open");
  close?.focus();
}

function setupDisclosureViewer() {
  ensureDisclosureViewerModal();
  document.querySelectorAll("[data-disclosure-viewer]").forEach((control) => {
    if (control.dataset.disclosureViewerBound === "true") return;
    control.dataset.disclosureViewerBound = "true";
    control.addEventListener("click", () => openDisclosureViewer(control));
  });
}

function disclosureListItemsHtml(items, includeReceiptNo = false) {
  return (
    items
      .map(
        (item) => `
          <li>
            <span class="disclosure-action-row">
              ${renderDisclosureViewerTrigger(item)}
              ${renderDisclosureSummaryButton(item)}
            </span>
            <span>${escapeHtml(disclosureMeta(item, includeReceiptNo))}</span>
          </li>
        `,
      )
      .join("") || `<li><span>표시할 공시가 없습니다.</span></li>`
  );
}

function disclosureTotalCount(disclosures) {
  const total = Number(disclosures?.total_count);
  return Number.isFinite(total) && total >= 0 ? total : null;
}

function disclosureCountText(loadedCount, totalCount) {
  if (totalCount !== null && totalCount !== undefined) {
    return `${loadedCount.toLocaleString("ko-KR")} / ${totalCount.toLocaleString("ko-KR")}개 공시`;
  }
  return `${loadedCount.toLocaleString("ko-KR")}개 공시`;
}

function updateDisclosureCount(loadedCount, totalCount) {
  const count = document.querySelector("[data-disclosure-count='true']");
  if (count) {
    count.textContent = disclosureCountText(loadedCount, totalCount);
  }
}

function appendDisclosureItems(items) {
  const list = document.querySelector("[data-disclosure-list='true']");
  if (!list || !items.length) return;
  list.insertAdjacentHTML("beforeend", disclosureListItemsHtml(items, true));
  setupDisclosureViewer();
  setupDisclosureSummaryButtons();
}

function setupInfiniteDisclosureScroll({ corpCode, disclosureType, initialPage, perPage, loadedCount, totalCount }) {
  const sentinel = document.querySelector("[data-disclosure-sentinel='true']");
  const status = document.querySelector("[data-disclosure-load-status='true']");
  if (!corpCode || !sentinel || !status) return;

  let nextPage = initialPage + 1;
  let currentLoadedCount = loadedCount;
  let isLoading = false;
  let isComplete = totalCount !== null && currentLoadedCount >= totalCount;

  const setStatus = (message) => {
    status.textContent = message;
  };

  const loadMore = async () => {
    if (isLoading || isComplete) return;
    isLoading = true;
    setStatus("공시를 더 불러오는 중입니다.");

    try {
      const payload = await fetchJson("/api/company/get_dart_disclosures", {
        corp_code: corpCode,
        disclosure_type: disclosureType,
        page: nextPage,
        per_page: DISCLOSURE_PAGE_SIZE,
      });
      const items = payload?.list || [];
      appendDisclosureItems(items);
      currentLoadedCount += items.length;
      nextPage += 1;
      if (totalCount === null) {
        totalCount = disclosureTotalCount(payload);
      }
      updateDisclosureCount(currentLoadedCount, totalCount);
      isComplete =
        !items.length ||
        items.length < perPage ||
        (totalCount !== null && currentLoadedCount >= totalCount);
      setStatus(isComplete ? "모든 공시를 불러왔습니다." : "아래로 스크롤하면 공시를 더 불러옵니다.");
    } catch (error) {
      setStatus(error.message || "공시를 더 불러오지 못했습니다.");
    } finally {
      isLoading = false;
    }
  };

  if (isComplete) {
    setStatus("모든 공시를 불러왔습니다.");
    return;
  }

  if (!("IntersectionObserver" in window)) {
    window.addEventListener("scroll", () => {
      const rect = sentinel.getBoundingClientRect();
      if (rect.top < window.innerHeight + 160) loadMore();
    });
    setStatus("아래로 스크롤하면 공시를 더 불러옵니다.");
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) {
      loadMore();
    }
  }, { rootMargin: "240px 0px" });
  observer.observe(sentinel);
  setStatus("아래로 스크롤하면 공시를 더 불러옵니다.");
}

function renderDisclosureFilters(activeType) {
  return `
    <div class="disclosure-filter-tabs" role="tablist" aria-label="공시 유형">
      ${DISCLOSURE_FILTERS
        .map(
          ([value, label]) => `
            <button type="button" class="${value === activeType ? "is-active" : ""}" data-disclosure-type="${attr(value)}" aria-selected="${value === activeType ? "true" : "false"}">
              ${label}
            </button>
          `,
        )
        .join("")}
    </div>
  `;
}

function setupDisclosureFilters({ corpCode, outline, crno }) {
  document.querySelectorAll("[data-disclosure-type]").forEach((button) => {
    if (button.dataset.disclosureFilterBound === "true") return;
    button.dataset.disclosureFilterBound = "true";
    button.addEventListener("click", async () => {
      const disclosureType = button.dataset.disclosureType;
      const payload = await fetchJson("/api/company/get_dart_disclosures", {
        corp_code: corpCode,
        disclosure_type: disclosureType,
        page: 1,
        per_page: DISCLOSURE_PAGE_SIZE,
      });
      const nextParams = new URLSearchParams(window.location.search);
      if (disclosureType) nextParams.set("disclosure_type", disclosureType);
      else nextParams.delete("disclosure_type");
      window.history.replaceState({}, "", `${window.location.pathname}?${nextParams.toString()}`);
      renderDisclosuresPage({ disclosures: payload, outline, crno, activeDisclosureType: disclosureType });
      setupInfiniteDisclosureScroll({
        corpCode,
        disclosureType,
        initialPage: 1,
        perPage: DISCLOSURE_PAGE_SIZE,
        loadedCount: payload?.list?.length || 0,
        totalCount: disclosureTotalCount(payload),
      });
      setupDisclosureFilters({ corpCode, outline, crno });
      setupDisclosureSummaryButtons();
    });
  });
}

function renderDartDisclosures(disclosures) {
  const items = (disclosures?.list || []).slice(0, 10);
  if (!items.length) return "";
  const crno = new URLSearchParams(window.location.search).get("crno");

  return `
    <article class="info-block company-disclosure-card">
      <div class="block-heading">
        <h3>최근 공시</h3>
        <a href="/profile?crno=${encodeURIComponent(crno)}&view=disclosures">더보기</a>
      </div>
      <ul class="disclosure-list">
        ${items
          .map(
            (item) => `
              <li>
                <span class="disclosure-action-row">
                  ${renderDisclosureViewerTrigger(item)}
                  ${renderDisclosureSummaryButton(item)}
                </span>
                <span>${escapeHtml(disclosureMeta(item))}</span>
              </li>
            `,
          )
          .join("")}
      </ul>
    </article>
  `;
}

function renderDisclosureEventTimeline(events) {
  const items = (events || []).slice(0, 8);
  if (!items.length) return "";
  return `
    <article class="info-block company-event-timeline-card">
      <div class="block-heading">
        <h3>공시 이벤트</h3>
      </div>
      <ol class="disclosure-event-timeline">
        ${items
          .map((event) => {
            const viewerItem = disclosureEventToViewerItem(event);
            return `
              <li>
                <span class="disclosure-event-date">${escapeHtml(compactDate(event.date))}</span>
                <span class="disclosure-event-badge disclosure-event-${attr(event.category)}">${escapeHtml(disclosureEventLabel(event.category))}</span>
                <span class="disclosure-action-row">
                  ${renderDisclosureViewerTrigger(viewerItem)}
                  ${renderDisclosureSummaryButton(viewerItem)}
                </span>
              </li>
            `;
          })
          .join("")}
      </ol>
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

function numericFinancialAmount(value) {
  const numeric = Number(String(value || "").replaceAll(",", ""));
  return Number.isFinite(numeric) ? numeric : null;
}

function financialDeltaBasis(item) {
  const current = numericFinancialAmount(item.thstrm_amount);
  const previousSamePeriod = numericFinancialAmount(item.yoy_amount);
  const previous = numericFinancialAmount(item.frmtrm_amount);

  if (item.reprt_code !== "11011") {
    return { current, previous: previousSamePeriod, label: "전년 동기" };
  }
  return { current, previous, label: "전년 대비" };
}

function financialDelta(item) {
  const { current, previous, label } = financialDeltaBasis(item);
  if (current === null || previous === null || previous === 0) {
    return null;
  }
  const ratio = ((current - previous) / Math.abs(previous)) * 100;
  return {
    ratio,
    label,
    className: ratio >= 0 ? "is-positive" : "is-negative",
  };
}

function financialDeltaText(item) {
  const delta = financialDelta(item);
  if (!delta) return "";
  const sign = delta.ratio > 0 ? "+" : "";
  return `${sign}${delta.ratio.toFixed(1)}% ${delta.label}`;
}

function renderFinancialSummaryPanel({ report, key, isActive }) {
  const selected = report?.selected;
  const accounts = report?.accounts;
  const items = financialSummaryItems(accounts);
  if (!items.length) return "";
  const crno = new URLSearchParams(window.location.search).get("crno");
  const corpCode = profileDetail.dataset.dartCorpCode || "";
  const subtitle = selected
    ? `${selected.business_year} · ${selected.report_name} · ${optionLabel(financialStatementOptions, selected.fs_division)}`
    : "재무정보";
  const trendPayload = {
    corpCode,
    endYear: selected?.business_year || "",
    reportCode: selected?.report_code || "",
    fsDivision: selected?.fs_division || "CFS",
    accounts: items.map((item) => item.account_nm),
  };

  return `
    <div class="financial-summary-panel ${isActive ? "is-active" : ""}" data-financial-panel="${key}" data-financial-detail-url="${financialDetailUrl(crno, selected)}" data-financial-trend-payload="${attr(JSON.stringify(trendPayload))}" ${isActive ? "" : "hidden"}>
      <div class="financial-summary-panel-head">
        <p class="financial-summary-meta">${subtitle}</p>
      </div>
      <div class="financial-metrics">
        ${items
          .map(
            (item) => {
              const delta = financialDelta(item);
              return `
                <button type="button" class="financial-metric-card" data-financial-trend-account="${attr(item.account_nm)}">
                  <span class="financial-metric-label">${text(item.account_nm)}</span>
                  <span class="financial-metric-value">${formatFinancialAmount(item.thstrm_amount, item.currency)}</span>
                  ${financialDeltaText(item) ? `<span class="delta-badge ${delta.className}">${financialDeltaText(item)}</span>` : ""}
                </button>
              `;
            },
          )
          .join("")}
      </div>
    </div>
  `;
}

function ensureFinancialTrendModal() {
  const existing = document.querySelector(".financial-trend-modal");
  if (existing) return existing;
  document.body.insertAdjacentHTML(
    "beforeend",
    `
      <div class="financial-trend-modal" hidden>
        <button class="financial-trend-backdrop" type="button" data-financial-trend-close aria-label="닫기"></button>
        <section class="financial-trend-dialog" role="dialog" aria-modal="true" aria-labelledby="financial-trend-title">
          <header class="financial-trend-header">
            <div>
              <p id="financial-trend-meta">최근 5개년</p>
              <h2 id="financial-trend-title">재무 추이</h2>
            </div>
            <button type="button" class="financial-trend-close" data-financial-trend-close>닫기</button>
          </header>
          <div class="financial-trend-controls">
            <button type="button" class="financial-trend-toggle" data-financial-trend-toggle>계정 선택</button>
            <div class="financial-trend-account-menu" data-financial-trend-menu hidden></div>
          </div>
          <div class="financial-trend-chart" data-financial-trend-chart role="img" aria-label="재무 항목 추이"></div>
        </section>
      </div>
    `,
  );
  const modal = document.querySelector(".financial-trend-modal");
  modal.querySelectorAll("[data-financial-trend-close]").forEach((control) => {
    control.addEventListener("click", closeFinancialTrendModal);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) closeFinancialTrendModal();
  });
  modal.querySelector("[data-financial-trend-toggle]").addEventListener("click", () => {
    const menu = modal.querySelector("[data-financial-trend-menu]");
    menu.hidden = !menu.hidden;
  });
  return modal;
}

function closeFinancialTrendModal() {
  const modal = document.querySelector(".financial-trend-modal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("has-financial-trend-open");
}

function trendSeries(periods, accountName) {
  return periods.map((period) => {
    const account = (period.accounts || []).find((item) => item.account_nm === accountName);
    return {
      label: period.business_year,
      value: numericFinancialAmount(account?.thstrm_amount),
    };
  });
}

function renderFinancialTrendChart(modal, trendPayload, selectedAccounts) {
  const chart = modal.querySelector("[data-financial-trend-chart]");
  const periods = trendPayload.periods || [];
  const series = selectedAccounts.map((accountName, index) => ({
    accountName,
    color: ["#1d5faa", "#0f8b6d", "#d97706", "#7c3aed", "#dc2626", "#475569"][index % 6],
    points: trendSeries(periods, accountName),
  }));
  const values = series.flatMap((item) => item.points.map((point) => point.value)).filter((value) => value !== null);
  if (!periods.length || !series.length || !values.length) {
    chart.innerHTML = `<p class="empty-copy">표시할 추이 데이터가 없습니다.</p>`;
    return;
  }
  const width = 640;
  const height = 260;
  const paddingX = 42;
  const paddingY = 28;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const plotWidth = width - paddingX * 2;
  const plotHeight = height - paddingY * 2;
  const xFor = (index) => paddingX + (index / Math.max(periods.length - 1, 1)) * plotWidth;
  const yFor = (value) => paddingY + ((max - value) / range) * plotHeight;
  chart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
      <path class="financial-trend-grid" d="M ${paddingX} ${paddingY} H ${width - paddingX} M ${paddingX} ${height / 2} H ${width - paddingX} M ${paddingX} ${height - paddingY} H ${width - paddingX}" />
      ${series
        .map((item) => {
          const path = item.points
            .map((point, index) => point.value === null ? "" : `${index === 0 ? "M" : "L"} ${xFor(index).toFixed(2)} ${yFor(point.value).toFixed(2)}`)
            .filter(Boolean)
            .join(" ");
          return `<path class="financial-trend-line" d="${path}" stroke="${item.color}" />`;
        })
        .join("")}
    </svg>
    <div class="financial-trend-axis" aria-hidden="true">
      ${periods.map((period) => `<span>${escapeHtml(period.business_year)}</span>`).join("")}
    </div>
    <div class="financial-trend-legend">
      ${series
        .map((item) => {
          const latest = item.points.at(-1)?.value;
          return `<span><i style="background:${item.color}"></i>${escapeHtml(item.accountName)} ${shortFinancialAmount(latest)}</span>`;
        })
        .join("")}
    </div>
  `;
}

function renderFinancialTrendAccounts(modal, accounts, trendPayload, selectedAccounts) {
  const menu = modal.querySelector("[data-financial-trend-menu]");
  menu.innerHTML = accounts
    .map(
      (accountName) => `
        <label class="financial-trend-account-check">
          <input type="checkbox" value="${attr(accountName)}" ${selectedAccounts.includes(accountName) ? "checked" : ""} />
          <span>${escapeHtml(accountName)}</span>
        </label>
      `,
    )
    .join("");
  menu.querySelectorAll("input").forEach((input) => {
    input.addEventListener("change", () => {
      const nextSelected = Array.from(menu.querySelectorAll("input:checked")).map((item) => item.value);
      renderFinancialTrendChart(modal, trendPayload, nextSelected);
    });
  });
}

async function openFinancialTrendModal(button) {
  const panel = button.closest("[data-financial-trend-payload]");
  if (!panel) return;
  const panelPayload = JSON.parse(panel.dataset.financialTrendPayload || "{}");
  const accountName = button.dataset.financialTrendAccount;
  const modal = ensureFinancialTrendModal();
  modal.hidden = false;
  document.body.classList.add("has-financial-trend-open");
  modal.querySelector("#financial-trend-title").textContent = `${accountName} 추이`;
  modal.querySelector("#financial-trend-meta").textContent = "최근 5개년";
  modal.querySelector("[data-financial-trend-chart]").innerHTML = `<p class="empty-copy">재무 추이를 불러오는 중입니다.</p>`;
  const trendPayload = await fetchJson("/api/company/get_dart_financial_trends", {
    corp_code: panelPayload.corpCode,
    end_year: panelPayload.endYear,
    report_code: panelPayload.reportCode,
    fs_division: panelPayload.fsDivision,
    years: 5,
  });
  const accounts = Array.from(
    new Set([
      accountName,
      ...(panelPayload.accounts || []),
      ...(trendPayload.periods || []).flatMap((period) => (period.accounts || []).map((item) => item.account_nm)),
    ]),
  ).filter(Boolean);
  const selectedAccounts = [accountName];
  renderFinancialTrendAccounts(modal, accounts, trendPayload, selectedAccounts);
  renderFinancialTrendChart(modal, trendPayload, selectedAccounts);
}

function setupFinancialTrendCards() {
  document.querySelectorAll("[data-financial-trend-account]").forEach((button) => {
    if (button.dataset.financialTrendBound === "true") return;
    button.dataset.financialTrendBound = "true";
    button.addEventListener("click", () => {
      openFinancialTrendModal(button).catch((error) => {
        const modal = ensureFinancialTrendModal();
        modal.querySelector("[data-financial-trend-chart]").innerHTML = `<p class="empty-copy">${escapeHtml(error.message || "재무 추이를 불러오지 못했습니다.")}</p>`;
      });
    });
  });
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
  const activeReport = activeKey === "quarter" ? quarterReport : annualReport;
  const activeDetailUrl = financialDetailUrl(new URLSearchParams(window.location.search).get("crno"), activeReport?.selected);

  return `
    <article class="info-block financial-summary">
      <div class="block-heading financial-summary-heading">
        <h3>재무 요약</h3>
        <a class="text-link financial-more-link" href="${activeDetailUrl}">더보기</a>
        <div class="summary-tabs" role="tablist" aria-label="재무제표 기간">
          <button type="button" class="${activeKey === "quarter" ? "is-active" : ""}" data-financial-tab="quarter" ${hasQuarter ? "" : "disabled"}>
            분기
          </button>
          <button type="button" class="${activeKey === "annual" ? "is-active" : ""}" data-financial-tab="annual" ${hasAnnual ? "" : "disabled"}>
            연간
          </button>
        </div>
      </div>
      ${renderFinancialSummaryPanel({ report: quarterReport, key: "quarter", isActive: activeKey === "quarter" })}
      ${renderFinancialSummaryPanel({ report: annualReport, key: "annual", isActive: activeKey === "annual" })}
    </article>
  `;
}

function renderCompanyInsightRow(info) {
  const financialSummary = renderDartFinancialAccounts(info);
  const disclosures = renderDartDisclosures(info.dart_disclosures);
  if (!financialSummary && !disclosures) return "";

  return `
    <div class="company-insight-row">
      ${financialSummary}
      ${disclosures}
    </div>
  `;
}

function renderInsightMetric(label, value) {
  if (!value) return "";
  return `<div><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`;
}

function ownershipBarColor(index) {
  return ["#1d5faa", "#0f8b6d", "#d97706", "#7c3aed", "#dc2626"][index % 5];
}

function isOwnershipTotalHolder(holder) {
  return ["계", "합계", "소계", "총계"].includes(String(holder?.name || "").trim());
}

function renderOwnershipStackedBar(ownership) {
  const holders = (ownership?.holders || [])
    .filter((holder) => Number.isFinite(Number(holder.ratio_number)) && Number(holder.ratio_number) > 0)
    .filter((holder) => !isOwnershipTotalHolder(holder))
    .sort((a, b) => Number(b.ratio_number) - Number(a.ratio_number))
    .slice(0, OWNERSHIP_BAR_MAX_HOLDERS);
  if (!holders.length) {
    return `
      <dl class="compact-metric-grid">
        ${renderInsightMetric("이름", ownership?.largest_holder_name)}
        ${renderInsightMetric("지분율", ownership?.largest_holder_ratio)}
      </dl>
    `;
  }
  const knownRatio = holders.reduce((sum, holder) => sum + Number(holder.ratio_number), 0);
  const segments = [
    ...holders.map((holder, index) => ({
      name: holder.name || `주주 ${index + 1}`,
      ratio: Math.max(0, Number(holder.ratio_number)),
      ratioText: holder.ratio || `${Number(holder.ratio_number).toFixed(2)}%`,
      color: ownershipBarColor(index),
    })),
    ...(knownRatio < 100
      ? [{
          name: "기타 주주",
          ratio: 100 - knownRatio,
          ratioText: `${(100 - knownRatio).toFixed(2)}%`,
          color: "#e7ebf3",
        }]
      : []),
  ];
  return `
    <div class="ownership-stacked-bar" aria-label="최대주주 지분 구성">
      <div class="ownership-bar-track">
        ${segments
          .map(
            (segment) => `
              <span
                class="ownership-bar-segment"
                style="width: ${Math.min(segment.ratio, 100).toFixed(4)}%; background: ${segment.color};"
                title="${attr(segment.name)} ${attr(segment.ratioText)}"
              ></span>
            `,
          )
          .join("")}
      </div>
      <ul class="ownership-bar-legend">
        ${segments
          .map(
            (segment) => `
              <li>
                <i style="background: ${segment.color};"></i>
                <span>${escapeHtml(segment.name)}</span>
                <strong>${escapeHtml(segment.ratioText)}</strong>
              </li>
            `,
          )
          .join("")}
      </ul>
    </div>
  `;
}

function renderDartInsightDetailButtons(insights) {
  if (!insights?.basis?.business_year || !insights?.basis?.report_code) return "";
  return `
    <div class="dart-insight-detail-actions">
      <button type="button" data-dart-insight-detail-kind="capital">주식구조 더보기</button>
      <button type="button" data-dart-insight-detail-kind="people">임직원 더보기</button>
    </div>
  `;
}

function renderCompanyInsightCards(insights) {
  if (!insights) return "";
  const ratioItems = insights.ratios?.items || [];
  const basisPayload = attr(JSON.stringify(insights.basis || {}));
  const cards = [
    insights.ownership
      ? `
        <article class="info-block company-insight-card">
          <div class="block-heading"><h3>최대주주</h3></div>
          ${renderOwnershipStackedBar(insights.ownership)}
        </article>
      `
      : "",
    insights.dividend
      ? `
        <article class="info-block company-insight-card">
          <div class="block-heading"><h3>배당</h3></div>
          <dl class="compact-metric-grid">
            ${renderInsightMetric("주당배당금", insights.dividend.dividend_per_share)}
            ${renderInsightMetric("배당성향", insights.dividend.payout_ratio)}
          </dl>
        </article>
      `
      : "",
    insights.audit
      ? `
        <article class="info-block company-insight-card">
          <div class="block-heading"><h3>감사의견</h3></div>
          <dl class="compact-metric-grid">
            ${renderInsightMetric("의견", insights.audit.opinion)}
            ${renderInsightMetric("회계감사인", insights.audit.auditor)}
          </dl>
        </article>
      `
      : "",
    ratioItems.length
      ? `
        <article class="info-block company-insight-card">
          <div class="block-heading"><h3>재무비율</h3></div>
          <dl class="compact-metric-grid">
            ${ratioItems.map((item) => renderInsightMetric(item.name, item.value)).join("")}
          </dl>
        </article>
      `
      : "",
  ].filter(Boolean);
  if (!cards.length) {
    return `<article class="info-block company-insight-empty"><p class="empty-copy">표시할 심화 정보가 없습니다.</p></article>`;
  }
  const sourceMeta = insights.basis
    ? `<p class="company-insight-source">출처 DART 정기보고서 · ${escapeHtml(insights.basis.business_year || "")} ${escapeHtml(insights.basis.report_name || "")} · 정정 공시가 있으면 수치가 바뀔 수 있습니다.</p>`
    : `<p class="company-insight-source">출처 DART 정기보고서 · 정정 공시가 있으면 수치가 바뀔 수 있습니다.</p>`;
  return `
    <section class="company-insight-cards" aria-label="기업 심화 정보" data-dart-insight-basis="${basisPayload}">
      ${cards.join("")}
      ${sourceMeta}
      ${renderDartInsightDetailButtons(insights)}
    </section>
  `;
}

function renderRiskSignalCards(riskSignals) {
  const signals = riskSignals?.signals || [];
  const historySignals = riskSignals?.requires_history || [];
  if (!signals.length && !historySignals.length) return "";
  return `
    <article class="info-block company-risk-card">
      <div class="block-heading">
        <h3>주의 신호</h3>
      </div>
      ${
        signals.length
          ? `<ul class="risk-signal-list">
              ${signals
                .map(
                  (signal) => `
                    <li class="risk-signal-item risk-signal-${attr(signal.severity || "info")}">
                      <strong>${escapeHtml(signal.label)}</strong>
                      <span>${escapeHtml(signal.detail)}</span>
                    </li>
                  `,
                )
                .join("")}
            </ul>`
          : `<p class="empty-copy">현재 데이터 기준으로 표시할 주의 신호가 없습니다.</p>`
      }
      ${
        historySignals.length
          ? `<p class="risk-history-note">과거 보고서 비교가 쌓이면 ${historySignals
              .slice(0, 3)
              .map((signal) => signal.label)
              .join(", ")} 같은 변화 신호도 표시할 수 있습니다.</p>`
          : ""
      }
    </article>
  `;
}

function renderDartInsightDetailRows(payload) {
  const rows = payload.kind === "capital"
    ? [...(payload.total_stock || []), ...(payload.treasury_stock || [])]
    : [...(payload.executives || []), ...(payload.employees || [])];
  if (!rows.length) return `<p class="empty-copy">표시할 상세 정보가 없습니다.</p>`;
  const kind = payload.kind || "capital";
  return `
    <ul class="dart-insight-detail-list">
      ${rows
        .slice(0, 80)
        .map((row) => {
          const title = row.nm || row.name || row.se || row.stock_knd || row.ofcps || row.chrg_job || "상세 항목";
          const meta = renderDartInsightDetailMeta(row, kind);
          return `
            <li>
              <strong>${escapeHtml(title)}</strong>
              ${meta}
            </li>
          `;
        })
        .join("")}
    </ul>
  `;
}

function formatDartInsightDetailField(label, value) {
  if (value === undefined || value === null || value === "" || value === "-") return "";
  return `<span class="dart-insight-detail-meta"><b>${label}</b> ${escapeHtml(value)}</span>`;
}

function renderDartInsightDetailMeta(row, kind) {
  const fields = kind === "people"
    ? [
        ["직위", row.ofcps],
        ["담당업무", row.chrg_job],
        ["상근여부", row.fte_at],
        ["성별", row.sexdstn],
        ["출생", row.birth_ym],
        ["임기만료", row.tenure_end_on],
        ["주요경력", row.main_career],
      ]
    : [
        ["구분", row.se || row.stock_knd],
        ["주식수", row.istc_totqy || row.trmend_qy || row.acqs_stock_qy || row.dsps_stock_qy],
        ["비율", row.qota_rt || row.stock_qota_rt],
        ["기초", row.bsis_qy || row.bsis_posesn_stock_co],
        ["증가", row.incrs_qy],
        ["감소", row.dcrs_qy],
        ["기말", row.trmend_qy],
      ];
  const html = fields.map(([label, value]) => formatDartInsightDetailField(label, value)).filter(Boolean).join("");
  return html || `<span class="dart-insight-detail-meta">표시할 주요 항목이 없습니다.</span>`;
}

function ensureDartInsightDetailModal() {
  const existing = document.querySelector(".dart-insight-detail-modal");
  if (existing) return existing;
  const wrapper = document.createElement("div");
  wrapper.innerHTML = `
    <div class="dart-insight-detail-modal" hidden>
      <button type="button" class="dart-insight-detail-backdrop" data-dart-insight-detail-close aria-label="닫기"></button>
      <section class="dart-insight-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="dart-insight-detail-title">
        <div class="dart-insight-detail-header">
          <h3 id="dart-insight-detail-title">상세 정보</h3>
          <button type="button" class="dart-insight-detail-close" data-dart-insight-detail-close aria-label="닫기">×</button>
        </div>
        <div class="dart-insight-detail-body" data-dart-insight-detail-body></div>
      </section>
    </div>
  `;
  const modal = wrapper.firstElementChild;
  document.body.appendChild(modal);
  modal.querySelectorAll("[data-dart-insight-detail-close]").forEach((button) => {
    button.addEventListener("click", () => {
      modal.hidden = true;
      document.body.classList.remove("has-dart-insight-detail-open");
    });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) {
      modal.hidden = true;
      document.body.classList.remove("has-dart-insight-detail-open");
    }
  });
  return modal;
}

async function openDartInsightDetailModal(button) {
  const kind = button.dataset.dartInsightDetailKind;
  const basis = JSON.parse(button.closest("[data-dart-insight-basis]")?.dataset.dartInsightBasis || "{}");
  const corpCode = profileDetail.dataset.dartCorpCode;
  const modal = ensureDartInsightDetailModal();
  modal.hidden = false;
  document.body.classList.add("has-dart-insight-detail-open");
  modal.querySelector("#dart-insight-detail-title").textContent = kind === "capital" ? "주식 구조" : "임직원";
  modal.querySelector("[data-dart-insight-detail-body]").innerHTML = `<p class="empty-copy">불러오는 중입니다.</p>`;
  const payload = await fetchJson("/api/company/get_dart_company_insight_detail", {
    corp_code: corpCode,
    business_year: basis.business_year,
    report_code: basis.report_code,
    kind,
  });
  modal.querySelector("[data-dart-insight-detail-body]").innerHTML = renderDartInsightDetailRows(payload);
}

function setupDartInsightDetailButtons() {
  document.querySelectorAll("[data-dart-insight-detail-kind]").forEach((button) => {
    if (button.dataset.dartInsightDetailBound === "true") return;
    button.dataset.dartInsightDetailBound = "true";
    button.addEventListener("click", () => {
      openDartInsightDetailModal(button).catch((error) => {
        const modal = ensureDartInsightDetailModal();
        modal.querySelector("[data-dart-insight-detail-body]").innerHTML = `<p class="empty-copy">${escapeHtml(error.message || "상세 정보를 불러오지 못했습니다.")}</p>`;
      });
    });
  });
}

function countListedRelationships(items) {
  return items.filter((item) => item.lstgYn === "Y" || item.lstgYn === "상장").length;
}

function relationshipCompanyName(item, type) {
  const keys = type === "subsidiaries"
    ? ["sbrdEnpNm", "corpNm", "enpNm", "afilCmpyNm"]
    : ["afilCmpyNm", "corpNm", "enpNm", "sbrdEnpNm"];
  for (const key of keys) {
    if (item?.[key]) return item[key];
  }
  return "회사명 정보 없음";
}

function relationshipMetaItems(item) {
  return [
    ["상장여부", item.lstgYn || item.lstgYnNm],
    ["법인등록번호", item.crno],
    ["사업자번호", item.bzno],
    ["단축코드", item.srtnCd],
    ["ISIN", item.isinCd],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");
}

function relationshipPayload(items) {
  return attr(JSON.stringify(items));
}

function isListedRelationship(item) {
  return item.lstgYn === "Y" || item.lstgYn === "상장";
}

function relationshipCountryText(item) {
  return String(item.natnNm || item.country || item.cntryNm || item.enpBsadr || item.addr || "");
}

function filterRelationshipItems(items, filter) {
  if (filter === "listed") return items.filter(isListedRelationship);
  if (filter === "unlisted") return items.filter((item) => !isListedRelationship(item));
  if (filter === "domestic") {
    return items.filter((item) => {
      const country = relationshipCountryText(item);
      return !country || /대한민국|한국|Korea|KR|서울|경기|부산|대구|인천|광주|대전|울산|세종|제주/.test(country);
    });
  }
  if (filter === "foreign") {
    return items.filter((item) => {
      const country = relationshipCountryText(item);
      return country && !/대한민국|한국|Korea|KR|서울|경기|부산|대구|인천|광주|대전|울산|세종|제주/.test(country);
    });
  }
  return items;
}

function renderRelationshipFilters(activeFilter = "all") {
  const filters = [
    ["all", "전체"],
    ["listed", "상장"],
    ["unlisted", "비상장"],
    ["domestic", "국내"],
    ["foreign", "해외"],
  ];
  return `
    <div class="relationship-list-filters" role="tablist" aria-label="관계회사 필터">
      ${filters
        .map(
          ([value, label]) => `
            <button type="button" class="${value === activeFilter ? "is-active" : ""}" data-relationship-filter="${value}" aria-selected="${value === activeFilter ? "true" : "false"}">${label}</button>
          `,
        )
        .join("")}
    </div>
  `;
}

function relationshipTermDescription(type) {
  if (type === "subsidiaries") {
    return "현재 회사가 지배하는 회사입니다. 연결재무제표에 포함되는 자회사 성격의 회사로 보면 됩니다.";
  }
  if (type === "listed-affiliates") {
    return "같은 기업집단에 속한 회사 중 상장된 회사입니다.";
  }
  return "같은 기업집단에 속한 회사입니다. 현재 회사가 직접 지배하지 않는 그룹 내 회사도 포함될 수 있습니다.";
}

function relationshipSummaryButton({ type, label, count, items }) {
  const description = relationshipTermDescription(type);
  return `
    <button
      type="button"
      class="relationship-summary-card"
      data-relationship-list-type="${attr(type)}"
      data-relationship-list-label="${attr(label)}"
      data-relationship-list-payload="${relationshipPayload(items)}"
      ${items.length ? "" : "disabled"}
    >
      <span class="relationship-summary-label">
        ${label}
        <span class="relationship-summary-help" data-relationship-help title="${attr(description)}" aria-label="${attr(description)}">?</span>
      </span>
      <span class="relationship-summary-count">${count.toLocaleString("ko-KR")}</span>
      <span class="relationship-summary-tooltip" data-relationship-tooltip>${escapeHtml(description)}</span>
    </button>
  `;
}

function renderRelationshipSummary(info) {
  const affiliates = normalizeItems(info.affiliate);
  const subsidiaries = normalizeItems(info.cons_subs_comp);
  if (!affiliates.length && !subsidiaries.length) return "";
  const listedAffiliates = affiliates.filter((item) => item.lstgYn === "Y" || item.lstgYn === "상장");
  return `
    <article class="info-block company-relationship-summary">
      <div class="block-heading">
        <h3>관계회사 요약</h3>
      </div>
      <div class="relationship-summary-grid">
        <div>${relationshipSummaryButton({ type: "affiliates", label: "계열회사", count: affiliates.length, items: affiliates })}</div>
        <div>${relationshipSummaryButton({ type: "subsidiaries", label: "종속기업", count: subsidiaries.length, items: subsidiaries })}</div>
        <div>${relationshipSummaryButton({ type: "listed-affiliates", label: "상장 관계사", count: listedAffiliates.length, items: listedAffiliates })}</div>
      </div>
    </article>
  `;
}

function renderRelationshipListItems(items, type) {
  if (!items.length) {
    return `<p class="empty-copy">표시할 회사 목록이 없습니다.</p>`;
  }
  return `
    <ul class="relationship-list-items">
      ${items
        .map((item) => {
          const meta = relationshipMetaItems(item);
          return `
            <li>
              <strong>${escapeHtml(relationshipCompanyName(item, type))}</strong>
              ${
                meta.length
                  ? `<span>${meta.map(([label, value]) => `${escapeHtml(label)} ${escapeHtml(value)}`).join(" · ")}</span>`
                  : ""
              }
            </li>
          `;
        })
        .join("")}
    </ul>
  `;
}

function renderRelationshipListBody(items, type, activeFilter = "all") {
  const filteredItems = filterRelationshipItems(items, activeFilter);
  return `
    ${renderRelationshipFilters(activeFilter)}
    ${renderRelationshipListItems(filteredItems, type)}
  `;
}

function bindRelationshipFilterButtons(modal, items, type) {
  modal.querySelectorAll("[data-relationship-filter]").forEach((filterButton) => {
    filterButton.addEventListener("click", () => {
      const activeFilter = filterButton.dataset.relationshipFilter || "all";
      modal.querySelector("[data-relationship-list-body]").innerHTML = renderRelationshipListBody(items, type, activeFilter);
      bindRelationshipFilterButtons(modal, items, type);
    });
  });
}

function ensureRelationshipListModal() {
  const existing = document.querySelector(".relationship-list-modal");
  if (existing) return existing;
  const wrapper = document.createElement("div");
  wrapper.innerHTML = `
    <div class="relationship-list-modal" hidden>
      <button type="button" class="relationship-list-backdrop" data-relationship-list-close aria-label="닫기"></button>
      <section class="relationship-list-dialog" role="dialog" aria-modal="true" aria-labelledby="relationship-list-title">
        <div class="relationship-list-header">
          <div>
            <h3 id="relationship-list-title">관계회사</h3>
            <p id="relationship-list-meta"></p>
          </div>
          <button type="button" class="relationship-list-close" data-relationship-list-close aria-label="닫기">×</button>
        </div>
        <div class="relationship-list-body" data-relationship-list-body></div>
      </section>
    </div>
  `;
  const modal = wrapper.firstElementChild;
  document.body.appendChild(modal);
  modal.querySelectorAll("[data-relationship-list-close]").forEach((button) => {
    button.addEventListener("click", closeRelationshipListModal);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) closeRelationshipListModal();
  });
  return modal;
}

function closeRelationshipListModal() {
  const modal = document.querySelector(".relationship-list-modal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("has-relationship-list-open");
}

function openRelationshipListModal(button) {
  const items = JSON.parse(button.dataset.relationshipListPayload || "[]");
  const type = button.dataset.relationshipListType || "affiliates";
  const label = button.dataset.relationshipListLabel || "관계회사";
  const modal = ensureRelationshipListModal();
  modal.hidden = false;
  document.body.classList.add("has-relationship-list-open");
  modal.querySelector("#relationship-list-title").textContent = label;
  modal.querySelector("#relationship-list-meta").textContent = `총 ${items.length.toLocaleString("ko-KR")}개 · 출처 금융위원회 기업기본정보`;
  modal.querySelector("[data-relationship-list-body]").innerHTML = renderRelationshipListBody(items, type);
  bindRelationshipFilterButtons(modal, items, type);
}

function closeRelationshipTooltips(exceptCard = null) {
  document.querySelectorAll(".relationship-summary-card.is-tooltip-open").forEach((card) => {
    if (card !== exceptCard) card.classList.remove("is-tooltip-open");
  });
}

function toggleRelationshipTooltip(event) {
  event.preventDefault();
  event.stopPropagation();
  const card = event.currentTarget.closest(".relationship-summary-card");
  if (!card) return;
  const willOpen = !card.classList.contains("is-tooltip-open");
  closeRelationshipTooltips(card);
  card.classList.toggle("is-tooltip-open", willOpen);
}

function setupRelationshipSummaryCards() {
  document.querySelectorAll("[data-relationship-list-type]").forEach((button) => {
    if (button.dataset.relationshipListBound === "true") return;
    button.dataset.relationshipListBound = "true";
    button.querySelectorAll("[data-relationship-help]").forEach((help) => {
      help.addEventListener("click", toggleRelationshipTooltip);
    });
    button.addEventListener("click", (event) => {
      if (event.target.closest("[data-relationship-help]")) return;
      closeRelationshipTooltips();
      openRelationshipListModal(button);
    });
  });
}

function setupCompareActions() {
  document.querySelectorAll("[data-compare-add]").forEach((button) => {
    if (button.dataset.compareBound === "true") return;
    button.dataset.compareBound = "true";
    button.addEventListener("click", () => {
      const nextItems = addCompanyToCompare({
        crno: button.dataset.compareCrno,
        name: button.dataset.compareName,
      });
      button.textContent = "비교함에 추가됨";
      button.classList.add("is-added");
      const link = document.querySelector("[data-compare-link]");
      if (link) {
        link.href = compareUrl(nextItems);
        link.hidden = nextItems.length < 2;
      }
    });
  });
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
          if (isActive) {
            const moreLink = summary.querySelector(".financial-more-link");
            if (moreLink && panel.dataset.financialDetailUrl) {
              moreLink.href = panel.dataset.financialDetailUrl;
            }
            setupFinancialTrendCards();
          }
        });
      });
    });
  });
}

function renderSubpageHeader({ kicker, title, subtitle, crno }) {
  profileTitle.textContent = title;
  profileSubtitle.textContent = String(subtitle).replace(/<[^>]*>/g, "");
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

function renderDisclosuresPage({ disclosures, outline, crno, activeDisclosureType = "" }) {
  const items = disclosures?.list || [];
  const totalCount = disclosureTotalCount(disclosures);
  const loadedCount = items.length;
  profileDetail.innerHTML = `
    ${renderSubpageHeader({
      kicker: "DART 공시",
      title: `${text(outline.corpNm, "기업")} 공시`,
      subtitle: `<span data-disclosure-count="true">${disclosureCountText(loadedCount, totalCount)}</span>`,
      crno,
    })}
    <div class="detail-body subpage-body">
      <article class="info-block full disclosure-subpage-card">
        <h3>공시 목록</h3>
        ${renderDisclosureFilters(activeDisclosureType)}
        <ul class="disclosure-list disclosure-list-large" data-disclosure-list="true">
          ${disclosureListItemsHtml(items, true)}
        </ul>
        <div class="disclosure-load-status" data-disclosure-load-status="true" role="status"></div>
        <div class="disclosure-scroll-sentinel" data-disclosure-sentinel="true" aria-hidden="true"></div>
      </article>
    </div>
  `;
  setupDisclosureViewer();
  setupDisclosureSummaryButtons();
}

function renderCompanyStockCard({ outline, listed, stock, stockWindow, market, crno, stockLoading = false, disclosureEvents = [] }) {
  const summary = stock?.summary || {};
  const price = summary.price || summary.extracted_price;
  const change = summary.price_movement?.percentage || summary.price_movement?.value;
  const statusText = stockLoading ? "주가 정보를 불러오는 중입니다." : stockUpdatedLabel(stock);
  const hasListedStock = Boolean(listed.srtnCd);
  return `
    <article
      class="info-block company-market-card ${stockLoading ? "is-loading-stock" : ""}"
      data-stock-code="${attr(String(listed.srtnCd || "").replace(/^A/, ""))}"
      data-stock-exchange="KRX"
      data-stock-language="ko"
      data-crno="${attr(crno)}"
      data-disclosure-events="${attr(JSON.stringify(disclosureEvents || []))}"
    >
      <div class="block-heading">
        <h3>상장 및 주가</h3>
        <span class="market-pill">${market}</span>
      </div>
      <div class="price-row">
        <div>
          <span class="price-label">${text(listed.itmsNm || outline.corpNm, "종목")}</span>
          <div class="price">${formatNumber(price)}</div>
        </div>
        ${change ? `<div class="price-meta">${text(change)}</div>` : ""}
      </div>
      <div class="stock-chart-shell">
        ${
          hasListedStock
            ? renderStockChart(stock, stockWindow, statusText, disclosureEvents)
            : `<p class="stock-chart-empty">상장/주가 정보를 찾을 수 없습니다.</p>`
        }
      </div>
      ${
        hasListedStock
          ? renderSourceMeta([
              { label: "출처", value: "SearchAPI Google Finance" },
              { label: "캐시 만료", value: formatDateTime(stock?._meta?.expires_at) },
            ])
          : renderSourceMeta([{ label: "상태", value: "금융위원회 기본정보 기준 상장 종목을 찾지 못했습니다." }])
      }
    </article>
  `;
}

function refreshCompanyStockCard({ outline, listed, stock, stockWindow, market, crno, disclosureEvents = [] }) {
  const card = document.querySelector(".company-market-card");
  if (!card) return;
  card.outerHTML = renderCompanyStockCard({
    outline,
    listed,
    stock,
    stockWindow,
    market,
    crno,
    disclosureEvents,
  });
  setupStockChartInteractions();
  setupStockWindowTabs();
  setupDisclosureViewer();
  setupDisclosureSummaryButtons();
}

function renderCompanyProfileSummaryCard() {
  return `
    <article class="info-block company-ai-summary-card" data-company-profile-summary-card>
      <div class="block-heading">
        <h3>AI 기업 요약</h3>
        <span class="summary-status-pill" data-company-profile-summary-status>생성 중</span>
      </div>
      <div class="company-ai-summary-body company-ai-summary-skeleton" data-company-profile-summary-body aria-live="polite">
        <span class="skeleton-line skeleton-section-title"></span>
        <span class="skeleton-line skeleton-wide"></span>
        <span class="skeleton-line"></span>
      </div>
    </article>
  `;
}

function renderCompanyProfileSummaryList(items) {
  if (!Array.isArray(items) || !items.length) return "";
  return `
    <ul>
      ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
    </ul>
  `;
}

function renderCompanyProfileSummaryPayload(payload) {
  const summary = payload?.summary || {};
  return `
    <p class="company-ai-summary-headline">${escapeHtml(text(summary.headline, "요약 문장을 생성하지 못했습니다."))}</p>
    ${
      summary.bullets?.length
        ? `<section><h4>핵심 포인트</h4>${renderCompanyProfileSummaryList(summary.bullets)}</section>`
        : ""
    }
    ${
      summary.watch_points?.length
        ? `<section><h4>확인할 점</h4>${renderCompanyProfileSummaryList(summary.watch_points)}</section>`
        : ""
    }
    ${
      summary.data_basis?.length
        ? `<section><h4>데이터 기준</h4>${renderCompanyProfileSummaryList(summary.data_basis)}</section>`
        : ""
    }
    ${
      summary.limitations?.length
        ? `<section><h4>한계</h4>${renderCompanyProfileSummaryList(summary.limitations)}</section>`
        : ""
    }
    <p class="company-ai-summary-source">OpenAI 요약 · 금융위원회/DART 기반이며 투자 판단이 아닙니다.</p>
  `;
}

async function loadCompanyProfileSummary(crno) {
  const card = document.querySelector("[data-company-profile-summary-card]");
  if (!card || !crno) return;
  const body = card.querySelector("[data-company-profile-summary-body]");
  const status = card.querySelector("[data-company-profile-summary-status]");
  try {
    const payload = await fetchJson("/api/company/get_company_profile_summary", {
      corporate_registration_number: crno,
    });
    body.classList.remove("company-ai-summary-skeleton");
    body.innerHTML = renderCompanyProfileSummaryPayload(payload);
    if (status) status.textContent = payload.cached ? "저장됨" : "생성됨";
  } catch (error) {
    body.classList.remove("company-ai-summary-skeleton");
    body.innerHTML = `
      <p class="company-ai-summary-empty">기업 요약을 만들 수 없습니다.</p>
      <p class="company-ai-summary-source">${escapeHtml(error.message || "요약 요청에 실패했습니다.")}</p>
    `;
    if (status) status.textContent = "실패";
  }
}

function renderCompanyDetail({ info, outline, listed, stock, stockWindow, stockLoading = false }) {
  const crno = new URLSearchParams(window.location.search).get("crno");
  const dartCompany = info.dart_company || {};
  const homepage = homepageUrl(outline.enpHmpgUrl || dartCompany.hm_url);
  const market = text(listed.mrktCtg || outline.corpRegMrktDcdNm, "비상장/정보 없음");
  const companySummary = companySummaryText({ info, outline, listed, market });
  const logo = document.querySelector(".company-logo-box");
  const corpCode = info.dart_corp_code?.match?.corp_code || dartCompany.corp_code || "";
  const initialCompareItems = compareItems();
  const isCompareAdded = initialCompareItems.some((item) => item.crno === crno);

  profileTitle.textContent = text(outline.corpNm, "기업명 정보 없음");
  profileSubtitle.textContent = text(outline.corpEnsnNm || dartCompany.corp_name_eng, "영문명 정보 없음");
  profileDetail.dataset.dartCorpCode = corpCode;
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
            <div class="profile-heading-actions">
              <button
                type="button"
                class="compare-add-button ${isCompareAdded ? "is-added" : ""}"
                data-compare-add
                data-compare-crno="${attr(crno)}"
                data-compare-name="${attr(outline.corpNm || listed.itmsNm)}"
              >${isCompareAdded ? "비교함에 추가됨" : "비교에 추가"}</button>
              <a class="compare-link-button" href="${attr(compareUrl(initialCompareItems))}" data-compare-link ${initialCompareItems.length >= 2 ? "" : "hidden"}>비교 보기</a>
              ${homepage ? `<a class="homepage-icon-link" href="${homepage}" target="_blank" rel="noreferrer" aria-label="홈페이지" title="홈페이지"><span aria-hidden="true">↗</span></a>` : ""}
            </div>
          </div>
          <p class="company-summary">
            ${escapeHtml(companySummary)}
          </p>
          <section class="company-profile-info-section" aria-label="기업 정보">
            <h3>기업 정보</h3>
            <dl class="company-facts">
              <div><dt>대표자</dt><dd>${text(outline.enpRprFnm || dartCompany.ceo_nm)}</dd></div>
              <div><dt>설립일</dt><dd>${compactDate(outline.enpEstbDt || dartCompany.est_dt)}</dd></div>
              <div><dt>직원 수</dt><dd>${formatNumber(outline.enpEmpeCnt)}</dd></div>
              <div><dt>전화번호</dt><dd>${text(outline.enpTlno || dartCompany.phn_no)}</dd></div>
              <div><dt>법인등록번호</dt><dd>${text(outline.crno || dartCompany.jurir_no || crno)}</dd></div>
              <div><dt>사업자번호</dt><dd>${text(outline.bzno || dartCompany.bizr_no)}</dd></div>
              <div><dt>DART 고유번호</dt><dd>${text(dartCompany.corp_code || info.dart_corp_code?.match?.corp_code)}</dd></div>
              <div><dt>FSS 고유번호</dt><dd>${text(outline.fssCorpUnqNo)}</dd></div>
              <div><dt>시장</dt><dd>${market}</dd></div>
              <div><dt>단축코드</dt><dd>${text(listed.srtnCd)}</dd></div>
              <div><dt>ISIN</dt><dd>${text(listed.isinCd)}</dd></div>
              <div><dt>업종</dt><dd>${text(outline.enpMainBizNm || listed.itmsNm, "정보 없음")}</dd></div>
              <div><dt>최초 영업일</dt><dd>${compactDate(outline.fstOpegDt)}</dd></div>
              <div><dt>최종 영업일</dt><dd>${compactDate(outline.lastOpegDt)}</dd></div>
            </dl>
            ${renderSourceMeta([
              { label: "출처", value: "금융위원회 기업기본정보 · DART" },
              { label: "기준일", value: compactDate(outline.basDt || listed.basDt) },
            ])}
          </section>
        </article>

        ${renderCompanyProfileSummaryCard()}

        ${renderCompanyStockCard({ outline, listed, stock, stockWindow, market, crno, stockLoading, disclosureEvents: info.disclosure_events })}

        ${renderCompanyInsightRow(info)}

        ${renderDisclosureEventTimeline(info.disclosure_events)}

        ${renderCompanyInsightCards(info.dart_insights)}

        ${renderRiskSignalCards(info.risk_signals)}

        ${renderRelationshipSummary(info)}

        <article class="info-block company-address-card">
          <h3>주소</h3>
          <p>${text(outline.enpBsadr, "주소 정보 없음")}</p>
        </article>
      </div>

    </div>
  `;
  setupStockChartInteractions();
  setupStockWindowTabs();
  setupFinancialSummaryTabs();
  setupFinancialTrendCards();
  setupDartInsightDetailButtons();
  setupRelationshipSummaryCards();
  setupCompareActions();
  setupDisclosureViewer();
  setupDisclosureSummaryButtons();
}

async function loadProfile() {
  const searchParams = new URLSearchParams(window.location.search);
  setupReturnSearchLink(searchParams);
  const crno = searchParams.get("crno");
  const view = searchParams.get("view");
  const stockWindow = selectedStockWindow(searchParams);
  const disclosureType = selectedDisclosureType(searchParams);
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
            disclosure_type: disclosureType,
            page: 1,
            per_page: DISCLOSURE_PAGE_SIZE,
          }).catch(() => info.dart_disclosures)
        : info.dart_disclosures;
      renderDisclosuresPage({ disclosures, outline, crno, activeDisclosureType: disclosureType });
      setupInfiniteDisclosureScroll({
        corpCode,
        disclosureType,
        initialPage: 1,
        perPage: DISCLOSURE_PAGE_SIZE,
        loadedCount: disclosures?.list?.length || 0,
        totalCount: disclosureTotalCount(disclosures),
      });
      setupDisclosureFilters({ corpCode, outline, crno });
      return;
    }

    const market = text(listed.mrktCtg || outline.corpRegMrktDcdNm, "비상장/정보 없음");
    const shouldLoadStock = Boolean(listed.srtnCd);
    renderCompanyDetail({
      info,
      outline,
      listed,
      stock: null,
      stockWindow,
      stockLoading: shouldLoadStock,
    });
    loadCompanyProfileSummary(crno);

    if (listed.srtnCd) {
      const stock = await fetchJson(stockUrl, {
        stock_code: listed.srtnCd.replace(/^A/, ""),
        exchange: "KRX",
        language: "ko",
        window: stockWindow,
        corporate_registration_number: crno,
      }).catch(() => null);
      refreshCompanyStockCard({
        outline,
        listed,
        stock,
        stockWindow,
        market,
        crno,
        disclosureEvents: info.disclosure_events,
      });
    }
  } catch (error) {
    renderError(error.message);
  }
}

loadProfile();
