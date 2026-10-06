"""DPDP Act 2023 control library and DPIA questionnaire (SRS section 5).

The control library joins discovery output to each obligation of the Act so
every risk cites the section it would breach. Rule numbers follow the DPDP
Rules, 2025 as notified on 13 November 2025 and should be re-checked against the
gazette text before the library is frozen (SRS section 5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Framework(str, Enum):
    DPDP = "dpdp"
    ISO27701 = "iso27701"
    ISO27001 = "iso27001"
    CERTIN = "certin"


@dataclass(frozen=True)
class Control:
    ref: str                       # DPDP section/rule reference
    obligation: str
    platform_check: str
    evidence_source: str
    question_keys: tuple[str, ...] = ()
    iso27701: tuple[str, ...] = ()
    iso27001: tuple[str, ...] = ()
    certin: tuple[str, ...] = ()


# SRS section 5.1 control library.
CONTROL_LIBRARY: list[Control] = [
    Control(
        ref="S.4, S.6",
        obligation="Processing only with consent or for a legitimate use; consent free, "
                   "specific, informed, unambiguous and withdrawable",
        platform_check="A lawful basis is recorded for every PII category in the inventory; "
                       "consent capture and withdrawal path described",
        evidence_source="Questionnaire B + inventory",
        question_keys=("B1", "B2", "B3"),
        iso27701=("7.2.2", "7.2.3"), iso27001=("A.5.34",),
    ),
    Control(
        ref="S.5, Rule 3",
        obligation="Notice to the Data Principal in plain language, in English and Eighth "
                   "Schedule languages",
        platform_check="Notice text or link attached; categories in notice match categories found",
        evidence_source="Questionnaire C + diff against inventory",
        question_keys=("C1", "C2", "C3"),
        iso27701=("7.3.2", "7.3.3"),
    ),
    Control(
        ref="S.7",
        obligation="Legitimate uses (employment, state functions, medical emergency, legal obligation)",
        platform_check="Where no consent, the legitimate use is named and fits",
        evidence_source="Questionnaire B",
        question_keys=("B4",),
    ),
    Control(
        ref="S.8(2)",
        obligation="Processing by a Data Processor only under a valid contract",
        platform_check="Processor list with contract reference per PII category shared",
        evidence_source="Questionnaire F",
        question_keys=("F1", "F2"),
        iso27701=("7.2.6",), iso27001=("A.5.19", "A.5.20"),
    ),
    Control(
        ref="S.8(3)",
        obligation="Accuracy and completeness where data affects a decision",
        platform_check="Correction mechanism described",
        evidence_source="Questionnaire H",
        question_keys=("H2",),
    ),
    Control(
        ref="S.8(4), S.8(5), Rule 6",
        obligation="Reasonable security safeguards: encryption, masking/tokenisation, access "
                   "control, logging and monitoring, backups, log retention",
        platform_check="Protection state per column; grants captured; access-review and "
                       "monitoring answers",
        evidence_source="Scan + Questionnaire E",
        question_keys=("E1", "E2", "E3", "E4", "E5"),
        iso27701=("8.2.1",), iso27001=("A.8.10", "A.8.11", "A.8.12", "A.8.24"),
        certin=("Direction 70B logging",),
    ),
    Control(
        ref="S.8(6), Rule 7",
        obligation="Breach intimation to the Data Protection Board and affected Data Principals",
        platform_check="Incident procedure, contact list and 72-hour reporting path documented",
        evidence_source="Questionnaire J",
        question_keys=("J1", "J2", "J3"),
        iso27001=("A.5.24", "A.5.26"), certin=("6-hour incident reporting",),
    ),
    Control(
        ref="S.8(7), Rule 8",
        obligation="Erasure when purpose is served or consent withdrawn; retention periods",
        platform_check="Retention period per PII category; purge job or procedure named",
        evidence_source="Questionnaire D + inventory",
        question_keys=("D2", "D3"),
        iso27701=("7.4.7",), iso27001=("A.8.10",),
    ),
    Control(
        ref="S.8(9), S.8(10), S.13",
        obligation="Grievance redressal mechanism and published contact",
        platform_check="Grievance channel and SLA documented",
        evidence_source="Questionnaire H",
        question_keys=("H4",),
    ),
    Control(
        ref="S.9, Rule 10",
        obligation="Children's data: verifiable parental consent, no tracking or targeted advertising",
        platform_check="Age of user base; under-18 indicators from scan; consent flow",
        evidence_source="Scan + Questionnaire I",
        question_keys=("I1", "I2", "I3"),
    ),
    Control(
        ref="S.10, Rule 12",
        obligation="Significant Data Fiduciary duties: DPO in India, independent audit, periodic "
                   "DPIA, algorithmic due diligence",
        platform_check="SDF status recorded at organisation level; DPIA cadence enforced",
        evidence_source="Admin settings + workflow",
        question_keys=(),
    ),
    Control(
        ref="S.11, S.12, S.14, Rule 13",
        obligation="Rights of access, correction, erasure and nomination",
        platform_check="Capability to locate and act on one principal's data across the application",
        evidence_source="Questionnaire H",
        question_keys=("H1", "H2", "H3"),
    ),
    Control(
        ref="S.16, Rule 14",
        obligation="Transfer of personal data outside India",
        platform_check="Hosting location, SaaS and processor jurisdictions",
        evidence_source="Questionnaire G",
        question_keys=("G1", "G2"),
    ),
    Control(
        ref="S.33, Schedule",
        obligation="Penalties up to Rs 250 crore for failure of security safeguards",
        platform_check="Used in risk impact scoring",
        evidence_source="Risk engine",
        question_keys=(),
    ),
]


@dataclass(frozen=True)
class Question:
    key: str
    text: str
    guidance: str = ""


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    answered_by: str
    questions: tuple[Question, ...] = field(default_factory=tuple)


# SRS section 5.2 questionnaire (core questions per section).
QUESTIONNAIRE: list[Section] = [
    Section("A", "Processing overview", "Owner", (
        Question("A1", "What is the business purpose of this application?"),
        Question("A2", "Who are the data principals (employees, consumers, vendors, public)?"),
        Question("A3", "What are the record volumes?"),
        Question("A4", "How does personal data enter the system?"),
    )),
    Section("B", "Lawful basis and consent", "Owner, reviewed by DPO", (
        Question("B1", "What is the lawful basis for each PII category?"),
        Question("B2", "How is consent captured and recorded?"),
        Question("B3", "How can a principal withdraw consent?"),
        Question("B4", "Where no consent is used, which legitimate use (S.7) applies?"),
    )),
    Section("C", "Notice and transparency", "Owner", (
        Question("C1", "Does a privacy notice exist and where is it shown?"),
        Question("C2", "In which languages is the notice available?"),
        Question("C3", "Do the notice categories match the inventory?"),
    )),
    Section("D", "Minimisation and retention", "Owner", (
        Question("D1", "Is each PII category necessary for the stated purpose?"),
        Question("D2", "What is the retention period per category?"),
        Question("D3", "What is the deletion mechanism, and are archived copies covered?"),
    )),
    Section("E", "Security safeguards", "Owner with IT", (
        Question("E1", "Is data encrypted at rest and in transit?"),
        Question("E2", "Is data masked in non-production environments?"),
        Question("E3", "What is the access-control model and privileged-access review?"),
        Question("E4", "Is access logged and monitored?"),
        Question("E5", "Are backups protected?"),
    )),
    Section("F", "Processors and sharing", "Owner", (
        Question("F1", "Which internal systems and external parties receive this data?"),
        Question("F2", "Is there a contract and a stated purpose for each sharing?"),
    )),
    Section("G", "Cross-border", "Owner", (
        Question("G1", "Where is the application hosted?"),
        Question("G2", "Is any processing or support performed outside India?"),
    )),
    Section("H", "Data principal rights and grievance", "Owner", (
        Question("H1", "Can the system find and export one person's data?"),
        Question("H2", "Can it correct one person's data?"),
        Question("H3", "Can it erase one person's data?"),
        Question("H4", "What is the grievance channel and its SLA?"),
    )),
    Section("I", "Children's data", "Owner", (
        Question("I1", "Does the system knowingly or possibly hold under-18 data?"),
        Question("I2", "Is verifiable parental consent obtained?"),
        Question("I3", "Is profiling or targeted advertising of children prevented?"),
    )),
    Section("J", "Breach readiness", "Owner with ISD", (
        Question("J1", "Does the incident plan cover this application?"),
        Question("J2", "Is the Board and principal notification path defined?"),
        Question("J3", "When was the last tabletop exercise?"),
    )),
    Section("K", "Automated decisions", "Owner", (
        Question("K1", "Does the system perform scoring, profiling or automated decisions?"),
        Question("K2", "Is there human review of automated decisions?"),
    )),
]

# Sections whose answers feed control effectiveness in the risk engine (SRS 5.3).
EFFECTIVENESS_SECTIONS = ("D", "E", "H", "J")


def question_keys() -> list[str]:
    return [q.key for s in QUESTIONNAIRE for q in s.questions]


def effectiveness_question_keys() -> list[str]:
    return [q.key for s in QUESTIONNAIRE if s.key in EFFECTIVENESS_SECTIONS
            for q in s.questions]
