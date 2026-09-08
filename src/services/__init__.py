"""Unconfigured services fail closed; no teammate algorithms are implemented."""
from src.exceptions import ServiceUnavailable


class UnconfiguredService:
    def __getattr__(self, name):
        def unavailable(*args, **kwargs):
            raise ServiceUnavailable(f"Service adapter required for '{name}'.")
        return unavailable
