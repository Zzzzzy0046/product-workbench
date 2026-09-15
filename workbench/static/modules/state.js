"use strict";

let state,
  projectId = localStorage.getItem("workbench-project"),
  tab = "overview",
  activeWorkflow = null,
  activeJob = null,
  outputFilter = "latest",
  polling = false,
  renderedBlocks = {},
  toastTimer;
