"""Human-in-the-loop interface for manual intervention."""

from typing import Optional

from playwright.sync_api import Page
from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from jobcli.utils.logger import JobLogger
from jobcli.ats.schemas.locator_schemas import LearnedLocator
from jobcli.profile.schemas import ATSType, ExecutionPhase, SelectorType
from jobcli.storage.repositories import LearnedLocatorRepository


class HumanInterface:
    """Interactive interface for human assistance."""

    def __init__(
        self,
        page: Page,
        locator_repo: LearnedLocatorRepository,
        logger: Optional[JobLogger] = None,
    ) -> None:
        """Initialize human interface."""
        self.page = page
        self.locator_repo = locator_repo
        self.logger = logger
        self.console = Console()

    def request_help(
        self,
        task: str,
        ats_type: ATSType = ATSType.UNKNOWN,
    ) -> tuple[bool, Optional[str], Optional[SelectorType]]:
        """Request human help for a task."""
        if self.logger:
            self.logger.info(
                "Requesting human assistance",
                phase=ExecutionPhase.HUMAN,
                task=task,
            )

        self.console.print("\n[bold red]⚠ Human Assistance Required[/bold red]")
        self.console.print(f"Task: [cyan]{task}[/cyan]")
        self.console.print(f"URL: [blue]{self.page.url}[/blue]\n")

        # Show detected elements
        self._show_detected_elements()

        # Get user choice
        choice = self._get_user_choice()

        if choice == "skip":
            return False, None, None
        elif choice == "manual":
            return self._get_manual_selector(task, ats_type)
        elif choice == "select":
            return self._select_from_elements(task, ats_type)
        else:
            return False, None, None

    def _show_detected_elements(self) -> None:
        """Show detected interactive elements to user."""
        try:
            # Get interactive elements
            buttons = self._get_buttons()
            links = self._get_links()

            if buttons:
                table = Table(title="Detected Buttons")
                table.add_column("Index", style="cyan")
                table.add_column("Text", style="green")
                table.add_column("Type", style="yellow")
                table.add_column("Visible", style="magenta")

                for i, btn in enumerate(buttons[:10], 1):
                    table.add_row(
                        str(i),
                        btn.get("text", "")[:50],
                        btn.get("type", ""),
                        "✓" if btn.get("visible") else "✗",
                    )

                self.console.print(table)

            if links:
                table = Table(title="Detected Links")
                table.add_column("Index", style="cyan")
                table.add_column("Text", style="green")
                table.add_column("Visible", style="magenta")

                for i, link in enumerate(links[:10], 1):
                    table.add_row(
                        str(i),
                        link.get("text", "")[:50],
                        "✓" if link.get("visible") else "✗",
                    )

                self.console.print(table)

        except Exception as e:
            self.console.print(f"[red]Error detecting elements: {e}[/red]")

    def _get_buttons(self) -> list[dict]:
        """Extract button elements."""
        script = """
        () => {
            const buttons = document.querySelectorAll('button, input[type="submit"], [role="button"]');
            return Array.from(buttons).map(btn => ({
                text: btn.textContent?.trim() || btn.value || '',
                type: btn.type || btn.tagName.toLowerCase(),
                visible: btn.offsetParent !== null,
                selector: btn.id ? `#${btn.id}` : (btn.className ? `.${btn.className.split(' ')[0]}` : ''),
            }));
        }
        """
        try:
            return self.page.evaluate(script)
        except Exception:
            return []

    def _get_links(self) -> list[dict]:
        """Extract link elements."""
        script = """
        () => {
            const links = document.querySelectorAll('a');
            return Array.from(links).map(link => ({
                text: link.textContent?.trim() || '',
                visible: link.offsetParent !== null,
                selector: link.id ? `#${link.id}` : (link.className ? `.${link.className.split(' ')[0]}` : ''),
            }));
        }
        """
        try:
            return self.page.evaluate(script)
        except Exception:
            return []

    def _get_user_choice(self) -> str:
        """Get user's choice of action."""
        self.console.print("\n[bold]What would you like to do?[/bold]")
        self.console.print("1. Select from detected elements")
        self.console.print("2. Provide manual selector")
        self.console.print("3. Skip this job")

        choice = IntPrompt.ask("Choice", choices=["1", "2", "3"], default=1)

        if choice == 1:
            return "select"
        elif choice == 2:
            return "manual"
        else:
            return "skip"

    def _select_from_elements(
        self, task: str, ats_type: ATSType
    ) -> tuple[bool, Optional[str], Optional[SelectorType]]:
        """Let user select from detected elements."""
        element_type = Prompt.ask(
            "Element type", choices=["button", "link"], default="button"
        )

        if element_type == "button":
            elements = self._get_buttons()
        else:
            elements = self._get_links()

        if not elements:
            self.console.print("[red]No elements detected[/red]")
            return False, None, None

        index = IntPrompt.ask(
            "Select element index",
            default=1,
            show_default=True,
        )

        if 1 <= index <= len(elements):
            element = elements[index - 1]
            selector = element.get("selector", "")

            if not selector:
                self.console.print("[red]No selector available for this element[/red]")
                return self._get_manual_selector(task, ats_type)

            # Ask if user wants to save this
            save = Confirm.ask("Save this locator for future use?", default=True)

            if save:
                self._save_learned_locator(
                    task, ats_type, selector, SelectorType.CSS, "Human selected element"
                )

            return True, selector, SelectorType.CSS

        self.console.print("[red]Invalid index[/red]")
        return False, None, None

    def _get_manual_selector(
        self, task: str, ats_type: ATSType
    ) -> tuple[bool, Optional[str], Optional[SelectorType]]:
        """Get manual selector from user."""
        self.console.print("\n[bold]Enter selector information:[/bold]")

        selector_type_str = Prompt.ask(
            "Selector type",
            choices=["css", "xpath", "text"],
            default="css",
        )

        selector = Prompt.ask("Selector")

        if not selector:
            return False, None, None

        selector_type = SelectorType(selector_type_str)

        # Test selector
        try:
            if selector_type == SelectorType.CSS:
                element = self.page.query_selector(selector)
            elif selector_type == SelectorType.XPATH:
                element = self.page.query_selector(f"xpath={selector}")
            else:
                element = self.page.get_by_text(selector).first

            if element:
                self.console.print("[green]✓ Selector found element[/green]")

                # Ask if user wants to save
                save = Confirm.ask("Save this locator for future use?", default=True)

                if save:
                    notes = Prompt.ask("Notes (optional)", default="")
                    self._save_learned_locator(task, ats_type, selector, selector_type, notes)

                return True, selector, selector_type
            else:
                self.console.print("[red]✗ Selector did not match any element[/red]")
                retry = Confirm.ask("Try again?", default=True)
                if retry:
                    return self._get_manual_selector(task, ats_type)
                return False, None, None

        except Exception as e:
            self.console.print(f"[red]Error testing selector: {e}[/red]")
            return False, None, None

    def _save_learned_locator(
        self,
        purpose: str,
        ats_type: ATSType,
        selector: str,
        selector_type: SelectorType,
        notes: str,
    ) -> None:
        """Save learned locator to database."""
        try:
            locator = LearnedLocator(
                ats_type=ats_type,
                selector=selector,
                selector_type=selector_type,
                purpose=purpose,
                notes=notes,
                created_by="human",
            )

            self.locator_repo.create(locator)

            self.console.print("[green]✓ Locator saved successfully[/green]")

            if self.logger:
                self.logger.info(
                    "Learned locator saved",
                    phase=ExecutionPhase.HUMAN,
                    purpose=purpose,
                    selector=selector,
                )

        except Exception as e:
            self.console.print(f"[red]Failed to save locator: {e}[/red]")

    def ask_continue(self) -> bool:
        """Ask if user wants to continue with application."""
        return Confirm.ask("\nContinue with this application?", default=True)

    def show_error(self, message: str) -> None:
        """Show error message to user."""
        self.console.print(f"\n[bold red]Error:[/bold red] {message}")

    def show_success(self, message: str) -> None:
        """Show success message to user."""
        self.console.print(f"\n[bold green]Success:[/bold green] {message}")

    def confirm_submission(self) -> bool:
        """Confirm before submitting application."""
        self.console.print("\n[bold yellow]Ready to submit application[/bold yellow]")
        return Confirm.ask("Submit now?", default=True)
