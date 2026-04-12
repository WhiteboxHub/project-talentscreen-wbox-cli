"""Rule-based locators for form fields."""

from typing import Any, Optional

from playwright.sync_api import Page

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import ExecutionPhase, ResumeData, SelectorType


class FormFieldLocator:
    """Locator for form fields."""

    def __init__(self, page: Page, logger: Optional[JobLogger] = None) -> None:
        """Initialize field locator."""
        self.page = page
        self.logger = logger

    def find_field_by_label(
        self, labels: list[str], field_type: str = "input"
    ) -> Optional[str]:
        """Find field by label text."""
        for label in labels:
            try:
                # Try label element
                selector = f"label:has-text('{label}') + {field_type}"
                if self.page.query_selector(selector):
                    return selector

                # Try placeholder
                selector = f"{field_type}[placeholder*='{label}' i]"
                if self.page.query_selector(selector):
                    return selector

                # Try name attribute
                selector = f"{field_type}[name*='{label.lower().replace(' ', '_')}']"
                if self.page.query_selector(selector):
                    return selector

                # Try id attribute
                selector = f"{field_type}[id*='{label.lower().replace(' ', '_')}']"
                if self.page.query_selector(selector):
                    return selector

            except Exception:
                continue

        return None

    def fill_text_field(self, labels: list[str], value: str) -> bool:
        """Fill text field."""
        selector = self.find_field_by_label(labels, "input")

        if not selector:
            selector = self.find_field_by_label(labels, "textarea")

        if selector:
            try:
                self.page.fill(selector, value, timeout=3000)
                if self.logger:
                    self.logger.info(
                        f"Filled field: {labels[0]}",
                        phase=ExecutionPhase.RULES,
                        selector=selector,
                        value=value[:50],
                    )
                return True
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"Failed to fill field: {labels[0]}",
                        phase=ExecutionPhase.RULES,
                        error=str(e),
                    )

        return False

    def fill_select_field(self, labels: list[str], value: str) -> bool:
        """Fill select dropdown."""
        selector = self.find_field_by_label(labels, "select")

        if selector:
            try:
                self.page.select_option(selector, value, timeout=3000)
                if self.logger:
                    self.logger.info(
                        f"Selected option: {labels[0]}",
                        phase=ExecutionPhase.RULES,
                        selector=selector,
                        value=value,
                    )
                return True
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"Failed to select option: {labels[0]}",
                        phase=ExecutionPhase.RULES,
                        error=str(e),
                    )

        return False

    def upload_file(self, labels: list[str], file_path: str) -> bool:
        """Upload file to file input."""
        selector = self.find_field_by_label(labels, "input[type='file']")

        if selector:
            try:
                self.page.set_input_files(selector, file_path, timeout=3000)
                if self.logger:
                    self.logger.info(
                        f"Uploaded file: {labels[0]}",
                        phase=ExecutionPhase.RULES,
                        selector=selector,
                        file_path=file_path,
                    )
                return True
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"Failed to upload file: {labels[0]}",
                        phase=ExecutionPhase.RULES,
                        error=str(e),
                    )

        return False


class FormFiller:
    """Fill job application forms using resume data."""

    # Field mappings: resume_field -> common labels
    FIELD_MAPPINGS = {
        "first_name": ["First Name", "Given Name", "First", "Name"],
        "last_name": ["Last Name", "Surname", "Family Name", "Last"],
        "email": ["Email", "Email Address", "E-mail"],
        "phone": ["Phone", "Phone Number", "Mobile", "Telephone", "Contact Number"],
        "address": ["Address", "Street Address", "Address Line 1"],
        "city": ["City", "Town"],
        "state": ["State", "Province", "Region"],
        "country": ["Country"],
        "zip_code": ["Zip Code", "Postal Code", "ZIP", "Postcode"],
        "linkedin": ["LinkedIn", "LinkedIn URL", "LinkedIn Profile"],
        "github": ["GitHub", "GitHub URL", "GitHub Profile"],
        "portfolio": ["Portfolio", "Portfolio URL", "Website"],
        "website": ["Website", "Personal Website", "Homepage"],
    }

    def __init__(
        self, page: Page, resume: ResumeData, logger: Optional[JobLogger] = None
    ) -> None:
        """Initialize form filler."""
        self.page = page
        self.resume = resume
        self.logger = logger
        self.field_locator = FormFieldLocator(page, logger)

    def fill_personal_info(self) -> dict[str, bool]:
        """Fill personal information fields."""
        results: dict[str, bool] = {}
        personal = self.resume.personal

        # Map personal info fields
        field_data = {
            "first_name": personal.first_name,
            "last_name": personal.last_name,
            "email": personal.email,
            "phone": personal.phone,
            "address": personal.address,
            "city": personal.city,
            "state": personal.state,
            "country": personal.country,
            "zip_code": personal.zip_code,
            "linkedin": personal.linkedin,
            "github": personal.github,
            "portfolio": personal.portfolio,
            "website": personal.website,
        }

        for field, value in field_data.items():
            if value:
                labels = self.FIELD_MAPPINGS.get(field, [field.replace("_", " ").title()])
                success = self.field_locator.fill_text_field(labels, value)
                results[field] = success

        return results

    def upload_resume(self, resume_path: str) -> bool:
        """Upload resume file."""
        labels = ["Resume", "CV", "Upload Resume", "Upload CV", "Attach Resume"]
        return self.field_locator.upload_file(labels, resume_path)

    def upload_cover_letter(self, cover_letter_path: str) -> bool:
        """Upload cover letter."""
        labels = ["Cover Letter", "Upload Cover Letter", "Attach Cover Letter"]
        return self.field_locator.upload_file(labels, cover_letter_path)

    def fill_work_authorization(self) -> dict[str, bool]:
        """Fill work authorization fields."""
        results: dict[str, bool] = {}
        auth = self.resume.work_authorization

        # Authorized to work
        if auth.authorized_to_work:
            labels = [
                "Are you authorized to work",
                "Work Authorization",
                "Authorized to work",
            ]
            results["authorized"] = self.field_locator.fill_select_field(labels, "Yes")

        # Require sponsorship
        if not auth.require_sponsorship:
            labels = [
                "Do you require sponsorship",
                "Require Sponsorship",
                "Visa Sponsorship",
            ]
            results["sponsorship"] = self.field_locator.fill_select_field(labels, "No")

        return results

    def fill_demographics(self) -> dict[str, bool]:
        """Fill demographic fields (optional)."""
        results: dict[str, bool] = {}

        if not self.resume.demographics:
            return results

        demo = self.resume.demographics

        if demo.gender:
            labels = ["Gender"]
            results["gender"] = self.field_locator.fill_select_field(labels, demo.gender)

        if demo.race:
            labels = ["Race", "Ethnicity"]
            results["race"] = self.field_locator.fill_select_field(labels, demo.race)

        if demo.veteran_status:
            labels = ["Veteran Status"]
            results["veteran"] = self.field_locator.fill_select_field(
                labels, demo.veteran_status
            )

        if demo.disability_status:
            labels = ["Disability Status"]
            results["disability"] = self.field_locator.fill_select_field(
                labels, demo.disability_status
            )

        return results

    def fill_all(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        """Fill all detected fields."""
        results: dict[str, Any] = {}

        if self.logger:
            self.logger.info("Starting form fill", phase=ExecutionPhase.RULES)

        # Fill personal info
        results["personal_info"] = self.fill_personal_info()

        # Upload resume
        if resume_path:
            results["resume_uploaded"] = self.upload_resume(resume_path)

        # Fill work authorization
        results["work_authorization"] = self.fill_work_authorization()

        # Fill demographics
        results["demographics"] = self.fill_demographics()

        if self.logger:
            self.logger.info(
                "Form fill completed",
                phase=ExecutionPhase.RULES,
                results=results,
            )

        return results
