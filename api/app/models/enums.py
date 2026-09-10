import enum


class BugReportStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReproductionRunStatus(enum.StrEnum):
    QUEUED = "queued"
    CLONING = "cloning"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    EXECUTING = "executing"
    VALIDATING = "validating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    ERROR = "error"
    INFRA_ERROR = "infra_error"


class ArtifactType(enum.StrEnum):
    REPRO_SCRIPT = "repro_script"
    FAILING_TEST = "failing_test"
    PATCH_DIFF = "patch_diff"
    LOG = "log"


class EvaluationVerdict(enum.StrEnum):
    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"
