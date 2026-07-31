"""The frameworks and controls this service ships knowing about.

Every control here is **automatable and real**: it names an evidence
path a platform collector actually produces and a comparison that
decides it. A shipped catalogue of un-automatable descriptions would
look impressive and assess nothing, and an organization would discover
that only after wiring up their estate.

The catalogue is deliberately small and cross-mapped rather than
exhaustive. A partial catalogue whose controls genuinely evaluate is
worth more than a complete one whose controls all return
``NOT_ASSESSED`` -- and the mappings are what let one evaluation answer
several standards at once, which is the property that makes adding the
next framework cheap.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import (
    ControlCategory,
    ControlRelationKind,
    ControlSeverity,
    FrameworkCode,
    FrameworkKind,
)
from app.rules.engine import Check, CheckOperator, LogicalOperator, Rule, referenced_paths


@dataclass(frozen=True, slots=True)
class ControlTemplate:
    """One shipped control."""

    code: str
    title: str
    description: str
    category: ControlCategory
    severity: ControlSeverity
    rule: Rule
    guidance: str = ""
    remediation_guidance: str = ""
    references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FrameworkTemplate:
    """One shipped framework and its controls."""

    slug: str
    name: str
    code: FrameworkCode
    kind: FrameworkKind
    description: str
    publisher: str
    framework_version: str
    controls: tuple[ControlTemplate, ...]
    weight: float = 1.0
    reference_url: str | None = None
    tags: tuple[str, ...] = ()


def _rule(name: str, *checks: Check, combinator: LogicalOperator = LogicalOperator.ALL) -> Rule:
    return Rule(name=name, logical_operator=combinator, checks=list(checks))


# ---- CIS Benchmarks ---------------------------------------------------

CIS = FrameworkTemplate(
    slug="cis-benchmarks",
    name="CIS Benchmarks",
    code=FrameworkCode.CIS_BENCHMARKS,
    kind=FrameworkKind.SECURITY,
    description="Center for Internet Security configuration baselines.",
    publisher="Center for Internet Security",
    framework_version="8.0",
    reference_url="https://www.cisecurity.org/cis-benchmarks",
    tags=("hardening", "configuration"),
    controls=(
        ControlTemplate(
            code="1.1.1",
            title="Remote root login is disabled",
            description=(
                "Direct remote login as root removes the accountability that makes an "
                "audit trail usable: every action is attributed to 'root' rather than to "
                "a person."
            ),
            category=ControlCategory.ACCESS_CONTROL,
            severity=ControlSeverity.CRITICAL,
            rule=_rule(
                "1.1.1",
                Check(
                    path="ssh.permit_root_login",
                    operator=CheckOperator.IN,
                    value=["no", "prohibit-password", False],
                    description="PermitRootLogin must not allow password root login.",
                ),
            ),
            remediation_guidance="Set PermitRootLogin to 'no' in sshd_config and reload sshd.",
        ),
        ControlTemplate(
            code="1.2.1",
            title="Password authentication is disabled for SSH",
            description="Key-based authentication only, so a guessable password is not a way in.",
            category=ControlCategory.ACCESS_CONTROL,
            severity=ControlSeverity.HIGH,
            rule=_rule(
                "1.2.1",
                Check(path="ssh.password_authentication", operator=CheckOperator.IS_FALSE),
            ),
            remediation_guidance="Set PasswordAuthentication to 'no' in sshd_config.",
        ),
        ControlTemplate(
            code="2.1.1",
            title="Host firewall is enabled",
            description="A host with no packet filter is exposed to its whole network segment.",
            category=ControlCategory.NETWORK_SECURITY,
            severity=ControlSeverity.HIGH,
            rule=_rule("2.1.1", Check(path="firewall.enabled", operator=CheckOperator.IS_TRUE)),
            remediation_guidance="Enable and persist the host firewall service.",
        ),
        ControlTemplate(
            code="3.1.1",
            title="System clock is synchronised",
            description=(
                "An unsynchronised clock makes every log on the host unusable as evidence, "
                "because events cannot be ordered against anything else."
            ),
            category=ControlCategory.LOGGING_MONITORING,
            severity=ControlSeverity.MEDIUM,
            rule=_rule(
                "3.1.1",
                Check(path="time.synchronised", operator=CheckOperator.IS_TRUE),
                Check(path="time.offset_seconds", operator=CheckOperator.BETWEEN, value=[-5, 5]),
            ),
            remediation_guidance="Enable chronyd or systemd-timesyncd against a reachable source.",
        ),
        ControlTemplate(
            code="4.1.1",
            title="Security patches are current",
            description="Unapplied security updates are the most exploited class of finding.",
            category=ControlCategory.VULNERABILITY_MANAGEMENT,
            severity=ControlSeverity.CRITICAL,
            rule=_rule(
                "4.1.1",
                Check(
                    path="packages.security_updates_pending",
                    operator=CheckOperator.COUNT_AT_MOST,
                    value=0,
                ),
            ),
            remediation_guidance="Apply outstanding security updates and reboot if required.",
        ),
        ControlTemplate(
            code="5.1.1",
            title="Audit logging is enabled",
            description=(
                "Without an audit daemon, there is nothing to investigate an incident with."
            ),
            category=ControlCategory.LOGGING_MONITORING,
            severity=ControlSeverity.HIGH,
            rule=_rule(
                "5.1.1",
                Check(path="auditd.enabled", operator=CheckOperator.IS_TRUE),
                Check(path="auditd.rules_loaded", operator=CheckOperator.COUNT_AT_LEAST, value=1),
            ),
            remediation_guidance="Enable auditd and load the baseline rule set.",
        ),
    ),
)


# ---- NIST 800-53 -------------------------------------------------------

NIST_800_53 = FrameworkTemplate(
    slug="nist-800-53",
    name="NIST SP 800-53",
    code=FrameworkCode.NIST_800_53,
    kind=FrameworkKind.REGULATORY,
    description="Security and privacy controls for information systems.",
    publisher="NIST",
    framework_version="Rev. 5",
    reference_url="https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final",
    tags=("federal", "security"),
    controls=(
        ControlTemplate(
            code="AC-6",
            title="Least privilege is enforced",
            description=(
                "Accounts hold only the authorisations their function requires. Measured "
                "here as the absence of unnecessary privileged accounts."
            ),
            category=ControlCategory.ACCESS_CONTROL,
            severity=ControlSeverity.CRITICAL,
            rule=_rule(
                "AC-6",
                Check(path="accounts.privileged", operator=CheckOperator.COUNT_AT_MOST, value=5),
                Check(path="ssh.permit_root_login", operator=CheckOperator.NOT_EQUALS, value="yes"),
            ),
            remediation_guidance=(
                "Review privileged accounts and remove those without a standing need."
            ),
        ),
        ControlTemplate(
            code="AU-2",
            title="Auditable events are defined and logged",
            description="The system records the events an investigation would need.",
            category=ControlCategory.LOGGING_MONITORING,
            severity=ControlSeverity.HIGH,
            rule=_rule(
                "AU-2",
                Check(path="auditd.enabled", operator=CheckOperator.IS_TRUE),
            ),
            remediation_guidance="Enable audit logging and forward it off the host.",
        ),
        ControlTemplate(
            code="SC-13",
            title="Cryptography in use is approved",
            description="Transport uses a version of TLS that is not known to be broken.",
            category=ControlCategory.CRYPTOGRAPHY,
            severity=ControlSeverity.CRITICAL,
            rule=_rule(
                "SC-13",
                Check(path="tls.min_version", operator=CheckOperator.GREATER_OR_EQUAL, value=1.2),
                Check(
                    path="tls.weak_ciphers",
                    operator=CheckOperator.COUNT_AT_MOST,
                    value=0,
                ),
            ),
            remediation_guidance=(
                "Set the minimum TLS version to 1.2 and remove weak cipher suites."
            ),
        ),
        ControlTemplate(
            code="SI-2",
            title="Flaw remediation is timely",
            description="Known vulnerabilities are fixed within the organization's window.",
            category=ControlCategory.VULNERABILITY_MANAGEMENT,
            severity=ControlSeverity.HIGH,
            rule=_rule(
                "SI-2",
                Check(
                    path="packages.last_patched_at",
                    operator=CheckOperator.NEWER_THAN_DAYS,
                    value=30,
                ),
            ),
            remediation_guidance="Bring the host into the regular patch cycle.",
        ),
        ControlTemplate(
            code="CP-9",
            title="System backups are performed",
            description="A recent, verified backup exists for the system.",
            category=ControlCategory.RESILIENCE,
            severity=ControlSeverity.HIGH,
            rule=_rule(
                "CP-9",
                Check(path="backup.enabled", operator=CheckOperator.IS_TRUE),
                Check(
                    path="backup.last_success_at", operator=CheckOperator.NEWER_THAN_DAYS, value=7
                ),
            ),
            remediation_guidance="Restore the backup schedule and verify a recent restore.",
        ),
    ),
)


# ---- ISO 27001 ---------------------------------------------------------

ISO_27001 = FrameworkTemplate(
    slug="iso-27001",
    name="ISO/IEC 27001",
    code=FrameworkCode.ISO_27001,
    kind=FrameworkKind.REGULATORY,
    description="Information security management system requirements.",
    publisher="ISO/IEC",
    framework_version="2022",
    reference_url="https://www.iso.org/standard/27001",
    tags=("isms", "certification"),
    controls=(
        ControlTemplate(
            code="A.8.2",
            title="Privileged access rights are restricted",
            description="Allocation and use of privileged access is controlled.",
            category=ControlCategory.ACCESS_CONTROL,
            severity=ControlSeverity.CRITICAL,
            rule=_rule(
                "A.8.2",
                Check(path="accounts.privileged", operator=CheckOperator.COUNT_AT_MOST, value=5),
            ),
            remediation_guidance="Reduce standing privilege and move to just-in-time elevation.",
        ),
        ControlTemplate(
            code="A.8.15",
            title="Logging is in place",
            description="Logs recording activities and anomalies are produced and kept.",
            category=ControlCategory.LOGGING_MONITORING,
            severity=ControlSeverity.HIGH,
            rule=_rule("A.8.15", Check(path="auditd.enabled", operator=CheckOperator.IS_TRUE)),
            remediation_guidance="Enable logging and confirm retention meets policy.",
        ),
        ControlTemplate(
            code="A.8.24",
            title="Cryptography is used appropriately",
            description="Rules for the effective use of cryptography are implemented.",
            category=ControlCategory.CRYPTOGRAPHY,
            severity=ControlSeverity.HIGH,
            rule=_rule(
                "A.8.24",
                Check(path="tls.min_version", operator=CheckOperator.GREATER_OR_EQUAL, value=1.2),
            ),
            remediation_guidance="Raise the minimum negotiated TLS version to 1.2.",
        ),
        ControlTemplate(
            code="A.8.13",
            title="Information backup",
            description="Backup copies are maintained and tested.",
            category=ControlCategory.RESILIENCE,
            severity=ControlSeverity.MEDIUM,
            rule=_rule("A.8.13", Check(path="backup.enabled", operator=CheckOperator.IS_TRUE)),
            remediation_guidance="Re-enable backups for this system.",
        ),
    ),
)


# ---- IEC 62443 (industrial) --------------------------------------------

IEC_62443 = FrameworkTemplate(
    slug="iec-62443",
    name="IEC 62443",
    code=FrameworkCode.IEC_62443,
    kind=FrameworkKind.INDUSTRIAL,
    description="Security for industrial automation and control systems.",
    publisher="IEC",
    framework_version="3-3",
    reference_url="https://www.iec.ch/",
    tags=("ot", "ics", "industrial"),
    controls=(
        ControlTemplate(
            code="SR-1.1",
            title="Human user identification and authentication",
            description="Every human user of the control system is identified and authenticated.",
            category=ControlCategory.ACCESS_CONTROL,
            severity=ControlSeverity.CRITICAL,
            rule=_rule(
                "SR-1.1",
                Check(path="accounts.shared", operator=CheckOperator.COUNT_AT_MOST, value=0),
            ),
            remediation_guidance="Replace shared operator accounts with named accounts.",
        ),
        ControlTemplate(
            code="SR-5.1",
            title="Network segmentation",
            description=(
                "Control system networks are segmented from business networks. The single "
                "most effective control in an industrial estate, and the one whose absence "
                "turns an office phishing email into a plant outage."
            ),
            category=ControlCategory.NETWORK_SECURITY,
            severity=ControlSeverity.CRITICAL,
            rule=_rule(
                "SR-5.1",
                Check(path="network.zone", operator=CheckOperator.IS_NOT_EMPTY),
                Check(path="network.routes_to_enterprise", operator=CheckOperator.IS_FALSE),
            ),
            remediation_guidance=(
                "Place the device in a defined zone with a conduit-controlled path."
            ),
        ),
        ControlTemplate(
            code="SR-7.6",
            title="Network and security configuration settings",
            description="The device runs a known, recorded configuration.",
            category=ControlCategory.CONFIGURATION,
            severity=ControlSeverity.HIGH,
            rule=_rule(
                "SR-7.6",
                Check(path="configuration.baseline_matched", operator=CheckOperator.IS_TRUE),
            ),
            remediation_guidance="Restore the device to its approved configuration baseline.",
        ),
    ),
)


# ---- SOC 2 --------------------------------------------------------------

SOC_2 = FrameworkTemplate(
    slug="soc-2",
    name="SOC 2",
    code=FrameworkCode.SOC_2,
    kind=FrameworkKind.REGULATORY,
    description="Trust services criteria for service organizations.",
    publisher="AICPA",
    framework_version="2017 (rev. 2022)",
    tags=("attestation", "saas"),
    controls=(
        ControlTemplate(
            code="CC6.1",
            title="Logical access is restricted",
            description="Access to systems is limited to authorised users.",
            category=ControlCategory.ACCESS_CONTROL,
            severity=ControlSeverity.CRITICAL,
            rule=_rule(
                "CC6.1",
                Check(path="ssh.password_authentication", operator=CheckOperator.IS_FALSE),
                Check(path="accounts.privileged", operator=CheckOperator.COUNT_AT_MOST, value=5),
            ),
            remediation_guidance="Disable password authentication and prune privileged accounts.",
        ),
        ControlTemplate(
            code="CC7.2",
            title="System monitoring detects anomalies",
            description="Monitoring is in place and producing data.",
            category=ControlCategory.LOGGING_MONITORING,
            severity=ControlSeverity.HIGH,
            rule=_rule(
                "CC7.2",
                Check(path="monitoring.agent_healthy", operator=CheckOperator.IS_TRUE),
                Check(
                    path="monitoring.last_metric_at",
                    operator=CheckOperator.NEWER_THAN_DAYS,
                    value=1,
                ),
            ),
            remediation_guidance="Restore the monitoring agent and confirm metrics are arriving.",
        ),
        ControlTemplate(
            code="A1.2",
            title="Recovery capability is maintained",
            description="Backups and recovery procedures support the availability commitment.",
            category=ControlCategory.RESILIENCE,
            severity=ControlSeverity.HIGH,
            rule=_rule(
                "A1.2",
                Check(
                    path="backup.last_success_at", operator=CheckOperator.NEWER_THAN_DAYS, value=7
                ),
            ),
            remediation_guidance="Repair the backup job and verify a restore.",
        ),
    ),
)


BUILTIN_FRAMEWORKS: tuple[FrameworkTemplate, ...] = (
    CIS,
    NIST_800_53,
    ISO_27001,
    IEC_62443,
    SOC_2,
)


@dataclass(frozen=True, slots=True)
class MappingTemplate:
    """A shipped equivalence between two controls in different frameworks."""

    source_framework: str
    source_code: str
    target_framework: str
    target_code: str
    relation: ControlRelationKind = ControlRelationKind.EQUIVALENT_TO
    confidence: float = 1.0
    note: str = ""


BUILTIN_MAPPINGS: tuple[MappingTemplate, ...] = (
    MappingTemplate(
        "nist-800-53",
        "AC-6",
        "iso-27001",
        "A.8.2",
        note="Both require privileged access to be held only where a function needs it.",
    ),
    MappingTemplate(
        "nist-800-53",
        "AU-2",
        "iso-27001",
        "A.8.15",
        note="Both require auditable events to be logged and retained.",
    ),
    MappingTemplate(
        "nist-800-53",
        "SC-13",
        "iso-27001",
        "A.8.24",
        note="Both require cryptography in use to be approved and current.",
    ),
    MappingTemplate(
        "nist-800-53",
        "AC-6",
        "soc-2",
        "CC6.1",
        relation=ControlRelationKind.SUPPORTS,
        confidence=0.8,
        note="CC6.1 is broader than AC-6; least privilege is one of the things it asks for.",
    ),
    MappingTemplate(
        "cis-benchmarks",
        "1.1.1",
        "nist-800-53",
        "AC-6",
        relation=ControlRelationKind.SUPPORTS,
        confidence=0.7,
        note="Disabling remote root login is one concrete way to evidence least privilege.",
    ),
    MappingTemplate(
        "cis-benchmarks",
        "5.1.1",
        "nist-800-53",
        "AU-2",
        relation=ControlRelationKind.SUPPORTS,
        confidence=0.9,
        note="Enabling auditd is the host-level implementation of the AU-2 requirement.",
    ),
    MappingTemplate(
        "cis-benchmarks",
        "4.1.1",
        "nist-800-53",
        "SI-2",
        relation=ControlRelationKind.SUPPORTS,
        confidence=0.9,
        note="Zero pending security updates is the observable form of timely flaw remediation.",
    ),
    MappingTemplate(
        "nist-800-53",
        "CP-9",
        "iso-27001",
        "A.8.13",
        note="Both require backups to exist and be current.",
    ),
    MappingTemplate(
        "nist-800-53",
        "CP-9",
        "soc-2",
        "A1.2",
        relation=ControlRelationKind.SUPPORTS,
        confidence=0.8,
        note="A1.2 asks for recovery capability, of which a current backup is the evidence.",
    ),
)


def framework_by_slug(slug: str) -> FrameworkTemplate | None:
    """Find a shipped framework by its slug."""
    return next((one for one in BUILTIN_FRAMEWORKS if one.slug == slug), None)


def all_evidence_paths() -> list[str]:
    """Every evidence path the shipped catalogue reads.

    What a collector should be asked to produce. Sorted and deduplicated
    so it can be compared against what a collector actually returned --
    the difference is the list of controls that will come back
    ``NOT_ASSESSED``, which is a far more useful thing to learn at
    configuration time than at audit time.
    """
    found: set[str] = set()
    for framework in BUILTIN_FRAMEWORKS:
        for control in framework.controls:
            found.update(referenced_paths(control.rule))
    return sorted(found)


__all__ = [
    "BUILTIN_FRAMEWORKS",
    "BUILTIN_MAPPINGS",
    "CIS",
    "IEC_62443",
    "ISO_27001",
    "NIST_800_53",
    "SOC_2",
    "ControlTemplate",
    "FrameworkTemplate",
    "MappingTemplate",
    "all_evidence_paths",
    "framework_by_slug",
]
