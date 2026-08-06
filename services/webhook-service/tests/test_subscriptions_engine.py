"""Pure tests for app/subscriptions/engine.py -- no database, no fixtures."""

from __future__ import annotations

from app.models.enums import SubscriptionScope
from app.subscriptions.engine import (
    EventContext,
    SubscriptionCandidate,
    matches,
    matching_subscriptions,
)


def _candidate(
    *,
    id: str = "sub-1",
    scope: SubscriptionScope = SubscriptionScope.WILDCARD,
    scope_reference: str | None = None,
    event_types: tuple[str, ...] = (),
    enabled: bool = True,
) -> SubscriptionCandidate:
    return SubscriptionCandidate(
        id=id,
        scope=scope,
        scope_reference=scope_reference,
        event_types=event_types,
        enabled=enabled,
    )


def _event(
    *,
    event_type: str = "order.created",
    organization_id: str = "org-1",
    project_id: str | None = None,
    role: str | None = None,
    user_id: str | None = None,
    topic: str | None = None,
    resource_id: str | None = None,
) -> EventContext:
    return EventContext(
        event_type=event_type,
        organization_id=organization_id,
        project_id=project_id,
        role=role,
        user_id=user_id,
        topic=topic,
        resource_id=resource_id,
    )


class TestSubscriptionCandidateDefaults:
    def test_event_types_defaults_to_an_empty_tuple(self) -> None:
        candidate = SubscriptionCandidate(
            id="s1", scope=SubscriptionScope.WILDCARD, scope_reference=None
        )
        assert candidate.event_types == ()

    def test_enabled_defaults_to_true(self) -> None:
        candidate = SubscriptionCandidate(
            id="s1", scope=SubscriptionScope.WILDCARD, scope_reference=None
        )
        assert candidate.enabled is True


class TestEventContextDefaults:
    def test_optional_fields_default_to_none(self) -> None:
        event = EventContext(event_type="order.created", organization_id="org-1")
        assert event.project_id is None
        assert event.role is None
        assert event.user_id is None
        assert event.topic is None
        assert event.resource_id is None


class TestScopeMatchingWildcard:
    def test_matches_regardless_of_scope_reference(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.WILDCARD, scope_reference=None)
        assert matches(candidate, _event()) is True

    def test_matches_even_with_an_unrelated_scope_reference_set(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.WILDCARD, scope_reference="ignored")
        assert matches(candidate, _event()) is True


class TestScopeMatchingConditional:
    def test_own_scope_check_always_passes(self) -> None:
        # `condition_expression` evaluation happens elsewhere (app/filters/engine.py);
        # this module's own scope check for CONDITIONAL is a pure pass-through.
        candidate = _candidate(scope=SubscriptionScope.CONDITIONAL, scope_reference=None)
        assert matches(candidate, _event()) is True


class TestScopeMatchingMissingReference:
    def test_a_none_scope_reference_never_matches_a_referenced_scope(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.ORGANIZATION, scope_reference=None)
        assert matches(candidate, _event(organization_id="org-1")) is False


class TestScopeMatchingOrganization:
    def test_matches_the_same_organization(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.ORGANIZATION, scope_reference="org-1")
        assert matches(candidate, _event(organization_id="org-1")) is True

    def test_does_not_match_a_different_organization(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.ORGANIZATION, scope_reference="org-1")
        assert matches(candidate, _event(organization_id="org-2")) is False


class TestScopeMatchingProject:
    def test_matches_the_same_project(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.PROJECT, scope_reference="proj-1")
        assert matches(candidate, _event(project_id="proj-1")) is True

    def test_does_not_match_a_different_project(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.PROJECT, scope_reference="proj-1")
        assert matches(candidate, _event(project_id="proj-2")) is False

    def test_does_not_match_when_event_has_no_project(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.PROJECT, scope_reference="proj-1")
        assert matches(candidate, _event(project_id=None)) is False


class TestScopeMatchingRole:
    def test_matches_the_same_role(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.ROLE, scope_reference="admin")
        assert matches(candidate, _event(role="admin")) is True

    def test_does_not_match_a_different_role(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.ROLE, scope_reference="admin")
        assert matches(candidate, _event(role="viewer")) is False


class TestScopeMatchingUser:
    def test_matches_the_same_user(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.USER, scope_reference="user-1")
        assert matches(candidate, _event(user_id="user-1")) is True

    def test_does_not_match_a_different_user(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.USER, scope_reference="user-1")
        assert matches(candidate, _event(user_id="user-2")) is False


class TestScopeMatchingTopic:
    def test_glob_pattern_matches_a_topic(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.TOPIC, scope_reference="billing.*")
        assert matches(candidate, _event(topic="billing.invoices")) is True

    def test_glob_pattern_excludes_an_unrelated_topic(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.TOPIC, scope_reference="billing.*")
        assert matches(candidate, _event(topic="shipping.updates")) is False

    def test_a_none_topic_falls_back_to_an_empty_string_for_matching(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.TOPIC, scope_reference="*")
        # fnmatch("", "*") is True -- a bare wildcard reference still matches a topic-less event.
        assert matches(candidate, _event(topic=None)) is True

    def test_a_none_topic_does_not_match_a_specific_reference(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.TOPIC, scope_reference="billing.*")
        assert matches(candidate, _event(topic=None)) is False


class TestScopeMatchingEvent:
    def test_glob_pattern_matches_the_event_type(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.EVENT, scope_reference="order.*")
        assert matches(candidate, _event(event_type="order.created")) is True

    def test_glob_pattern_excludes_an_unrelated_event_type(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.EVENT, scope_reference="order.*")
        assert matches(candidate, _event(event_type="user.created")) is False


class TestScopeMatchingResource:
    def test_matches_the_same_resource(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.RESOURCE, scope_reference="res-1")
        assert matches(candidate, _event(resource_id="res-1")) is True

    def test_does_not_match_a_different_resource(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.RESOURCE, scope_reference="res-1")
        assert matches(candidate, _event(resource_id="res-2")) is False


class TestScopeMatchingUnrecognisedScope:
    def test_an_unrecognised_scope_value_never_matches(self) -> None:
        # Defensive-only branch: every real SubscriptionScope member is handled explicitly
        # above, so this exercises the final fallback for a value outside the enum -- plain
        # dataclasses don't enforce their type hints at runtime, so this is constructible.
        candidate = SubscriptionCandidate(
            id="s1", scope="not-a-real-scope", scope_reference="anything", enabled=True  # type: ignore[arg-type]
        )
        assert matches(candidate, _event()) is False


class TestEventTypeMatching:
    def test_empty_event_types_matches_everything(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.WILDCARD, event_types=())
        assert matches(candidate, _event(event_type="anything.at.all")) is True

    def test_a_matching_glob_pattern_among_many(self) -> None:
        candidate = _candidate(
            scope=SubscriptionScope.WILDCARD, event_types=("user.*", "order.created", "billing.*")
        )
        assert matches(candidate, _event(event_type="order.created")) is True

    def test_no_matching_pattern_among_many(self) -> None:
        candidate = _candidate(
            scope=SubscriptionScope.WILDCARD, event_types=("user.*", "billing.*")
        )
        assert matches(candidate, _event(event_type="order.created")) is False


class TestMatchesDisabled:
    def test_a_disabled_candidate_never_matches_even_when_scope_and_type_would(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.WILDCARD, event_types=(), enabled=False)
        assert matches(candidate, _event()) is False


class TestMatchingSubscriptions:
    def test_returns_only_the_matching_candidates_in_original_order(self) -> None:
        first = _candidate(id="a", scope=SubscriptionScope.EVENT, scope_reference="order.*")
        second = _candidate(id="b", scope=SubscriptionScope.EVENT, scope_reference="user.*")
        third = _candidate(id="c", scope=SubscriptionScope.WILDCARD)
        result = matching_subscriptions([first, second, third], _event(event_type="order.created"))
        assert [c.id for c in result] == ["a", "c"]

    def test_empty_candidate_list_returns_empty(self) -> None:
        assert matching_subscriptions([], _event()) == []

    def test_no_matches_returns_empty(self) -> None:
        candidate = _candidate(scope=SubscriptionScope.EVENT, scope_reference="user.*")
        assert matching_subscriptions([candidate], _event(event_type="order.created")) == []
