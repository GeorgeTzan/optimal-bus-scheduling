class StaleVersionConflictError(Exception):
    """Raised when an assignment patch specifies an outdated revision version (HTTP 409)."""
    pass


class ImmutableRevisionError(Exception):
    """Raised when attempting to modify a revision that has already been published."""
    pass


class LockedAssignmentError(Exception):
    """Raised when attempting to overwrite a locked assignment without explicit unlock flag."""
    pass


class PublicationVerificationFailedError(Exception):
    """Raised when an independent verification check detects rule violations on publication."""
    pass
