"""Factory for creating ATS handlers."""

from typing import Optional

from playwright.sync_api import Page

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import ATSType, ResumeData
from jobcli.locators.ats.base_handler import BaseATSHandler
from jobcli.locators.ats.greenhouse_handler import GreenhouseHandler
from jobcli.locators.ats.lever_handler import LeverHandler
from jobcli.locators.ats.workday_handler import WorkdayHandler


class ATSHandlerFactory:
    """Factory for creating ATS-specific handlers."""

    @staticmethod
    def create_handler(
        ats_type: ATSType,
        page: Page,
        resume: ResumeData,
        logger: Optional[JobLogger] = None,
    ) -> Optional[BaseATSHandler]:
        """Create appropriate ATS handler."""
        handlers = {
            ATSType.GREENHOUSE: GreenhouseHandler,
            ATSType.LEVER: LeverHandler,
            ATSType.WORKDAY: WorkdayHandler,
            # Add more handlers as implemented
        }

        handler_class = handlers.get(ats_type)
        if handler_class:
            return handler_class(page, resume, logger)

        return None

    @staticmethod
    def get_supported_ats() -> list[ATSType]:
        """Get list of supported ATS systems."""
        return [
            ATSType.GREENHOUSE,
            ATSType.LEVER,
            ATSType.WORKDAY,
            # Add more as implemented
        ]
