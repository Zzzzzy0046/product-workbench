"""Stable boundary around task-specific deliverable validators."""


class ValidationService:
    def check(self, task_id, output, workflow_mode="fast", sources=None):
        try:
            from workbench.validators import summarize, validate
        except ModuleNotFoundError:
            from validators import summarize, validate
        return summarize(validate(task_id, output, workflow_mode, sources or []))
