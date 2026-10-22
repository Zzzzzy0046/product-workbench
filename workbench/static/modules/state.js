"use strict";

let state,
  projectId = localStorage.getItem("workbench-project"),
  tab = "overview",
  activeWorkflow = null,
  activeWorkflowStage = null,
  activeJob = null,
  outputFilter = "latest",
  polling = false,
  renderedBlocks = {},
  toastTimer;
