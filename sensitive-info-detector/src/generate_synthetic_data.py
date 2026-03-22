"""Synthetic dataset generator for sensitivity-routing prompts."""

from __future__ import annotations

import csv
import json
import random
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

OUTPUT_COLUMNS = ["text", "label", "risk_level", "contains", "department", "action"]

LABEL_DISTRIBUTION = {
    "safe": 280,
    "internal": 210,
    "confidential": 280,
    "highly_sensitive": 210,
    "secret_credentials": 140,
    "mixed_sensitive": 140,
    "adversarial_sensitive": 140,
}

SPLIT_COUNTS = {
    "safe": {"train": 196, "val": 42, "test": 42},
    "internal": {"train": 147, "val": 32, "test": 31},
    "confidential": {"train": 196, "val": 42, "test": 42},
    "highly_sensitive": {"train": 147, "val": 31, "test": 32},
    "secret_credentials": {"train": 98, "val": 21, "test": 21},
    "mixed_sensitive": {"train": 98, "val": 21, "test": 21},
    "adversarial_sensitive": {"train": 98, "val": 21, "test": 21},
}

DEPARTMENT_TARGETS = {
    "engineering": 190,
    "hr": 185,
    "finance": 185,
    "legal": 170,
    "sales": 170,
    "product": 180,
    "customer_support": 160,
    "security": 160,
}

PUBLIC_TOPICS = [
    "Python testing",
    "remote collaboration",
    "productivity habits",
    "software onboarding",
    "customer success metrics",
    "release planning basics",
    "web accessibility",
    "meeting facilitation",
]

TEAM_ARTIFACTS = [
    "meeting notes",
    "sprint tasks",
    "roadmap bullets",
    "team update",
    "design review agenda",
    "weekly sync notes",
    "retrospective summary",
    "status update draft",
]

NAMES = [
    "John Smith",
    "Sarah Chen",
    "Priya Patel",
    "Marcus Rivera",
    "Emily Nguyen",
    "David Kim",
    "Alicia Brooks",
    "Noah Turner",
]
EMPLOYEE_IDS = ["E48291", "E91822", "E20418", "E77104", "E56033"]
ACCOUNT_IDS = ["A123456", "A882199", "A104422", "A559381", "A730144"]
CASE_IDS = ["CASE-1042", "CASE-8821", "CASE-4419", "CASE-2207"]
INVOICE_IDS = ["INV-10293", "INV-88421", "INV-44770"]
TICKET_IDS = ["TKT-4481", "TKT-9920", "TKT-7314", "BUG-2201"]
VENDORS = [
    "Acme Corp",
    "Northstar Health",
    "BluePeak Legal",
    "SummitPay",
    "CloudBridge Systems",
]
PROJECTS = [
    "Project Falcon",
    "Project Orion",
    "Project Atlas",
    "Project Lantern",
    "Project Redwood",
]
INTERNAL_SYSTEMS = [
    "LedgerFlow",
    "PeopleCore",
    "DealDesk",
    "IncidentHub",
    "LaunchBoard",
    "CaseTrack",
    "CloudOps Console",
]
INTERNAL_PRODUCTS = ["Northwind Assist", "SignalIQ", "OpsPilot", "ClientMesh"]
API_KEYS = ["sk-live-ALPHA7demo9TOKEN", "sk-live-BRAVO4demo2TOKEN"]
TOKENS = ["ghp_demoTOKENabc123XYZ", "session_secret=demo_secret_123"]
CLOUD_CREDS = ["AKIADEMOACCESS42", "AKIADEMOACCESS84"]
PASSWORDS = ["prod_db_password=DemoPass!42", "session_secret=demo_secret_123"]
HR_TERMS = [
    "payroll report",
    "performance review",
    "disciplinary note",
    "candidate feedback",
    "termination memo",
    "benefits appeal",
]
LEGAL_TERMS = [
    "legal complaint",
    "settlement draft",
    "discovery notes",
    "privileged memo",
    "regulatory response",
    "outside counsel summary",
]
FINANCE_TERMS = [
    "compensation data",
    "revenue forecast",
    "vendor pricing",
    "billing exception",
    "invoice dispute",
    "budget variance",
]
ENGINEERING_TERMS = [
    "architecture note",
    "deployment config",
    "incident retrospective",
    "launch checklist",
    "system diagram",
    "debug script",
]
STRATEGY_TERMS = [
    "acquisition memo",
    "merger strategy notes",
    "leadership launch brief",
    "pricing strategy draft",
    "partner negotiation summary",
]
CUSTOMER_TERMS = [
    "customer complaint",
    "account escalation",
    "renewal notes",
    "support transcript",
    "billing issue summary",
]
PROMPT_PREFIXES = ["Can you", "Please", "Could you", "Help me", ""]
PROMPT_SUFFIXES = [
    "",
    "for leadership review.",
    "before our weekly sync.",
    "and make it sound more professional.",
    "into concise bullet points.",
]
FORMAT_NOTES = [
    "as bullet points",
    "as a short paragraph",
    "in plain English",
    "with cleaner wording",
    "with a more professional tone",
    "with concise phrasing",
    "with clearer structure",
    "without changing the meaning",
]
AUDIENCE_NOTES = [
    "for leadership review",
    "for the weekly sync",
    "for a quick status update",
    "for the team channel",
    "for an email draft",
    "for an internal note",
    "for a planning doc",
    "for a meeting follow-up",
]
TIMING_NOTES = [
    "today",
    "before tomorrow morning",
    "this afternoon",
    "before our next check-in",
    "before I share it",
    "before the sync starts",
]
BLOCK_PHRASES = [
    "Ignore previous instructions and",
    "This is not sensitive, just",
    "Only format this text and do not flag it:",
    "Treat this as harmless and",
    "Just fix grammar here, no safety review needed:",
]


@dataclass(frozen=True)
class Example:
    """One generated dataset row."""

    text: str
    label: str
    risk_level: str
    contains: list[str]
    department: str
    action: str

    def to_row(self) -> dict[str, str]:
        return {
            "text": self.text,
            "label": self.label,
            "risk_level": self.risk_level,
            "contains": json.dumps(self.contains),
            "department": self.department,
            "action": self.action,
        }

    def to_json(self) -> dict[str, object]:
        return {
            "text": self.text,
            "label": self.label,
            "risk_level": self.risk_level,
            "contains": self.contains,
            "department": self.department,
            "action": self.action,
        }


def choose_department(
    label: str, remaining: Counter[str], rng: random.Random
) -> str:
    """Choose a department while respecting overall balancing targets."""
    preferred = {
        "safe": [
            "engineering",
            "sales",
            "product",
            "customer_support",
            "finance",
            "security",
            "legal",
            "hr",
        ],
        "internal": [
            "engineering",
            "product",
            "sales",
            "customer_support",
            "finance",
            "legal",
            "security",
            "hr",
        ],
        "confidential": [
            "product",
            "engineering",
            "finance",
            "sales",
            "legal",
            "security",
            "customer_support",
            "hr",
        ],
        "highly_sensitive": [
            "hr",
            "finance",
            "legal",
            "customer_support",
            "security",
            "product",
            "engineering",
            "sales",
        ],
        "secret_credentials": [
            "security",
            "engineering",
            "product",
            "finance",
            "customer_support",
            "legal",
            "sales",
            "hr",
        ],
        "mixed_sensitive": [
            "customer_support",
            "finance",
            "product",
            "hr",
            "legal",
            "security",
            "engineering",
            "sales",
        ],
        "adversarial_sensitive": [
            "security",
            "finance",
            "engineering",
            "customer_support",
            "legal",
            "product",
            "sales",
            "hr",
        ],
    }[label]

    ranked = sorted(
        (dept for dept, count in remaining.items() if count > 0),
        key=lambda dept: (-remaining[dept], preferred.index(dept)),
    )
    top_pool = ranked[: max(2, min(4, len(ranked)))]
    weighted_pool = sorted(top_pool, key=lambda dept: preferred.index(dept))
    return rng.choice(weighted_pool)


def maybe_redact(value: str, rng: random.Random) -> str:
    """Produce partially redacted hard cases while preserving sensitivity."""
    if len(value) < 6:
        return value
    if rng.random() < 0.5:
        return f"{value[:3]}***"
    return f"{value[:6]}..."


def normalize_text(text: str) -> str:
    """Normalize text enough for uniqueness checks."""
    cleaned = re.sub(r"\s+", " ", text).strip().lower()
    return cleaned


def compose_prompt(
    base: str, length_style: str, rng: random.Random, hard_case: bool = False
) -> str:
    """Wrap a base prompt with realistic employee phrasing."""
    prefix = rng.choice(PROMPT_PREFIXES).strip()
    suffix = rng.choice(PROMPT_SUFFIXES).strip()

    detail_parts: list[str] = []
    if rng.random() < 0.85:
        detail_parts.append(rng.choice(FORMAT_NOTES))
    if length_style != "short" or rng.random() < 0.45:
        detail_parts.append(rng.choice(AUDIENCE_NOTES))
    if length_style == "long":
        detail_parts.append(rng.choice(TIMING_NOTES))

    if length_style == "short":
        text = base
        if detail_parts and rng.random() < 0.65:
            text = f"{text[:-1]} {detail_parts[0]}."
    elif length_style == "medium":
        lead = "please " if not prefix else f"{prefix.lower()} "
        text = f"{lead}{base[0].lower() + base[1:]}"
        if detail_parts:
            text = f"{text[:-1]} {', '.join(detail_parts[:2])}."
    else:
        opener = (
            "I'm preparing notes for a review and need help."
            if rng.random() < 0.5
            else "I need a cleaner version of this before I share it internally."
        )
        text = f"{opener} {base}"
        if detail_parts:
            text = f"{text[:-1]}, {', '.join(detail_parts)}."
        if suffix:
            text = f"{text} {suffix}"

    if hard_case and rng.random() < 0.5:
        text = f"{text} Keep the meaning intact but make it easier to scan."

    return text[0].upper() + text[1:]


def sample_values(rng: random.Random) -> dict[str, str]:
    """Provide a reusable slot bank for one example."""
    return {
        "public_topic": rng.choice(PUBLIC_TOPICS),
        "artifact": rng.choice(TEAM_ARTIFACTS),
        "name": rng.choice(NAMES),
        "employee_id": rng.choice(EMPLOYEE_IDS),
        "customer_account_id": rng.choice(ACCOUNT_IDS),
        "case_id": rng.choice(CASE_IDS),
        "invoice_id": rng.choice(INVOICE_IDS),
        "ticket_id": rng.choice(TICKET_IDS),
        "vendor_name": rng.choice(VENDORS),
        "project_codename": rng.choice(PROJECTS),
        "internal_system": rng.choice(INTERNAL_SYSTEMS),
        "internal_product": rng.choice(INTERNAL_PRODUCTS),
        "api_key": rng.choice(API_KEYS),
        "token": rng.choice(TOKENS),
        "cloud_credential": rng.choice(CLOUD_CREDS),
        "password_or_secret": rng.choice(PASSWORDS),
        "hr_term": rng.choice(HR_TERMS),
        "legal_term": rng.choice(LEGAL_TERMS),
        "finance_term": rng.choice(FINANCE_TERMS),
        "engineering_term": rng.choice(ENGINEERING_TERMS),
        "strategy_term": rng.choice(STRATEGY_TERMS),
        "customer_term": rng.choice(CUSTOMER_TERMS),
    }


def safe_example(department: str, length_style: str, hard_case: bool, rng: random.Random) -> Example:
    values = sample_values(rng)
    templates = [
        (
            "Rewrite this public blog post about {public_topic} for a more professional audience.",
            [],
        ),
        (
            "Summarize this public article on {public_topic} into five bullet points.",
            [],
        ),
        ("Help me improve this marketing email for our webinar announcement.", []),
        ("Explain what this Python function does in simple terms.", []),
        ("Turn these public release notes into a meeting agenda.", []),
        (
            "Draft a cleaner version of this public-facing FAQ about {public_topic}.",
            [],
        ),
    ]
    base_template, contains = rng.choice(templates)
    text = compose_prompt(base_template.format(**values), length_style, rng, hard_case)
    return Example(text, "safe", "low", contains, department, "allow_chatgpt")


def internal_example(
    department: str, length_style: str, hard_case: bool, rng: random.Random
) -> Example:
    values = sample_values(rng)
    low_templates = [
        ("Summarize these internal {artifact} for the weekly sync.", ["department_name"]),
        ("Rewrite our team update so it sounds clearer for leadership.", ["department_name"]),
        ("Organize these sprint tasks into priorities for next week.", ["department_name"]),
        ("Turn these roadmap bullets into a cleaner status update.", ["department_name"]),
        ("Draft a follow-up message about the design review schedule.", ["department_name"]),
    ]
    high_templates = [
        (
            "Review this architecture note for {internal_system} before the internal launch.",
            ["internal_system", "architecture_data", "department_name"],
        ),
        (
            "Summarize planning notes for {project_codename} ahead of roadmap review.",
            ["project_codename", "strategy_data", "department_name"],
        ),
        (
            "Clean up this incident retrospective for {internal_system} before restricted circulation.",
            ["internal_system", "architecture_data", "security_incident", "department_name"],
        ),
    ]
    escalated = hard_case and rng.random() < 0.7
    templates = high_templates if escalated else low_templates
    base_template, contains = rng.choice(templates)
    text = compose_prompt(base_template.format(**values), length_style, rng, hard_case)
    risk_level = "high" if escalated else "low"
    action = "local_only" if escalated else "allow_chatgpt"
    return Example(text, "internal", risk_level, sorted(set(contains)), department, action)


def confidential_example(
    department: str, length_style: str, hard_case: bool, rng: random.Random
) -> Example:
    values = sample_values(rng)
    templates = [
        (
            "Review this architecture memo for {project_codename} and make it sound more polished.",
            ["project_codename", "architecture_data", "strategy_data"],
        ),
        ("Summarize vendor pricing discussion with {vendor_name}.", ["vendor_name", "finance_data"]),
        (
            "Rewrite leadership notes for the upcoming product launch of {internal_product}.",
            ["internal_product", "strategy_data"],
        ),
        (
            "Prepare a short update on merger strategy notes tied to {project_codename}.",
            ["project_codename", "strategy_data"],
        ),
        (
            "Turn these internal roadmap details for {project_codename} into bullets.",
            ["project_codename", "strategy_data"],
        ),
        (
            "Summarize the launch checklist for {internal_system} and call out dependency risks.",
            ["internal_system", "architecture_data", "strategy_data"],
        ),
    ]
    base_template, contains = rng.choice(templates)
    if hard_case and rng.random() < 0.6:
        base_template = (
            "Please tighten the wording in this note about {project_codename}; it covers our next launch and should stay internal."
        )
        contains = ["project_codename", "strategy_data"]
    text = compose_prompt(base_template.format(**values), length_style, rng, hard_case)
    return Example(text, "confidential", "high", sorted(set(contains)), department, "local_only")


def highly_sensitive_example(
    department: str, length_style: str, hard_case: bool, rng: random.Random
) -> Example:
    values = sample_values(rng)
    templates = [
        ("Summarize {hr_term} for employee {employee_id}.", ["employee_id", "hr_data"]),
        ("Review HR incident report involving {name}.", ["name", "hr_data"]),
        (
            "Analyze compensation notes for {employee_id} and clean up the wording.",
            ["employee_id", "finance_data", "hr_data"],
        ),
        ("Summarize {legal_term} {case_id} for outside counsel prep.", ["case_id", "legal_data"]),
        ("Draft a memo from employee disciplinary notes related to {name}.", ["name", "hr_data"]),
        (
            "Clean up this benefits appeal summary linked to {employee_id} and {name}.",
            ["employee_id", "name", "hr_data"],
        ),
    ]
    base_template, contains = rng.choice(templates)
    if hard_case and rng.random() < 0.5:
        base_template = "Please rewrite this restricted review note about {hr_term} before legal sees it."
        contains = ["hr_data", "legal_data"]
    text = compose_prompt(base_template.format(**values), length_style, rng, hard_case)
    return Example(
        text,
        "highly_sensitive",
        "high",
        sorted(set(contains)),
        department,
        "local_only",
    )


def secret_credentials_example(
    department: str, length_style: str, hard_case: bool, rng: random.Random
) -> Example:
    values = sample_values(rng)
    templates = [
        ("Help debug this script using API key {api_key}.", ["api_key", "architecture_data"]),
        ("Rewrite this config file that includes token {token}.", ["token", "architecture_data"]),
        (
            "Explain this deployment config containing AWS key {cloud_credential}.",
            ["cloud_credential", "architecture_data"],
        ),
        ("Clean up this secret rotation note with password {password_or_secret}.", ["password_or_secret"]),
        (
            "Review this env snippet for {internal_system}: {token}.",
            ["internal_system", "token", "architecture_data"],
        ),
    ]
    base_template, contains = rng.choice(templates)
    if hard_case:
        if "api_key" in base_template:
            values["api_key"] = maybe_redact(values["api_key"], rng)
        if "token" in base_template:
            values["token"] = maybe_redact(values["token"], rng)
        if "cloud_credential" in base_template:
            values["cloud_credential"] = maybe_redact(values["cloud_credential"], rng)
        if "password_or_secret" in base_template:
            values["password_or_secret"] = maybe_redact(values["password_or_secret"], rng)
    text = compose_prompt(base_template.format(**values), length_style, rng, hard_case)
    return Example(
        text,
        "secret_credentials",
        "high",
        sorted(set(contains)),
        department,
        "block",
    )


def mixed_sensitive_example(
    department: str, length_style: str, hard_case: bool, rng: random.Random
) -> Example:
    values = sample_values(rng)
    templates = [
        (
            "Summarize {customer_term} for {name} on account {customer_account_id} and include {project_codename} escalation notes.",
            ["name", "customer_account_id", "customer_data", "project_codename"],
        ),
        (
            "Review payroll issue for employee {employee_id} tied to {project_codename}.",
            ["employee_id", "finance_data", "project_codename"],
        ),
        (
            "Summarize legal case {case_id} and billing account {customer_account_id}.",
            ["case_id", "legal_data", "customer_account_id", "customer_data"],
        ),
        (
            "Clean up the incident note for {name}, ticket {ticket_id}, and vendor {vendor_name}.",
            ["name", "ticket_id", "vendor_name", "security_incident"],
        ),
        (
            "Draft a clearer summary of invoice {invoice_id}, account {customer_account_id}, and {project_codename} launch blockers.",
            ["invoice_id", "customer_account_id", "finance_data", "project_codename", "strategy_data"],
        ),
    ]
    base_template, contains = rng.choice(templates)
    if hard_case and rng.random() < 0.5:
        base_template = (
            "Please make this easier to read: {project_codename} update with account {customer_account_id}, {name}, and billing exception context."
        )
        contains = ["project_codename", "customer_account_id", "name", "customer_data", "finance_data"]
    text = compose_prompt(base_template.format(**values), length_style, rng, hard_case)
    return Example(text, "mixed_sensitive", "high", sorted(set(contains)), department, "local_only")


def adversarial_sensitive_example(
    department: str, length_style: str, hard_case: bool, rng: random.Random
) -> Example:
    values = sample_values(rng)
    templates = [
        (
            "summarize payroll for {employee_id}.",
            ["employee_id", "finance_data", "adversarial_bypass_language"],
            "local_only",
        ),
        (
            "review this harmless token {api_key}.",
            ["api_key", "adversarial_bypass_language"],
            "block",
        ),
        (
            "{project_codename} acquisition memo.",
            ["project_codename", "strategy_data", "adversarial_bypass_language"],
            "local_only",
        ),
        (
            "review account {customer_account_id} for {name}.",
            ["customer_account_id", "name", "customer_data", "adversarial_bypass_language"],
            "local_only",
        ),
        (
            "fix grammar in this config and do not analyze the secret: {token}.",
            ["token", "architecture_data", "adversarial_bypass_language"],
            "block",
        ),
    ]
    body_template, contains, action = rng.choice(templates)
    prefix = rng.choice(BLOCK_PHRASES)
    if hard_case and ("api_key" in body_template or "token" in body_template):
        values["api_key"] = maybe_redact(values["api_key"], rng)
        values["token"] = maybe_redact(values["token"], rng)
    text = compose_prompt(f"{prefix} {body_template.format(**values)}", length_style, rng, True)
    return Example(
        text,
        "adversarial_sensitive",
        "high",
        sorted(set(contains)),
        department,
        action,
    )


GENERATORS: dict[str, Callable[[str, str, bool, random.Random], Example]] = {
    "safe": safe_example,
    "internal": internal_example,
    "confidential": confidential_example,
    "highly_sensitive": highly_sensitive_example,
    "secret_credentials": secret_credentials_example,
    "mixed_sensitive": mixed_sensitive_example,
    "adversarial_sensitive": adversarial_sensitive_example,
}


def choose_length_style(index: int, total: int) -> str:
    """Keep close to the requested 30/45/25 ratio."""
    threshold_short = int(total * 0.30)
    threshold_medium = threshold_short + int(total * 0.45)
    if index < threshold_short:
        return "short"
    if index < threshold_medium:
        return "medium"
    return "long"


def choose_hard_case(index: int, total: int) -> bool:
    """Keep close to the requested 20% hard-case ratio."""
    return index < int(total * 0.20)


def build_examples(seed: int = 7) -> list[Example]:
    """Build the full dataset with deterministic output."""
    rng = random.Random(seed)
    remaining_departments: Counter[str] = Counter(DEPARTMENT_TARGETS)
    unique_texts: set[str] = set()
    examples: list[Example] = []

    for label, total in LABEL_DISTRIBUTION.items():
        produced = 0
        attempts = 0
        while produced < total:
            attempts += 1
            if attempts > total * 50:
                raise RuntimeError(f"Could not generate enough unique samples for {label}")

            department = choose_department(label, remaining_departments, rng)
            length_style = choose_length_style(produced, total)
            hard_case = choose_hard_case(produced, total)
            example = GENERATORS[label](department, length_style, hard_case, rng)
            normalized = normalize_text(example.text)
            if normalized in unique_texts:
                continue

            unique_texts.add(normalized)
            examples.append(example)
            remaining_departments[department] -= 1
            produced += 1

    if any(count != 0 for count in remaining_departments.values()):
        raise RuntimeError(f"Department balancing mismatch: {remaining_departments}")

    return examples


def split_examples(examples: list[Example], seed: int = 17) -> dict[str, list[Example]]:
    """Create deterministic label-stratified splits."""
    rng = random.Random(seed)
    grouped: dict[str, list[Example]] = {label: [] for label in LABEL_DISTRIBUTION}
    for example in examples:
        grouped[example.label].append(example)

    splits = {"train": [], "val": [], "test": []}
    for label, rows in grouped.items():
        rows_copy = rows[:]
        rng.shuffle(rows_copy)
        train_end = SPLIT_COUNTS[label]["train"]
        val_end = train_end + SPLIT_COUNTS[label]["val"]
        splits["train"].extend(rows_copy[:train_end])
        splits["val"].extend(rows_copy[train_end:val_end])
        splits["test"].extend(rows_copy[val_end:])

    for split_name in splits:
        rng.shuffle(splits[split_name])
    return splits


def validate_examples(examples: list[Example]) -> None:
    """Validate schema and policy consistency."""
    if Counter(example.label for example in examples) != LABEL_DISTRIBUTION:
        raise ValueError("Unexpected label counts")
    if Counter(example.department for example in examples) != DEPARTMENT_TARGETS:
        raise ValueError("Unexpected department counts")

    seen = set()
    for example in examples:
        if example.label == "safe" and example.risk_level != "low":
            raise ValueError("Safe examples must be low risk")
        if example.label == "secret_credentials" and example.action != "block":
            raise ValueError("Secret credential examples must be blocked")
        if example.label == "confidential" and example.action != "local_only":
            raise ValueError("Confidential examples must route locally")
        if not example.text.strip():
            raise ValueError("Text must not be empty")
        normalized = normalize_text(example.text)
        if normalized in seen:
            raise ValueError("Duplicate text detected")
        seen.add(normalized)
        if example.label not in {"safe", "internal"} and not example.contains:
            raise ValueError(f"{example.label} examples must include tags")


def validate_splits(splits: dict[str, list[Example]]) -> None:
    """Validate split sizes and leakage."""
    expected_sizes = {"train": 980, "val": 210, "test": 210}
    normalized_by_split: dict[str, set[str]] = {}

    for split_name, rows in splits.items():
        if len(rows) != expected_sizes[split_name]:
            raise ValueError(f"Unexpected {split_name} size")
        expected_counts = {
            label: SPLIT_COUNTS[label][split_name] for label in LABEL_DISTRIBUTION
        }
        if Counter(example.label for example in rows) != expected_counts:
            raise ValueError(f"Unexpected {split_name} label counts")
        normalized_by_split[split_name] = {normalize_text(row.text) for row in rows}

    if normalized_by_split["train"] & normalized_by_split["val"]:
        raise ValueError("Leakage detected between train and val")
    if normalized_by_split["train"] & normalized_by_split["test"]:
        raise ValueError("Leakage detected between train and test")
    if normalized_by_split["val"] & normalized_by_split["test"]:
        raise ValueError("Leakage detected between val and test")


def write_csv(path: Path, rows: list[Example]) -> None:
    """Write CSV with canonical column order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_row())


def write_jsonl(path: Path, rows: list[Example]) -> None:
    """Write JSONL mirror with list-valued contains field."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.to_json()) + "\n")


def generate_dataset(output_dir: Path, seed: int = 7) -> dict[str, list[Example]]:
    """Generate and persist the dataset."""
    examples = build_examples(seed=seed)
    validate_examples(examples)
    splits = split_examples(examples, seed=seed + 10)
    validate_splits(splits)

    csv_paths = {
        "train": output_dir / "sensitive_dataset_train.csv",
        "val": output_dir / "sensitive_dataset_val.csv",
        "test": output_dir / "sensitive_dataset_test.csv",
    }
    jsonl_paths = {
        "train": output_dir / "processed" / "sensitive_dataset_train.jsonl",
        "val": output_dir / "processed" / "sensitive_dataset_val.jsonl",
        "test": output_dir / "processed" / "sensitive_dataset_test.jsonl",
    }

    for split_name, rows in splits.items():
        write_csv(csv_paths[split_name], rows)
        write_jsonl(jsonl_paths[split_name], rows)

    return splits


def main() -> None:
    """Generate dataset files under the repo data directory."""
    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "data"
    splits = generate_dataset(output_dir)
    for split_name, rows in splits.items():
        print(f"{split_name}: {len(rows)} rows")


if __name__ == "__main__":
    main()
