"use strict";

async function api(path, body) {
  const response = await fetch(
    path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Workbench-Token": state?.token || "",
          },
          body: JSON.stringify(body),
        },
  );
  const data = await response.json();
  if (!response.ok) throw Error(data.error || "请求失败");
  return data;
}
async function refresh(render = true) {
  state = await api(
    "/api/state" +
      (projectId ? "?project=" + encodeURIComponent(projectId) : ""),
  );
  if (render) draw();
}
