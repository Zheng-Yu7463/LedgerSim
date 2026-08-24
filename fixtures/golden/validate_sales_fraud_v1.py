from __future__ import annotations

import copy
import hashlib
import hmac
import json
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

FIXTURE_DIRECTORY = Path(__file__).resolve().parent
FIXTURE_PATH = FIXTURE_DIRECTORY / "sales-fraud-v1.json"
SCHEMA_PATH = FIXTURE_DIRECTORY / "sales-fraud-v1.schema.json"
REQUIRED_STATE_LAYERS = {"economic", "enterprise", "reported", "normative"}
INPUT_ROLES = {
    "ControlTransferred": "control_transfer",
    "SettlementRightEstablished": "settlement_right",
    "ShipmentRecordAccepted": "shipment_record",
    "SalesInvoiceIssued": "sales_invoice",
    "CustomerPaymentReceived": "customer_payment",
    "CustomerReceiptRecorded": "customer_receipt",
}


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def require_unique(values: list, description: str) -> None:
    if len(values) != len(set(values)):
        raise AssertionError(f"duplicate {description}")


def canonical_sha256(value: object) -> str:
    canonical_json = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode()).hexdigest()


def validate_schema(fixture: dict, schema: dict) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.validate(fixture)
    return validator


def validate_negative_schema_cases(fixture: dict, validator: Draft202012Validator) -> None:
    def empty_policy(candidate: dict) -> None:
        candidate["policy"] = {}

    def empty_command_payload(candidate: dict) -> None:
        candidate["steps"][0]["command"]["payload"] = {}

    def empty_labels(candidate: dict) -> None:
        candidate["labels"] = []

    def empty_visibility(candidate: dict) -> None:
        candidate["visibility_expectations"] = []

    def positive_understatement(candidate: dict) -> None:
        understated = next(
            item for item in candidate["misstatements"] if item["direction"] == "understated"
        )
        understated["misstatement_amount"] = understated["misstatement_amount"].removeprefix("-")

    def commitment_without_expiry(candidate: dict) -> None:
        commitment_event = next(
            event
            for step in candidate["steps"]
            for event in step["expected_events"]
            if event["event_type"] == "CustomerCommitmentEstablished"
        )
        del commitment_event["payload"]["expires_at"]

    def false_accounting_digest_assertion(candidate: dict) -> None:
        candidate["determinism_tests"]["event_order_permutations"][0][
            "expected_accounting_content_digest_equal"
        ] = False

    def string_lineage_digest_assertion(candidate: dict) -> None:
        candidate["determinism_tests"]["event_order_permutations"][0][
            "expected_lineage_digest_equal"
        ] = "yes"

    def duplicate_decision_spec(candidate: dict) -> None:
        candidate["decision_specs"][1] = copy.deepcopy(candidate["decision_specs"][0])

    mutations = {
        "empty policy": empty_policy,
        "empty command payload": empty_command_payload,
        "empty labels": empty_labels,
        "empty visibility": empty_visibility,
        "positive amount marked understated": positive_understatement,
        "customer commitment without expires_at": commitment_without_expiry,
        "false accounting digest equality": false_accounting_digest_assertion,
        "string lineage digest equality": string_lineage_digest_assertion,
        "duplicate decision spec": duplicate_decision_spec,
    }

    for description, mutate in mutations.items():
        candidate = copy.deepcopy(fixture)
        mutate(candidate)
        try:
            validator.validate(candidate)
        except ValidationError:
            continue
        raise AssertionError(f"schema accepted invalid case: {description}")


def validate_references_and_uniqueness(fixture: dict) -> None:
    state_ids = set(fixture["state_snapshots"])
    referenced_state_ids = {step["expected_state_ref"] for step in fixture["steps"]}
    if referenced_state_ids != state_ids:
        raise AssertionError("step state references and declared state snapshots differ")

    command_ids = [step["command"]["command_id"] for step in fixture["steps"]]
    event_ids = [
        event["event_id"] for step in fixture["steps"] for event in step["expected_events"]
    ]
    journal_ids = [journal["journal_id"] for journal in fixture["journals"]]
    journal_line_ids = [
        line["line_id"] for journal in fixture["journals"] for line in journal["lines"]
    ]
    case_roles = [
        (journal["accounting_case_key"], journal["journal_role"]) for journal in fixture["journals"]
    ]
    case_roles.extend((case["accounting_case_key"], "pending") for case in fixture["pending_cases"])

    require_unique(command_ids, "command_id")
    require_unique(event_ids, "event_id")
    require_unique(journal_ids, "journal_id")
    require_unique(journal_line_ids, "journal line_id")
    require_unique(case_roles, "accounting case role")

    event_id_set = set(event_ids)
    for journal in fixture["journals"]:
        missing_inputs = set(journal["input_event_ids"]) - event_id_set
        if missing_inputs:
            raise AssertionError(f"journal has missing input events: {sorted(missing_inputs)}")

    journals_by_id = {journal["journal_id"]: journal for journal in fixture["journals"]}
    reversed_originals = []
    for journal in fixture["journals"]:
        original_id = journal["reverses_journal_id"]
        if journal["journal_role"] == "recognition":
            if original_id is not None:
                raise AssertionError("recognition journal cannot reverse another journal")
            continue
        if original_id not in journals_by_id:
            raise AssertionError("reversal journal references a missing original journal")
        original = journals_by_id[original_id]
        if original["journal_role"] != "recognition":
            raise AssertionError("reversal journal must reference a recognition journal")
        if (
            original["accounting_case_key"] != journal["accounting_case_key"]
            or original["ledger_type"] != journal["ledger_type"]
        ):
            raise AssertionError("reversal and original journal contracts differ")
        reversed_originals.append(original_id)
    require_unique(reversed_originals, "reversed original journal")

    artifact_ids = event_id_set | set(journal_ids) | set(journal_line_ids)
    artifact_ids |= {item["object_id"] for item in fixture["misstatements"]}
    label_ids = [label["object_id"] for label in fixture["labels"]]
    require_unique(label_ids, "label object_id")
    missing_label_objects = set(label_ids) - artifact_ids
    if missing_label_objects:
        raise AssertionError(f"labels reference missing objects: {sorted(missing_label_objects)}")

    visibility_relations = [
        (
            item["object_id"],
            item["observer_profile_id"],
            item["observation_cutoff"],
            item["view_policy_version"],
        )
        for item in fixture["visibility_expectations"]
    ]
    require_unique(visibility_relations, "visibility relation")
    visibility_ids = {relation[0] for relation in visibility_relations}
    if visibility_ids - set(label_ids):
        raise AssertionError("visibility references an unlabeled object")

    ordinary_visibility_ids = {
        item["object_id"]
        for item in fixture["visibility_expectations"]
        if item["observer_profile_id"] == "ordinary_business_v1"
    }
    if ordinary_visibility_ids != set(label_ids):
        raise AssertionError("ordinary-business visibility must cover every labeled object")

    fraud_decision_ids = [
        event["event_id"]
        for step in fixture["steps"]
        for event in step["expected_events"]
        if event["event_type"] == "FraudDecisionRecorded"
    ]
    if len(fraud_decision_ids) != 1:
        raise AssertionError("fixture must contain exactly one fraud decision event")
    fraud_decision_visibility = {
        item["observer_profile_id"]: item["access_status"]
        for item in fixture["visibility_expectations"]
        if item["object_id"] == fraud_decision_ids[0]
    }
    if fraud_decision_visibility != {
        "ordinary_business_v1": "restricted",
        "restricted_research_v1": "allowed",
    }:
        raise AssertionError("fraud decision visibility does not prove observer-dependent access")


def validate_accounting(fixture: dict) -> None:
    for journal in fixture["journals"]:
        debits = sum(Decimal(line["debit_amount"]) for line in journal["lines"])
        credits = sum(Decimal(line["credit_amount"]) for line in journal["lines"])
        if debits != credits:
            raise AssertionError(f"unbalanced journal: {journal['journal_id']}")

    for state_id, state in fixture["state_snapshots"].items():
        if not REQUIRED_STATE_LAYERS.issubset(state):
            raise AssertionError(f"state snapshot lacks a required layer: {state_id}")
        for ledger_type in ("reported", "normative"):
            ledger = state[ledger_type]
            assets = (
                Decimal(ledger["bank"])
                + Decimal(ledger["accounts_receivable"])
                + Decimal(ledger["inventory"])
            )
            equity = Decimal(ledger["paid_in_capital"]) + Decimal(ledger["profit"])
            if assets != equity:
                raise AssertionError(f"accounting equation fails: {state_id}/{ledger_type}")
            if Decimal(ledger["profit"]) != Decimal(ledger["sales_revenue"]) - Decimal(
                ledger["cost_of_goods_sold"]
            ):
                raise AssertionError(f"profit equation fails: {state_id}/{ledger_type}")

    baseline = fixture["state_snapshots"]["state-baseline-005"]
    fraud = fixture["state_snapshots"]["state-fraud-004"]
    if baseline["reported"] != baseline["normative"]:
        raise AssertionError("baseline reported and normative ledgers differ")
    if baseline["reported"] != fraud["reported"]:
        raise AssertionError("baseline and fraud reported views differ")

    final_differences = {
        item: Decimal(fraud["reported"][item]) - Decimal(fraud["normative"][item])
        for item in (
            "accounts_receivable",
            "inventory",
            "sales_revenue",
            "cost_of_goods_sold",
            "profit",
        )
    }
    declared_differences = {
        item["item"]: Decimal(item["misstatement_amount"]) for item in fixture["misstatements"]
    }
    if final_differences != declared_differences:
        raise AssertionError("declared misstatements do not match final ledger differences")


def validate_accounting_digests_and_permutations(fixture: dict) -> None:
    events = {
        event["event_id"]: event for step in fixture["steps"] for event in step["expected_events"]
    }
    journals = {journal["journal_id"]: journal for journal in fixture["journals"]}

    for journal in journals.values():
        rule_version = journal["accounting_case_key"].split("|")[3]
        if journal["journal_role"] == "reversal":
            rule_version = f"{rule_version}:reversal_v1"
        content = {
            "accounting_date": journal["accounting_date"],
            "accounting_period": journal["accounting_date"][:7],
            "currency": fixture["currency"],
            "ledger_type": journal["ledger_type"],
            "lines": sorted(
                [
                    {
                        "account": line["account"],
                        "credit_amount": line["credit_amount"],
                        "debit_amount": line["debit_amount"],
                    }
                    for line in journal["lines"]
                ],
                key=lambda line: (line["account"], line["debit_amount"], line["credit_amount"]),
            ),
            "rule_version": rule_version,
        }
        if canonical_sha256(content) != journal["accounting_content_digest"]:
            raise AssertionError(f"accounting content digest differs: {journal['journal_id']}")

        expected_lineage = sorted(
            [
                {
                    "event_semantic_id": (
                        f"{events[event_id]['event_type']}|"
                        f"{events[event_id]['payload']['business_chain_id']}"
                    ),
                    "input_role": INPUT_ROLES[events[event_id]["event_type"]],
                }
                for event_id in journal["input_event_ids"]
            ],
            key=lambda item: (item["input_role"], item["event_semantic_id"]),
        )
        if journal["input_lineage"] != expected_lineage:
            raise AssertionError(
                f"journal lineage differs from input events: {journal['journal_id']}"
            )
        if canonical_sha256(expected_lineage) != journal["lineage_digest"]:
            raise AssertionError(f"lineage digest differs: {journal['journal_id']}")

    groups: dict[str, list[dict]] = {}
    for permutation in fixture["determinism_tests"]["event_order_permutations"]:
        groups.setdefault(permutation["comparison_group"], []).append(permutation)
        missing_events = set(permutation["event_refs"]) - set(events)
        missing_journals = set(permutation["expected_journal_ids"]) - set(journals)
        if missing_events or missing_journals:
            raise AssertionError(f"permutation has missing references: {permutation['name']}")
        for journal_id in permutation["expected_journal_ids"]:
            if set(journals[journal_id]["input_event_ids"]) != set(permutation["event_refs"]):
                raise AssertionError(
                    f"permutation inputs differ from journal lineage: {permutation['name']}"
                )

    for group_name, permutations in groups.items():
        if len(permutations) != 2:
            raise AssertionError(f"comparison group must contain two permutations: {group_name}")
        first, second = permutations
        if set(first["event_refs"]) != set(second["event_refs"]):
            raise AssertionError(f"comparison group uses different event sets: {group_name}")
        if set(first["expected_journal_ids"]) != set(second["expected_journal_ids"]):
            raise AssertionError(f"comparison group uses different journals: {group_name}")
        first_digests = sorted(
            (
                journals[journal_id]["accounting_content_digest"],
                journals[journal_id]["lineage_digest"],
            )
            for journal_id in first["expected_journal_ids"]
        )
        second_digests = sorted(
            (
                journals[journal_id]["accounting_content_digest"],
                journals[journal_id]["lineage_digest"],
            )
            for journal_id in second["expected_journal_ids"]
        )
        if first_digests != second_digests:
            raise AssertionError(f"permutation digests differ: {group_name}")


def validate_random_vectors(fixture: dict) -> None:
    specs = {item["decision_spec_id"]: item for item in fixture["decision_specs"]}
    if set(specs) != {"payment_delay_v1", "post_fraud_collection_v1"}:
        raise AssertionError("decision specs must contain each required specification once")

    tests = {item["name"]: item for item in fixture["counterfactual_tests"]}
    if set(tests) != {
        "shared_state_shared_random",
        "causal_branch_random",
        "raw_branch_id_forbidden",
    }:
        raise AssertionError("counterfactual tests must contain each required case once")

    for test_name in ("shared_state_shared_random", "causal_branch_random"):
        test = tests[test_name]
        spec = specs[test["decision_spec_id"]]
        if set(test["normalized_input"]) != set(spec["input_fields"]):
            raise AssertionError(f"normalized input differs from DecisionSpec: {test_name}")
        if canonical_sha256(test["normalized_input"]) != test["expected_state_digest"]:
            raise AssertionError(f"decision state digest differs: {test_name}")

        decision_id = spec["decision_id_template"].format(**test["normalized_input"])
        if decision_id != test["expected_decision_id"]:
            raise AssertionError(f"decision ID differs from DecisionSpec: {test_name}")

        random_key_parts = [
            test["counterfactual_key"],
            spec["decision_spec_id"],
            str(spec["version"]),
            test["normalized_input"]["customer_id"],
            test["normalized_input"]["period"],
            str(test["normalized_input"]["occurrence_index"]),
        ]
        if test_name == "causal_branch_random":
            random_key_parts.append(test["normalized_input"]["causal_context_id"])
        derived_random_key = "|".join(random_key_parts)
        if derived_random_key != test["expected_random_key"]:
            raise AssertionError(f"random key differs from DecisionSpec: {test_name}")

        random_digest = hmac.new(
            test["root_seed"].encode(),
            derived_random_key.encode(),
            hashlib.sha256,
        ).hexdigest()
        if random_digest != test["expected_random_hex"]:
            raise AssertionError(f"random vector differs: {test_name}")

    causal = tests["causal_branch_random"]
    events = {
        event["event_id"]: (event, step["command"])
        for step in fixture["steps"]
        for event in step["expected_events"]
    }
    labels = {item["object_id"]: item for item in fixture["labels"]}
    if causal["cause_event_id"] not in events:
        raise AssertionError("causal random vector references a missing event")
    cause_event, cause_command = events[causal["cause_event_id"]]
    if cause_event["event_type"] != "FraudDecisionRecorded":
        raise AssertionError("causal random vector does not reference a fraud decision")
    if labels[causal["cause_event_id"]]["causal_role"] != "direct_action":
        raise AssertionError("causal random cause is not labeled as a direct action")
    expected_semantic_ancestor = (
        f"fraud-decision|{cause_command['actor_id']}|"
        f"{cause_event['payload']['target_period']}|{cause_event['payload']['target_amount']}"
    )
    if causal["causal_ancestor_semantic_keys"] != [expected_semantic_ancestor]:
        raise AssertionError("causal ancestor semantic key differs from the cause event")

    context_material = "|".join(
        [
            *sorted(causal["causal_ancestor_semantic_keys"]),
            causal["decision_spec_id"],
            str(specs[causal["decision_spec_id"]]["version"]),
        ]
    ).encode()
    if hashlib.sha256(context_material).hexdigest() != causal["expected_causal_context_id"]:
        raise AssertionError("causal context digest differs")
    if causal["normalized_input"]["causal_context_id"] != causal["expected_causal_context_id"]:
        raise AssertionError("causal normalized input uses a different context")


def validate_release_gates(fixture: dict) -> None:
    tests = {item["name"]: item for item in fixture["release_tests"]}
    expected_names = {
        "single_branch_publish_succeeds",
        "second_twin_publish_rejected",
        "duplicate_history_fingerprint_rejected",
    }
    if set(tests) != expected_names:
        raise AssertionError("release tests must contain each required case once")

    for test_name, test in tests.items():
        pair_keys: set[tuple[int, str]] = set()
        history_keys: set[tuple[int, str]] = set()
        for member in test["existing_members"]:
            pair_key = (member["dataset_major_version"], member["branch_pair_id"])
            history_key = (member["dataset_major_version"], member["shared_history_fingerprint"])
            if pair_key in pair_keys or history_key in history_keys:
                raise AssertionError(f"release test starts from an invalid state: {test_name}")
            pair_keys.add(pair_key)
            history_keys.add(history_key)

        candidate = test["candidate"]
        candidate_pair_key = (candidate["dataset_major_version"], candidate["branch_pair_id"])
        candidate_history_key = (
            candidate["dataset_major_version"],
            candidate["shared_history_fingerprint"],
        )
        if candidate_pair_key in pair_keys:
            actual_result = "BranchPairAlreadyPublished"
        elif candidate_history_key in history_keys:
            actual_result = "DuplicateSharedHistoryFingerprint"
        else:
            actual_result = "published"

        if actual_result != test["expected_result"]:
            raise AssertionError(f"release gate result differs: {test_name}")

    twin_test = tests["second_twin_publish_rejected"]
    twin_existing = twin_test["existing_members"][0]
    twin_candidate = twin_test["candidate"]
    if twin_existing["branch_id"] == twin_candidate["branch_id"]:
        raise AssertionError("twin release test must use two different branches")
    if (
        twin_existing["dataset_major_version"],
        twin_existing["branch_pair_id"],
    ) != (
        twin_candidate["dataset_major_version"],
        twin_candidate["branch_pair_id"],
    ):
        raise AssertionError("twin release test members must belong to the same pair")

    history_test = tests["duplicate_history_fingerprint_rejected"]
    history_existing = history_test["existing_members"][0]
    history_candidate = history_test["candidate"]
    if history_existing["branch_pair_id"] == history_candidate["branch_pair_id"]:
        raise AssertionError("history collision test must use different branch pairs")
    if (
        history_existing["shared_history_fingerprint"]
        != history_candidate["shared_history_fingerprint"]
    ):
        raise AssertionError("history collision test must reuse the same fingerprint")


def main() -> None:
    fixture = load_json(FIXTURE_PATH)
    schema = load_json(SCHEMA_PATH)
    validator = validate_schema(fixture, schema)
    validate_negative_schema_cases(fixture, validator)
    validate_references_and_uniqueness(fixture)
    validate_accounting(fixture)
    validate_accounting_digests_and_permutations(fixture)
    validate_random_vectors(fixture)
    validate_release_gates(fixture)
    print(
        "PASS: schema, 9 negative cases, references, accounting digests, "
        "visibility, random vectors, and release gates"
    )


if __name__ == "__main__":
    main()
