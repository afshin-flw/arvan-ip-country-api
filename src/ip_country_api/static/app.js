"use strict";

const form = document.querySelector("#lookup-form");
const input = document.querySelector("#ip-address");
const button = document.querySelector("#submit-button");
const message = document.querySelector("#form-message");
const result = document.querySelector("#result");

const setLoading = (loading) => {
  button.disabled = loading;
  button.classList.toggle("loading", loading);
  button.setAttribute("aria-busy", String(loading));
};

const displayTime = (value) => new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "medium",
}).format(new Date(value));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const ip = input.value.trim();
  message.textContent = "";
  result.hidden = true;
  if (!ip) {
    message.textContent = "Enter a public IPv4 or IPv6 address.";
    input.focus();
    return;
  }

  setLoading(true);
  try {
    const response = await fetch("/api/v1/lookups", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ip}),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "The lookup could not be completed.");
    }
    document.querySelector("#country-name").textContent = payload.country_name;
    document.querySelector("#country-code").textContent = payload.country_code;
    document.querySelector("#normalized-ip").textContent = payload.ip;
    document.querySelector("#fetched-at").textContent = displayTime(payload.fetched_at);
    document.querySelector("#expires-at").textContent = displayTime(payload.expires_at);
    const source = document.querySelector("#source");
    source.textContent = payload.source;
    source.className = `badge ${payload.source}`;
    result.hidden = false;
    result.focus({preventScroll: true});
  } catch (error) {
    message.textContent = error instanceof Error ? error.message : "The lookup could not be completed.";
  } finally {
    setLoading(false);
  }
});
