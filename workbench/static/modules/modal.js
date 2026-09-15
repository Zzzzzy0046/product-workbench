"use strict";

function modal(label, html) {
  $("#modal-label").textContent = label;
  $("#modal-body").innerHTML = html;
  if (!$("#modal").open) $("#modal").showModal();
}
function close() {
  activeJob = null;
  $("#modal").close();
}
$("#close-modal").onclick = close;
$("#modal").addEventListener("cancel", () => (activeJob = null));
document.addEventListener("error", (event) => {
  const image = event.target;
  if (image?.matches?.("img.document-image")) {
    image.classList.add("image-load-error");
    image.alt = `${image.alt || "项目图片"}（加载失败，请检查图片资料）`;
  }
}, true);
