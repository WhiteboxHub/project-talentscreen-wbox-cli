"""Factory for creating ATS handlers.

All 20 supported ATSType values have a dedicated handler.
ATSType.UNKNOWN falls back to GenericATSHandler.
"""

from typing import Optional

from playwright.sync_api import Page

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import ATSType, ResumeData
from jobcli.locators.ats.base_handler import BaseATSHandler
from jobcli.locators.ats.generic_handler import GenericATSHandler

# Platform-specific handlers
from jobcli.locators.ats.greenhouse_handler import GreenhouseHandler
from jobcli.locators.ats.lever_handler import LeverHandler
from jobcli.locators.ats.workday_handler import WorkdayHandler
from jobcli.locators.ats.icims_handler import IcimsHandler
from jobcli.locators.ats.taleo_handler import TaleoHandler
from jobcli.locators.ats.successfactors_handler import SuccessFactorsHandler
from jobcli.locators.ats.smartrecruiters_handler import SmartRecruitersHandler
from jobcli.locators.ats.jobvite_handler import JobviteHandler
from jobcli.locators.ats.ashby_handler import AshbyHandler
from jobcli.locators.ats.breezy_handler import BreezyHandler
from jobcli.locators.ats.recruitee_handler import RecruiteeHandler
from jobcli.locators.ats.jazzhr_handler import JazzHRHandler
from jobcli.locators.ats.bamboohr_handler import BambooHRHandler
from jobcli.locators.ats.workable_handler import WorkableHandler
from jobcli.locators.ats.adp_handler import ADPHandler
from jobcli.locators.ats.paylocity_handler import PaylocityHandler
from jobcli.locators.ats.ukg_handler import UKGHandler
from jobcli.locators.ats.cornerstone_handler import CornerstoneHandler
from jobcli.locators.ats.avature_handler import AvatureHandler
from jobcli.locators.ats.phenom_handler import PhenomHandler


class ATSHandlerFactory:
    """Factory for creating ATS-specific handlers.

    Every ATSType (except UNKNOWN) has a dedicated handler that extends
    GenericATSHandler.  UNKNOWN and any future unregistered types fall
    back to GenericATSHandler directly (never returns None).
    """

    _HANDLERS: dict[ATSType, type[BaseATSHandler]] = {
        ATSType.GREENHOUSE:         GreenhouseHandler,
        ATSType.LEVER:              LeverHandler,
        ATSType.WORKDAY:            WorkdayHandler,
        ATSType.ICIMS:              IcimsHandler,
        ATSType.TALEO:              TaleoHandler,
        ATSType.SAP_SUCCESSFACTORS: SuccessFactorsHandler,
        ATSType.SMARTRECRUITERS:    SmartRecruitersHandler,
        ATSType.JOBVITE:            JobviteHandler,
        ATSType.ASHBY:              AshbyHandler,
        ATSType.BREEZY_HR:          BreezyHandler,
        ATSType.RECRUITEE:          RecruiteeHandler,
        ATSType.JAZZ_HR:            JazzHRHandler,
        ATSType.BAMBOO_HR:          BambooHRHandler,
        ATSType.WORKABLE:           WorkableHandler,
        ATSType.ADP_RECRUITING:     ADPHandler,
        ATSType.PAYLOCITY:          PaylocityHandler,
        ATSType.UKG_PRO:            UKGHandler,
        ATSType.CORNERSTONE:        CornerstoneHandler,
        ATSType.AVATURE:            AvatureHandler,
        ATSType.PHENOM_PEOPLE:      PhenomHandler,
        # ATSType.UNKNOWN → generic fallback (see create_handler)
    }

    @staticmethod
    def create_handler(
        ats_type: ATSType,
        page: Page,
        resume: ResumeData,
        logger: Optional[JobLogger] = None,
    ) -> BaseATSHandler:
        """Create the appropriate ATS handler.

        Always returns a handler (never None):
          - Known ATSType  → dedicated platform handler
          - UNKNOWN / new  → GenericATSHandler (heuristic confidence engine)
        """
        handler_class = ATSHandlerFactory._HANDLERS.get(ats_type)
        if handler_class:
            return handler_class(page, resume, logger)

        if logger:
            logger.info(
                f"No dedicated handler for {ats_type.value!r} — using GenericATSHandler",
            )
        return GenericATSHandler(page, resume, logger)

    @staticmethod
    def get_supported_ats() -> list[ATSType]:
        """Return ATSType values that have a dedicated handler."""
        return list(ATSHandlerFactory._HANDLERS.keys())

    @staticmethod
    def is_dedicated(ats_type: ATSType) -> bool:
        """Return True if a dedicated (non-generic) handler exists."""
        return ats_type in ATSHandlerFactory._HANDLERS
