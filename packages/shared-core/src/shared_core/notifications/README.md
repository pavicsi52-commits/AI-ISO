# Enterprise Notification Framework

Multi-channel notification delivery for AI-IOS
(docs/025_Enterprise_Notification_Framework.md.txt "OBJECTIVE"): Email,
SMS, Push, In-App, Slack, Microsoft Teams, Discord, Webhooks. Every
channel implements the same interface; templates, preferences, retry,
rate limiting, analytics, and health monitoring are all channel-agnostic.

## Developer Guide

```python
from shared_core.config.settings import EmailSettings
from shared_core.enums.notification_type import NotificationType
from shared_core.notifications import create_notification_framework

manager = create_notification_framework(
    email_settings=EmailSettings(email_enabled=True, smtp_host="smtp.example.com"),
)

result = await manager.send(
    user_id="user-1", notification_type=NotificationType.INFORMATION, body="Your report is ready.",
)
```

`create_notification_framework()` is the one call a service's startup
makes: it wires the channel registry, router, and dispatcher into one
`NotificationManager`. It only auto-registers `EmailChannel` (the one
channel with dedicated `EmailSettings`) -- every other channel needs
per-provider configuration this framework has no default for, so
register those explicitly:

```python
from shared_core.notifications import SlackChannel

manager.channels.register(SlackChannel(webhook_url_resolver=lambda message: my_slack_webhook_url))
```

### Channels

```python
from shared_core.notifications import EmailChannel, SlackChannel, TeamsChannel, DiscordChannel, WebhookChannel, SmsChannel, PushChannel, InAppChannel

# every channel implements: async def send(message: NotificationMessage) -> DeliveryResult
```

`SMS`/`Push` have no vendor named in the spec (Twilio vs. Vonage; FCM
vs. APNs all speak different REST APIs), so they're generic HTTP POST
providers -- pass the real vendor's endpoint/headers. Slack/Teams/
Discord/Webhook are real, well-defined integrations (incoming webhook
JSON payloads); `InAppChannel` writes into an in-memory
`InAppNotificationStore` (unread/read/archived/pinned/categories/
search/filtering/pagination) -- purely in-process, the same "no
business tables" stance as every prior framework's own state.

### Templates

```python
from shared_core.notifications import Template, TemplateFormat, TemplateRegistry, render_template

registry = TemplateRegistry()
registry.register(Template(
    template_id="welcome", format=TemplateFormat.MARKDOWN,
    subject_template="Welcome, {{ name }}!", body_template="# Hi {{ name }}\n\nWelcome to AI-IOS.",
))
rendered = render_template(registry.get("welcome"), {"name": "Ada"})
```

Jinja2's `SandboxedEnvironment` -- a template may come from a service's
own (possibly user-editable) configuration, not just trusted source
code, so unrestricted Jinja2 would be a real injection risk. To send a
rendered HTML/Markdown body over email, set
`metadata={"body_format": "markdown"}` (or `"html"`) on the
`NotificationMessage` -- `EmailChannel` then sends a proper
`plain + html` multipart message instead of raw markup as plain text.

### Preferences and Routing

```python
from shared_core.notifications import NotificationPreferences, PreferencesStore, NotificationRouter

preferences = PreferencesStore()
preferences.set(NotificationPreferences(
    user_id="user-1", preferred_channels=[...], quiet_hours_start=..., quiet_hours_end=...,
))
router = NotificationRouter(preferences)
router.resolve_channels("user-1", notification_type=NotificationType.INFORMATION)
router.should_defer_for_quiet_hours("user-1", priority=Priority.NORMAL, now=...)
```

Critical/High priority always overrides quiet hours -- an operator
override for genuinely urgent notifications, matching
`shared_core.monitoring`'s maintenance-mode precedent.

### Retry, Rate Limiting, and Dead Letters

```python
from shared_core.notifications import NotificationDispatcher, notification_retry_policy, build_notification_rate_limiter

dispatcher = NotificationDispatcher(
    channels=manager.channels, history=manager.history, dead_letters=manager.dead_letters,
    retry_policy=notification_retry_policy(max_attempts=3),
    rate_limiter=build_notification_rate_limiter(cache_manager),
)
```

Reuses `shared_core.queue.retry.RetryPolicy`/`compute_backoff_delay`
and `shared_core.cache.ratelimit.RateLimitCache` directly rather than
reimplementing exponential backoff or rate limiting a second/third
time. A notification that exhausts retry goes to `manager.dead_letters`
for manual retry.

### Analytics and Health

```python
manager.analytics.sent_count()
manager.analytics.channel_usage()
manager.analytics.average_latency_ms(channel=NotificationChannel.EMAIL)

from shared_core.notifications import calculate_notification_health, check_smtp_health
report = calculate_notification_health(channel_statuses={...}, queue_status=...)
```

Purely in-process (this framework must not create business/persistence
tables) -- computed from `manager.history`/`manager.tracking`, the same
stance as `shared_core.monitoring.availability` and
`shared_core.telemetry.analytics`. `health.py` reuses
`shared_core.monitoring.checks`' TCP/HTTP reachability primitives and
`shared_core.monitoring.status.calculate_status` rather than
reimplementing connectivity checks or status rollup.

## Architecture Notes

- **`NotificationType` repurposed, not extended**: the Prompt 012
  baseline `shared_core.enums.notification_type.NotificationType` held
  a channel-flavored value set (`toast`/`email`/`in_app`/`webhook`/
  `sms`) as a placeholder before this prompt's spec existed to clarify
  the two concepts are separate. Docs/025 uses "Type" for a 15-value
  *category* concept (Information/Success/.../Maintenance) and
  "Channel" for the actual delivery channels -- so `NotificationType`'s
  values were replaced with the category list, and a new
  `shared_core.enums.notification_channel.NotificationChannel` (8
  values, matching "CHANNELS") was added for the channel concept.
  Confirmed near-zero blast radius (one generic structural test file)
  before repurposing.
- **Real bug, caught while writing the manager/factory tests, not by
  inspection**: `NotificationManager.history`/`.dead_letters` default
  to their own fresh, empty stores via `field(default_factory=...)` --
  but `NotificationDispatcher` almost always already owns its *own*
  `HistoryStore`/`DeadLetterStore` instances. `create_notification_framework()`'s
  first draft built two separate pairs, so `manager.analytics` silently
  read back empty even after real dispatches went through. Fixed by
  constructing the stores once and passing the *same* instances to both
  the dispatcher and the manager; a regression test asserts
  `manager.history is manager.dispatcher._history` so this can't
  silently reappear.
- **A second real gap, also caught by testing**: `email.py` defined
  `render_email_body()` (a `RenderedNotification` -> `(plain, html)`
  helper) but never actually wired it into `EmailChannel.send()` --
  every email went out as plain text regardless of whether the caller
  had rendered a rich HTML/Markdown body, silently showing raw markup
  source to recipients. Fixed by reading an optional
  `message.metadata["body_format"]` convention (the message model's own
  documented extension point) and sending a proper multipart message
  when set, rather than adding a new field to `NotificationMessage`
  itself (docs/025's "MESSAGE MODEL" is a fixed field list).
- **Real bug, caught while writing the rate limiter test**: all four of
  `NotificationRateLimiter`'s scopes (`per_user`/`per_organization`/
  `per_channel`/global) share one underlying `RateLimitCache`-backed
  cache. Without a per-scope key prefix, a user ID and an organization
  ID with the same literal string value would silently share one
  counter. Fixed by prefixing each scope's identifier
  (`user:`/`org:`/`channel:`) before checking; a test using the same
  literal string as both a `user_id` and an `organization_id` confirms
  the two scopes stay isolated.
- **No circular imports**: `notifications -> queue` (`RetryPolicy`/
  `compute_backoff_delay` reuse), `notifications -> cache`
  (`RateLimitCache` reuse), and `notifications -> monitoring` (`checks`/
  `status` reuse for health) are all safe and one-directional -- none
  of those packages depend on `notifications`.
- **`trace`/`span`-style naming note, resolved the same way as Prompt
  024**: the `priority` submodule and the re-exported `Priority` enum
  differ only in case, which Python treats as distinct attribute names
  -- no actual collision, but verified concretely (not just reasoned
  about) before finalizing `__init__.py`, the same discipline as every
  prior prompt.
- **New dependencies**: `jinja2` (sandboxed template rendering),
  `aiosmtplib` (real async SMTP delivery), `markdown` (Markdown-to-HTML
  conversion for `render_to_html`); `aiosmtpd` as a dev-only dependency,
  for spinning up a genuine throwaway SMTP server in tests rather than
  mocking `aiosmtplib` away.
