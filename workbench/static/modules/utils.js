"use strict";

const $ = (s) => document.querySelector(s);
const escapeHTML = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const E = escapeHTML;
const date = (s) =>
  new Date(s).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
const badge = (status) =>
  `<span class="tag ${["failed", "interrupted"].includes(status) ? "bad" : ["running", "queued"].includes(status) ? "run" : status === "prepared" ? "warn" : ""}">${E(statusNames[status] || status)}</span>`;
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("#toast").hidden = true), 4500);
}
function error(err) {
  toast(err.message);
  console.error(err);
}
