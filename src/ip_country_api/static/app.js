"use strict";

const API_PATH = "/api/v1/lookups";
const REQUEST_TIMEOUT_MS = 12000;

const ERROR_MESSAGES = Object.freeze({
  INVALID_IP: {
    title: "That IP address cannot be looked up",
    message: "Please enter a valid public IPv4 or IPv6 address.",
    kind: "validation-error",
  },
  NON_PUBLIC_IP: {
    title: "That address is not public",
    message: "Private, loopback, reserved, and link-local addresses cannot be resolved by this service.",
    kind: "validation-error",
  },
  DATABASE_UNAVAILABLE: {
    title: "The lookup service is temporarily unavailable",
    message: "The application cannot currently reach its PostgreSQL cache. Please try again shortly.",
    kind: "backend-error",
  },
  DATABASE_SCHEMA_UNAVAILABLE: {
    title: "The lookup service is starting up",
    message: "The data store is not ready yet. Please wait a moment and try again.",
    kind: "backend-error",
  },
  PROVIDER_TIMEOUT: {
    title: "The lookup took too long",
    message: "The GeoIP provider did not respond in time. Please try again.",
    kind: "backend-error",
  },
  PROVIDER_AUTHENTICATION_FAILED: {
    title: "The GeoIP provider is unavailable",
    message: "The upstream lookup service could not accept this request. Please try again later.",
    kind: "backend-error",
  },
  PROVIDER_RATE_LIMITED: {
    title: "Too many provider requests",
    message: "The GeoIP provider is temporarily rate limited. Please wait and try again.",
    kind: "backend-error",
  },
  PROVIDER_INVALID_RESPONSE: {
    title: "The provider returned an unexpected result",
    message: "Country data could not be verified for this address. Please try again.",
    kind: "backend-error",
  },
  PROVIDER_UNAVAILABLE: {
    title: "The GeoIP provider is temporarily unavailable",
    message: "Fresh country data cannot be retrieved right now. Please try again shortly.",
    kind: "backend-error",
  },
  INTERNAL_ERROR: {
    title: "The lookup could not be completed",
    message: "An unexpected problem occurred. Please try again.",
    kind: "backend-error",
  },
});

const SOURCE_PRESENTATION = Object.freeze({
  provider: {
    label: "Fresh provider lookup",
    detail: "External GeoIP provider",
    note: "This IP was not found in the local cache, so fresh country data was retrieved and stored.",
    state: "success-provider",
  },
  database: {
    label: "PostgreSQL cache",
    detail: "PostgreSQL cache",
    note: "This result was served directly from PostgreSQL without another external request.",
    state: "success-database",
  },
});

const form = document.querySelector("#lookup-form");
const input = document.querySelector("#ip-address");
const button = document.querySelector("#submit-button");
const buttonLabel = button.querySelector(".button-label");
const buttonLoading = button.querySelector(".button-loading");
const formMessage = document.querySelector("#form-message");
const loadingState = document.querySelector("#loading-state");
const result = document.querySelector("#result");
const errorState = document.querySelector("#error-state");
const retryButton = document.querySelector("#retry-button");
const announcer = document.querySelector("#status-announcer");
const exampleButtons = [...document.querySelectorAll("[data-example-ip]")];

let activeController = null;

const setPageState = (state) => {
  document.body.dataset.state = state;
};

const announce = (text) => {
  announcer.textContent = "";
  window.requestAnimationFrame(() => {
    announcer.textContent = text;
  });
};

const setLoading = (loading) => {
  form.setAttribute("aria-busy", String(loading));
  input.disabled = loading;
  button.disabled = loading;
  buttonLabel.hidden = loading;
  buttonLoading.hidden = !loading;
  exampleButtons.forEach((exampleButton) => {
    exampleButton.disabled = loading;
  });
};

const clearFeedback = () => {
  formMessage.textContent = "";
  input.removeAttribute("aria-invalid");
  loadingState.hidden = true;
  result.hidden = true;
  errorState.hidden = true;
};

const displayTime = (value) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Not available";
  }
  return `${new Intl.DateTimeFormat(undefined, {
    dateStyle: "long",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date)} UTC`;
};

const showLoading = () => {
  clearFeedback();
  setPageState("loading");
  loadingState.hidden = false;
  announce("Lookup started. Checking the local cache and GeoIP provider.");
};

const showValidationMessage = (message) => {
  clearFeedback();
  setPageState("validation-error");
  input.setAttribute("aria-invalid", "true");
  formMessage.textContent = message;
  announce(message);
  input.focus();
};

const showResult = (payload) => {
  const presentation = SOURCE_PRESENTATION[payload.source] || SOURCE_PRESENTATION.provider;
  clearFeedback();
  setPageState(presentation.state);

  document.querySelector("#country-name").textContent = payload.country_name;
  document.querySelector("#country-code").textContent = payload.country_code;
  document.querySelector("#normalized-ip").textContent = payload.ip;
  document.querySelector("#source-label").textContent = presentation.label;
  document.querySelector("#source-detail").textContent = presentation.detail;
  document.querySelector("#source-note").textContent = presentation.note;
  document.querySelector("#fetched-at").textContent = displayTime(payload.fetched_at);
  document.querySelector("#expires-at").textContent = displayTime(payload.expires_at);

  const sourceBadge = document.querySelector("#source");
  sourceBadge.className = `source-badge ${payload.source === "database" ? "database" : "provider"}`;
  result.hidden = false;
  announce(`Lookup complete. ${payload.country_name}. ${presentation.label}.`);
  result.focus({preventScroll: true});
};

const showError = (code, requestId, override = null) => {
  const error = override || ERROR_MESSAGES[code] || ERROR_MESSAGES.INTERNAL_ERROR;
  clearFeedback();
  setPageState(error.kind);
  document.querySelector("#error-title").textContent = error.title;
  document.querySelector("#error-message").textContent = error.message;

  const requestIdWrap = document.querySelector("#request-id-wrap");
  const requestIdValue = document.querySelector("#request-id");
  const hasRequestId = typeof requestId === "string" && requestId.length > 0;
  requestIdWrap.hidden = !hasRequestId;
  requestIdValue.textContent = hasRequestId ? requestId : "";

  errorState.hidden = false;
  announce(`${error.title}. ${error.message}`);
  if (error.kind === "validation-error") {
    input.setAttribute("aria-invalid", "true");
    input.focus({preventScroll: true});
  } else {
    errorState.focus({preventScroll: true});
  }
};

const parsePayload = async (response) => {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    return null;
  }
  try {
    return await response.json();
  } catch {
    return null;
  }
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (button.disabled) {
    return;
  }

  const ip = input.value.trim();
  input.value = ip;
  if (!ip) {
    showValidationMessage("Enter a public IPv4 or IPv6 address.");
    return;
  }

  if (activeController) {
    activeController.abort();
  }
  const controller = new AbortController();
  activeController = controller;
  let timedOut = false;
  const timeoutId = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);

  setLoading(true);
  showLoading();

  try {
    const response = await fetch(API_PATH, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ip}),
      signal: controller.signal,
    });
    const payload = await parsePayload(response);
    if (!response.ok || !payload) {
      const apiError = payload?.error;
      showError(apiError?.code, apiError?.request_id);
      return;
    }
    showResult(payload);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError" && !timedOut) {
      return;
    }
    showError(null, null, timedOut ? {
      title: "The lookup timed out",
      message: "The service did not respond in time. Check your connection and try again.",
      kind: "network-error",
    } : {
      title: "The service could not be reached",
      message: "Check your network connection and try the lookup again.",
      kind: "network-error",
    });
  } finally {
    window.clearTimeout(timeoutId);
    if (activeController === controller) {
      activeController = null;
      setLoading(false);
    }
  }
});

exampleButtons.forEach((exampleButton) => {
  exampleButton.addEventListener("click", () => {
    input.value = exampleButton.dataset.exampleIp || "";
    input.removeAttribute("aria-invalid");
    formMessage.textContent = "";
    input.focus();
  });
});

retryButton.addEventListener("click", () => {
  form.requestSubmit();
});
