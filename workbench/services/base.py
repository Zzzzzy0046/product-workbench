"""Small binding primitive shared by domain services."""


class BoundService:
    """Expose the Workbench host to migrated methods without global state."""

    def __init__(self, workbench):
        object.__setattr__(self, "_workbench", workbench)

    def __getattr__(self, name):
        return getattr(self._workbench, name)

    def __setattr__(self, name, value):
        if name == "_workbench":
            object.__setattr__(self, name, value)
            return
        setattr(self._workbench, name, value)
