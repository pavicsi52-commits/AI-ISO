"""Background worker: Git repository synchronization.

Per docs/039 "PERFORMANCE": "Git Synchronization Workers". Registered
on this service's own :class:`~shared_core.queue.consumer.Consumer` at
startup (see ``app/core/factory.py``'s ``_lifespan``), the same
in-process queue-consumer pattern
``services/asset-management-service``'s own ``sweep_worker``
established.

The queue message carries an optional ``caller_token`` -- present for
every interactively-triggered sync, absent for a schedule-fired one.
No prior AI-IOS prompt establishes a service-account/machine-credential
mechanism, the same documented, honest platform gap
``services/discovery-service``'s own ``discovery_worker``/
``discovery_execution.py`` already flagged: with no caller identity,
this worker skips (and logs) any repository whose
:attr:`~app.models.configuration_git_repository.ConfigurationGitRepository
.credential_ref` is set, since the token needed to resolve that secret
from ``services/secrets-management-service`` simply does not exist for
an unattended run; a repository with no credential (a public
repository) still syncs regardless.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.queue.consumer import MessageHandler
from shared_core.queue.decorators import job
from shared_core.types.queue import QueueMessage

from app.services.gitops import ConfigurationGitOpsService
from app.services.profile import ConfigurationProfileService

logger = get_logger("app.workers.git_sync_worker")

GIT_SYNC_QUEUE_NAME = "configuration_management_git_sync_queue"

GitSyncServices = tuple[ConfigurationGitOpsService, ConfigurationProfileService]
GitSyncServiceFactory = Callable[[], AbstractAsyncContextManager[GitSyncServices]]


def build_git_sync_worker(service_factory: GitSyncServiceFactory) -> MessageHandler:
    """Build the ``@job``-decorated handler for :data:`GIT_SYNC_QUEUE_NAME`."""

    async def handle_git_sync_job(message: QueueMessage) -> None:
        repository_id = UUID(str(message["repository_id"]))
        profile_id = UUID(str(message["profile_id"]))
        caller_token = message.get("caller_token")
        commit_message = str(message.get("commit_message") or "Scheduled configuration sync.")
        try:
            async with service_factory() as (gitops, profiles):
                repository = await gitops.get_by_id(repository_id)
                if repository.credential_ref is not None and caller_token is None:
                    logger.warning(
                        "Skipping Git sync: no caller identity available to resolve "
                        "this repository's credential.",
                        extra={"extra_fields": {"repository_id": str(repository_id)}},
                    )
                    return
                profile = await profiles.get_by_id(profile_id)
                await gitops.sync_profile(
                    repository_id,
                    profile=profile,
                    caller_token=str(caller_token) if caller_token else "",
                    commit_message=commit_message,
                )
        except Exception:
            logger.exception(
                "Configuration Git sync failed.",
                extra={"extra_fields": {"repository_id": str(repository_id)}},
            )
            raise

    return job(GIT_SYNC_QUEUE_NAME)(handle_git_sync_job)


__all__ = [
    "GIT_SYNC_QUEUE_NAME",
    "GitSyncServiceFactory",
    "GitSyncServices",
    "build_git_sync_worker",
]
