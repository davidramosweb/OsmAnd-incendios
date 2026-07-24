const EXPECTED_ZONE_IDS = [53, 54, 55, 56, 57, 58, 59];
const zoneCards = new Map(
  [...document.querySelectorAll("[data-zone-id]")].map((element) => [
    Number(element.dataset.zoneId),
    element,
  ]),
);

const statusCard = document.querySelector("#live-status");
const statusSymbol = statusCard?.querySelector(".status-card__symbol");
const statusSummary = document.querySelector("#status-summary");
const statusDetail = document.querySelector("#status-detail");
const statusTime = document.querySelector("#status-time");
const periodButtons = [...document.querySelectorAll("[data-period]")];
let loadedStatus = null;
let selectedPeriod = "current";

function isValidZones(value, forecast = false) {
  if (!Array.isArray(value) || value.length !== EXPECTED_ZONE_IDS.length) return false;
  return value.every((zone, index) =>
    typeof zone === "object" &&
    zone !== null &&
    zone.zoneId === EXPECTED_ZONE_IDS[index] &&
    [1, 2, 3].includes(zone.level) &&
    (!forecast || zone.forestAccess === undefined),
  );
}

function isValidStatus(value) {
  if (typeof value !== "object" || value === null || typeof value.isStale !== "boolean") {
    return false;
  }
  if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,3})?$/.test(value.sourceTimestampOriginal)) {
    return false;
  }
  if (!isValidZones(value.zones)) return false;
  const forecast = value.forecastNextDay;
  return typeof forecast === "object" &&
    forecast !== null &&
    /^\d{4}-\d{2}-\d{2}$/.test(forecast.validDate) &&
    typeof forecast.isStale === "boolean" &&
    isValidZones(forecast.zones, true);
}

function sourceTimeMarkup(sourceTimestamp) {
  const match = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})/.exec(sourceTimestamp);
  if (!match) return { label: "Hora no disponible", iso: "" };
  const [, year, month, day, hour, minute, second] = match;
  return {
    label: `${day}/${month}/${year}, ${hour}:${minute} (Europe/Madrid)`,
    iso: `${year}-${month}-${day}T${hour}:${minute}:${second}`,
  };
}

function displayDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value;
}

function setStatusKind(kind) {
  statusCard?.classList.remove(
    "status-card--current",
    "status-card--forecast",
    "status-card--stale",
    "status-card--unavailable",
  );
  statusCard?.classList.add(`status-card--${kind}`);
}

function resetZones() {
  for (const card of zoneCards.values()) {
    card.className = "zone-card zone-card--unavailable";
    card.querySelector(".zone-card__level").textContent = "No disponible";
  }
}

function showUnavailable(detail) {
  setStatusKind("unavailable");
  if (statusSymbol) statusSymbol.textContent = "?";
  if (statusSummary) statusSummary.textContent = "Estado no disponible";
  if (statusDetail) statusDetail.textContent = detail;
  if (statusTime) {
    statusTime.textContent = "Consulte 112CV antes de desplazarse";
    statusTime.removeAttribute("datetime");
  }
  resetZones();
}

function showStatus(status, period) {
  const forecast = period === "forecast_next_day";
  const periodStatus = forecast ? status.forecastNextDay : status;
  const stale = periodStatus.isStale;
  const time = sourceTimeMarkup(status.sourceTimestampOriginal);
  setStatusKind(stale ? "stale" : forecast ? "forecast" : "current");
  if (statusSymbol) statusSymbol.textContent = stale ? "!" : forecast ? "↗" : "✓";
  if (statusSummary) {
    statusSummary.textContent = stale
      ? `Último parte disponible · ${forecast ? "Mañana" : "Hoy"}`
      : forecast
        ? `Previsión para el ${displayDate(periodStatus.validDate)}`
        : "Datos de hoy";
  }
  if (statusDetail) {
    statusDetail.textContent = stale
      ? "La fuente todavía no ha publicado un parte fechado para hoy; se conservan los últimos colores recibidos."
      : forecast
        ? "Nivel de riesgo previsto; no confirma cierres futuros."
        : "La fuente corresponde al día actual en Europe/Madrid.";
  }
  if (statusTime) {
    statusTime.textContent = `Fuente actualizada: ${time.label}`;
    statusTime.setAttribute("datetime", time.iso);
  }

  for (const zone of periodStatus.zones) {
    const card = zoneCards.get(zone.zoneId);
    if (!card) continue;
    card.className = `zone-card zone-card--level-${zone.level}${forecast ? " zone-card--forecast" : ""}`;
    const label = card.querySelector(".zone-card__level");
    label.textContent = forecast
      ? `Nivel ${zone.level} previsto${zone.level === 3 ? " · no confirma cierre" : ""}`
      : zone.level === 3
        ? "Nivel 3 · cierre preventivo"
        : `Nivel ${zone.level} · no confirma apertura`;
  }
}

function selectPeriod(period) {
  selectedPeriod = period;
  for (const button of periodButtons) {
    button.setAttribute("aria-pressed", String(button.dataset.period === period));
  }
  if (loadedStatus) showStatus(loadedStatus, selectedPeriod);
}

for (const button of periodButtons) {
  button.addEventListener("click", () => selectPeriod(button.dataset.period));
}

async function loadStatus() {
  if (statusSummary) statusSummary.textContent = "Consultando estado…";
  try {
    const response = await fetch("/status.json", {
      headers: { accept: "application/json" },
    });
    if (!response.ok) throw new Error("status unavailable");
    const status = await response.json();
    if (!isValidStatus(status)) throw new Error("invalid status");
    loadedStatus = status;
    showStatus(status, selectedPeriod);
  } catch {
    showUnavailable(
      "No se ha podido validar el estado. Consulte la fuente oficial antes de desplazarse.",
    );
  }
}

void loadStatus();
