from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ITSMAdapter(ABC):
    @abstractmethod
    def create_ticket(self, diagnostic_summary: dict[str, Any]) -> str:
        raise NotImplementedError


class MockITSMAdapter(ITSMAdapter):
    def create_ticket(self, diagnostic_summary: dict[str, Any]) -> str:
        # Persistence is owned by the tool registry; adapter supplies an external-style ID.
        from datetime import UTC, datetime

        suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")[-12:]
        return f"TKT-{suffix}"


class JiraServiceManagementAdapter(ITSMAdapter):
    def create_ticket(self, diagnostic_summary: dict[str, Any]) -> str:
        raise RuntimeError("Jira adapter requires deployment credentials and an approved field mapping")


class ServiceNowAdapter(ITSMAdapter):
    def create_ticket(self, diagnostic_summary: dict[str, Any]) -> str:
        raise RuntimeError("ServiceNow adapter requires deployment credentials and an approved field mapping")

