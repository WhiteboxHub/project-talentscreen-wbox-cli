"""Tests for wboxcli reset (clear login/keys/resume without wiping jobs)."""

from jobcli.profile.schemas import Config, PersonalInfo, ResumeData
from jobcli.storage.models import ConfigModel, Database, UserDataModel
from jobcli.storage.repositories import ConfigRepository, UserDataRepository


def test_reset_clears_config_and_profile(tmp_path):
    db_path = tmp_path / "test.db"
    db = Database(f"sqlite:///{db_path.as_posix()}")
    db.create_tables()
    session = db.get_session()

    config_repo = ConfigRepository(session)
    config_repo.set("openai_api_key", "sk-test")
    config_repo.set("resume_pdf_path", "/tmp/resume.pdf")
    config_repo.set("job_board_username", "user@test.com")

    user_repo = UserDataRepository(session)
    user_repo.save_resume(
        ResumeData(
            personal=PersonalInfo(first_name="A", last_name="B", email="a@b.com"),
        )
    )

    keys = [
        "openai_api_key",
        "resume_pdf_path",
        "job_board_username",
    ]
    assert config_repo.delete_keys(keys) == 3
    assert user_repo.clear_profile_data() == 1

    assert config_repo.get("openai_api_key") is None
    assert session.query(UserDataModel).count() == 0
    session.close()
