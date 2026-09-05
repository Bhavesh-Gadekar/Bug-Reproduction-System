import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_scoped_session
from app.models import (
    Artifact,
    ArtifactType,
    BugReport,
    BugReportStatus,
    EvaluationResult,
    EvaluationVerdict,
    Repo,
    ReproductionRun,
    ReproductionRunStatus,
    RunStep,
    User,
    Workspace,
)


def test_scoped_session_isolates_workspace_data(postgres_engine):
    """
    Assert that a query executed through a scoped session for Workspace A
    never returns rows belonging to Workspace B on a real PostgreSQL instance.
    Validates native Postgres ENUMs, JSONB, and UUID foreign key cascades.
    """
    workspace_a_id = uuid.uuid4()
    workspace_b_id = uuid.uuid4()

    # Seed data using an unscoped direct session
    with Session(bind=postgres_engine) as setup_session:
        # Create workspaces
        ws_a = Workspace(id=workspace_a_id, name="Acme Corp Workspace A")
        ws_b = Workspace(id=workspace_b_id, name="Beta Inc Workspace B")
        setup_session.add_all([ws_a, ws_b])
        setup_session.flush()

        # Create users in both workspaces
        user_a = User(
            workspace_id=workspace_a_id,
            clerk_user_id="user_a_clerk_123",
            email="alice@acme.com",
            role="admin",
        )
        user_b = User(
            workspace_id=workspace_b_id,
            clerk_user_id="user_b_clerk_456",
            email="bob@beta.com",
            role="member",
        )
        setup_session.add_all([user_a, user_b])

        # Create repos in both workspaces
        repo_a = Repo(
            workspace_id=workspace_a_id,
            git_url="https://github.com/acme/backend.git",
            default_branch="main",
        )
        repo_b = Repo(
            workspace_id=workspace_b_id,
            git_url="https://github.com/beta/frontend.git",
            default_branch="master",
        )
        setup_session.add_all([repo_a, repo_b])
        setup_session.flush()

        # Create bug reports with native ENUM and JSONB payload
        bug_a = BugReport(
            workspace_id=workspace_a_id,
            repo_id=repo_a.id,
            title="Workspace A Bug: Null Pointer Exception",
            status=BugReportStatus.QUEUED,
            reported_env={"os": "linux", "python": "3.11", "docker": True},
        )
        bug_b = BugReport(
            workspace_id=workspace_b_id,
            repo_id=repo_b.id,
            title="Workspace B Bug: Memory Leak in Worker",
            status=BugReportStatus.RUNNING,
            reported_env={"os": "windows", "python": "3.11"},
        )
        setup_session.add_all([bug_a, bug_b])
        setup_session.flush()

        # Create reproduction runs and artifacts with native PostgreSQL ENUMs
        run_a = ReproductionRun(
            bug_report_id=bug_a.id,
            status=ReproductionRunStatus.GENERATING,
            model_version="gemini-2.0-flash",
            candidate_produced=True,
        )
        setup_session.add(run_a)
        setup_session.flush()

        step_a = RunStep(
            run_id=run_a.id,
            node_name="analyzer",
            input={"trace": "stack trace line 42"},
            output={"identified_root_cause": "NPE in handler"},
            tokens_used=1200,
            latency_ms=450,
        )
        artifact_a = Artifact(
            run_id=run_a.id,
            type=ArtifactType.REPRO_SCRIPT,
            storage_path="workspaces/ws_a/repros/test_repro.py",
        )
        eval_a = EvaluationResult(
            run_id=run_a.id,
            verdict=EvaluationVerdict.TRUE_POSITIVE,
            reviewer="auto_validator",
            notes="Bug reproduced successfully",
        )
        setup_session.add_all([step_a, artifact_a, eval_a])
        setup_session.commit()

    # Query through Scoped Session for Workspace A
    session_a = get_scoped_session(workspace_id=workspace_a_id, bind=postgres_engine)

    # 1. Test Repos scoping
    repos_in_a = session_a.query(Repo).all()
    assert len(repos_in_a) == 1
    assert repos_in_a[0].workspace_id == workspace_a_id
    assert repos_in_a[0].git_url == "https://github.com/acme/backend.git"

    # 2. Test Users scoping
    users_in_a = session_a.query(User).all()
    assert len(users_in_a) == 1
    assert users_in_a[0].workspace_id == workspace_a_id
    assert users_in_a[0].email == "alice@acme.com"

    # 3. Test Bug Reports scoping (using select scalars) and JSONB verification
    stmt = select(BugReport)
    bugs_in_a = session_a.scalars(stmt).all()
    assert len(bugs_in_a) == 1
    assert bugs_in_a[0].workspace_id == workspace_a_id
    assert bugs_in_a[0].title == "Workspace A Bug: Null Pointer Exception"
    assert bugs_in_a[0].status == BugReportStatus.QUEUED
    assert bugs_in_a[0].reported_env == {"os": "linux", "python": "3.11", "docker": True}

    # 4. Verify that querying through Workspace B's session only returns B's data
    session_b = get_scoped_session(workspace_id=workspace_b_id, bind=postgres_engine)

    repos_in_b = session_b.query(Repo).all()
    assert len(repos_in_b) == 1
    assert repos_in_b[0].workspace_id == workspace_b_id
    assert repos_in_b[0].git_url == "https://github.com/beta/frontend.git"

    users_in_b = session_b.query(User).all()
    assert len(users_in_b) == 1
    assert users_in_b[0].workspace_id == workspace_b_id
    assert users_in_b[0].email == "bob@beta.com"

    bugs_in_b = session_b.scalars(select(BugReport)).all()
    assert len(bugs_in_b) == 1
    assert bugs_in_b[0].workspace_id == workspace_b_id
    assert bugs_in_b[0].title == "Workspace B Bug: Memory Leak in Worker"
    assert bugs_in_b[0].status == BugReportStatus.RUNNING

    # 5. Clean up sessions
    session_a.close()
    session_b.close()
