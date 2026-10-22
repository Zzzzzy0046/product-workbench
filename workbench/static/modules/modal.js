"use strict";

function modal(label, html, { wide = false } = {}) {
  $("#modal-label").textContent = label;
  $("#modal-body").innerHTML = html;
  $("#modal").classList.toggle("wide", wide);
  if (!$("#modal").open) $("#modal").showModal();
}

// Forms opt in with data-dirty-guard and an isDirty() function; anything else
// (or a form whose value matches its initial text) closes without asking.
function hasUnsavedEdits(root = document) {
  return [...root.querySelectorAll("[data-dirty-guard]")].some((form) =>
    typeof form.isDirty === "function" ? form.isDirty() : false,
  );
}

async function confirmDiscardEdits(root = document) {
  if (!hasUnsavedEdits(root)) return true;
  return window.confirm("有未保存的修改，确定放弃吗？");
}

function guardForm(form) {
  if (!form) return;
  const fields = () => [...form.querySelectorAll("textarea, input:not([type=checkbox]):not([type=radio]):not([type=file]), select")].map((item) => item.value).join("\u0000");
  const initial = fields();
  form.dataset.dirtyGuard = "true";
  form.isDirty = () => fields() !== initial;
}

function close() {
  activeJob = null;
  $("#modal").close();
}
async function requestClose() {
  if (!(await confirmDiscardEdits($("#modal")))) return;
  close();
}
$("#close-modal").onclick = requestClose;
$("#modal").addEventListener("cancel", (event) => {
  event.preventDefault();
  requestClose();
});
window.addEventListener("beforeunload", (event) => {
  if (hasUnsavedEdits()) {
    event.preventDefault();
    event.returnValue = "";
  }
});
document.addEventListener("error", (event) => {
  const image = event.target;
  if (image?.matches?.("img.document-image")) {
    image.classList.add("image-load-error");
    image.alt = `${image.alt || "项目图片"}（加载失败，请检查图片资料）`;
  }
}, true);
