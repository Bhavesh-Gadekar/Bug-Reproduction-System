"""Initial schema creation for Bug Reproduction Agent

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-04 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Native Postgres ENUM definitions
# (create_type=False because they are explicitly created in upgrade())
bug_report_status_enum = postgresql.ENUM(
    "queued",
    "running",
    "completed",
    "failed",
    name="bug_report_status",
    create_type=False,
)
reproduction_run_status_enum = postgresql.ENUM(
    "queued",
    "cloning",
    "analyzing",
    "generating",
    "executing",
    "validating",
    "succeeded",
    "failed",
    "timed_out",
    name="reproduction_run_status",
    create_type=False,
)
artifact_type_enum = postgresql.ENUM(
    "repro_script",
    "failing_test",
    "patch_diff",
    "log",
    name="artifact_type",
    create_type=False,
)
evaluation_verdict_enum = postgresql.ENUM(
    "true_positive",
    "false_positive",
    "false_negative",
    name="evaluation_verdict",
    create_type=False,
)


def upgrade() -> None:
    # 1. Create Enum Types (if running on PostgreSQL)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bug_report_status_enum.create(bind, checkfirst=True)
        reproduction_run_status_enum.create(bind, checkfirst=True)
        artifact_type_enum.create(bind, checkfirst=True)
        evaluation_verdict_enum.create(bind, checkfirst=True)

    # 2. Create workspaces table
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("clerk_org_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_workspaces_clerk_org_id",
        "workspaces",
        ["clerk_org_id"],
        unique=True,
    )

    # 3. Create users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clerk_user_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="member"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_users_workspace_id", "users", ["workspace_id"])
    op.create_index("ix_users_clerk_user_id", "users", ["clerk_user_id"])
    op.create_index("ix_users_email", "users", ["email"])

    # 4. Create repos table
    op.create_table(
        "repos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("git_url", sa.String(length=512), nullable=False),
        sa.Column(
            "default_branch",
            sa.String(length=100),
            nullable=False,
            server_default="main",
        ),
        sa.Column("access_token_ref", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_repos_workspace_id", "repos", ["workspace_id"])

    # 5. Create bug_reports table
    op.create_table(
        "bug_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("raw_stack_trace", sa.Text(), nullable=True),
        sa.Column("reported_env", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", bug_report_status_enum, nullable=False, server_default="queued"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_bug_reports_workspace_id", "bug_reports", ["workspace_id"])
    op.create_index("ix_bug_reports_repo_id", "bug_reports", ["repo_id"])
    op.create_index("ix_bug_reports_status", "bug_reports", ["status"])

    # 6. Create reproduction_runs table
    op.create_table(
        "reproduction_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bug_report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", reproduction_run_status_enum, nullable=False, server_default="queued"),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=100), nullable=True),
        sa.Column("candidate_produced", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("plausible_reproduced", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sandbox_container_id", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["bug_report_id"], ["bug_reports.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_reproduction_runs_bug_report_id", "reproduction_runs", ["bug_report_id"])
    op.create_index("ix_reproduction_runs_status", "reproduction_runs", ["status"])

    # 7. Create run_steps table
    op.create_table(
        "run_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_name", sa.String(length=255), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["reproduction_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_run_steps_run_id", "run_steps", ["run_id"])

    # 8. Create artifacts table
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", artifact_type_enum, nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False, comment="Backblaze B2 object key"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["reproduction_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])
    op.create_index("ix_artifacts_type", "artifacts", ["type"])

    # 9. Create evaluation_results table
    op.create_table(
        "evaluation_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verdict", evaluation_verdict_enum, nullable=False),
        sa.Column("reviewer", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["reproduction_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_evaluation_results_run_id", "evaluation_results", ["run_id"])
    op.create_index("ix_evaluation_results_verdict", "evaluation_results", ["verdict"])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("evaluation_results")
    op.drop_table("artifacts")
    op.drop_table("run_steps")
    op.drop_table("reproduction_runs")
    op.drop_table("bug_reports")
    op.drop_table("repos")
    op.drop_table("users")
    op.drop_table("workspaces")

    # Drop enum types (if running on PostgreSQL)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        evaluation_verdict_enum.drop(bind, checkfirst=True)
        artifact_type_enum.drop(bind, checkfirst=True)
        reproduction_run_status_enum.drop(bind, checkfirst=True)
        bug_report_status_enum.drop(bind, checkfirst=True)
