#!/usr/bin/env python3
"""Validate resume JSON file against schema."""

import json
import sys
from pathlib import Path

from pydantic import ValidationError

from jobcli.core.schemas import ResumeData


def validate_resume(json_path: str) -> None:
    """Validate resume JSON file."""
    path = Path(json_path)

    if not path.exists():
        print(f"❌ File not found: {json_path}")
        sys.exit(1)

    try:
        with open(path) as f:
            data = json.load(f)

        # Validate with Pydantic
        resume = ResumeData(**data)

        print("✅ Resume JSON is valid!")
        print(f"\n📋 Summary:")
        print(f"   Name: {resume.personal.first_name} {resume.personal.last_name}")
        print(f"   Email: {resume.personal.email}")
        print(f"   Phone: {resume.personal.phone}")
        print(f"   Experience entries: {len(resume.experience)}")
        print(f"   Education entries: {len(resume.education)}")
        print(f"   Skills: {len(resume.skills)}")
        print(f"   Certifications: {len(resume.certifications)}")

        if resume.personal.linkedin:
            print(f"   LinkedIn: {resume.personal.linkedin}")
        if resume.personal.github:
            print(f"   GitHub: {resume.personal.github}")

        print(f"\n💼 Work Authorization:")
        print(
            f"   Authorized to work: {'Yes' if resume.work_authorization.authorized_to_work else 'No'}"
        )
        print(
            f"   Requires sponsorship: {'Yes' if resume.work_authorization.require_sponsorship else 'No'}"
        )

        if resume.demographics:
            print(f"\n👤 Demographics: Provided")

        sys.exit(0)

    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        sys.exit(1)

    except ValidationError as e:
        print(f"❌ Validation failed:\n")
        for error in e.errors():
            field = " -> ".join(str(x) for x in error["loc"])
            message = error["msg"]
            print(f"   {field}: {message}")
        sys.exit(1)

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_resume.py <resume.json>")
        print("\nExample:")
        print("  python validate_resume.py example_resume.json")
        sys.exit(1)

    validate_resume(sys.argv[1])
