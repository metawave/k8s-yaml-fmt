#!/usr/bin/env python3
"""
Kubernetes YAML Formatter with idiomatic key ordering.

Ensures consistent key order for K8s manifests:
- Top level: apiVersion, kind, metadata, spec, data, stringData, ...
- metadata: name, namespace, labels, annotations
- spec fields: kind-specific ordering

Usage:
    k8s_yaml_fmt.py <file.yaml> [file2.yaml ...]
    k8s_yaml_fmt.py --check <file.yaml>    # Check only, exit 1 if changes needed
    k8s_yaml_fmt.py --diff <file.yaml>     # Show diff without modifying

Configuration:
    Create .k8s-yaml-fmt.yaml in your project root:

    additional_kinds:
      MyCustomResource:
        - field1
        - field2
"""

import argparse
import difflib
import sys
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Optional

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError, YAMLStreamError

# Config file name
CONFIG_FILE_NAME = ".k8s-yaml-fmt.yaml"


@dataclass
class Config:
    """Configuration for the formatter."""

    # Custom resource kinds with their spec field ordering
    additional_kinds: dict = field(default_factory=dict)

    # Formatting options
    indent: int = 2  # Mapping indent
    sequence_indent: int = 2  # Sequence indent
    sequence_offset: int = 0  # Offset for sequence items (0 or 2 common)
    line_width: int = 4096  # Max line width before wrapping (high = no wrap)

    def get_spec_order(self, kind: str) -> list:
        """Get spec order for a kind, checking additional_kinds first."""
        if kind in self.additional_kinds:
            return self.additional_kinds[kind]
        return SPEC_ORDERS.get(kind, [])

    def is_supported_kind(self, kind: str) -> bool:
        """Check if a kind is supported (built-in or additional)."""
        return kind in SPEC_ORDERS or kind in self.additional_kinds


def find_config_file(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find config file by searching:
    1. Current directory (or start_path)
    2. Parent directories up to git root or filesystem root
    3. Home directory
    """
    search_path = start_path or Path.cwd()

    # Search current and parent directories
    current = search_path.resolve()
    while current != current.parent:
        config_path = current / CONFIG_FILE_NAME
        if config_path.exists():
            return config_path
        # Stop at git root
        if (current / ".git").exists():
            break
        current = current.parent

    # Check home directory
    home_config = Path.home() / CONFIG_FILE_NAME
    if home_config.exists():
        return home_config

    return None


def _validated_int(data: dict, key: str, default: int, min_val: int = 1) -> int:
    """Get an integer config value with validation, returning default if invalid."""
    value = data.get(key, default)
    return value if isinstance(value, int) and value >= min_val else default


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from file or return defaults."""
    if config_path is None:
        config_path = find_config_file()

    if config_path is None or not config_path.exists():
        return Config()

    try:
        yaml = YAML()
        with open(config_path) as f:
            data = yaml.load(f)

        if data is None:
            return Config()

        # Parse additional_kinds
        additional_kinds = {}
        if "additional_kinds" in data and isinstance(data["additional_kinds"], dict):
            for kind, fields in data["additional_kinds"].items():
                if isinstance(fields, list):
                    additional_kinds[kind] = fields

        return Config(
            additional_kinds=additional_kinds,
            indent=_validated_int(data, "indent", 2),
            sequence_indent=_validated_int(data, "sequence_indent", 2),
            sequence_offset=_validated_int(data, "sequence_offset", 0, min_val=0),
            line_width=_validated_int(data, "line_width", 4096),
        )

    except Exception as e:
        print(f"Warning: Failed to load config from {config_path}: {e}", file=sys.stderr)
        return Config()

# Key ordering definitions
TOP_LEVEL_ORDER = [
    "apiVersion",
    "kind",
    "metadata",
    "spec",
    "data",
    "stringData",
    "type",
    "immutable",
    "rules",
    "subjects",
    "roleRef",
    "webhooks",
    "status",
]

METADATA_ORDER = [
    "name",
    "namespace",
    "labels",
    "annotations",
    "ownerReferences",
    "finalizers",
]

# Spec orderings per kind
SPEC_ORDERS = {
    "Deployment": [
        "replicas",
        "selector",
        "strategy",
        "minReadySeconds",
        "revisionHistoryLimit",
        "progressDeadlineSeconds",
        "paused",
        "template",
    ],
    "Service": [
        "type",
        "selector",
        "ports",
        "clusterIP",
        "clusterIPs",
        "externalIPs",
        "externalName",
        "externalTrafficPolicy",
        "internalTrafficPolicy",
        "loadBalancerIP",
        "loadBalancerSourceRanges",
        "loadBalancerClass",
        "sessionAffinity",
        "sessionAffinityConfig",
        "ipFamilies",
        "ipFamilyPolicy",
    ],
    "Ingress": [
        "ingressClassName",
        "defaultBackend",
        "tls",
        "rules",
    ],
    "Pod": [
        "serviceAccountName",
        "serviceAccount",
        "automountServiceAccountToken",
        "nodeName",
        "nodeSelector",
        "affinity",
        "tolerations",
        "schedulerName",
        "priorityClassName",
        "priority",
        "securityContext",
        "hostNetwork",
        "hostPID",
        "hostIPC",
        "hostname",
        "subdomain",
        "dnsPolicy",
        "dnsConfig",
        "restartPolicy",
        "terminationGracePeriodSeconds",
        "activeDeadlineSeconds",
        "initContainers",
        "containers",
        "volumes",
        "imagePullSecrets",
    ],
    "StatefulSet": [
        "replicas",
        "selector",
        "serviceName",
        "podManagementPolicy",
        "updateStrategy",
        "revisionHistoryLimit",
        "minReadySeconds",
        "persistentVolumeClaimRetentionPolicy",
        "template",
        "volumeClaimTemplates",
    ],
    "DaemonSet": [
        "selector",
        "updateStrategy",
        "minReadySeconds",
        "revisionHistoryLimit",
        "template",
    ],
    "Job": [
        "parallelism",
        "completions",
        "completionMode",
        "backoffLimit",
        "activeDeadlineSeconds",
        "ttlSecondsAfterFinished",
        "suspend",
        "selector",
        "manualSelector",
        "template",
    ],
    "CronJob": [
        "schedule",
        "timeZone",
        "startingDeadlineSeconds",
        "concurrencyPolicy",
        "suspend",
        "successfulJobsHistoryLimit",
        "failedJobsHistoryLimit",
        "jobTemplate",
    ],
    "PersistentVolumeClaim": [
        "accessModes",
        "selector",
        "resources",
        "volumeName",
        "storageClassName",
        "volumeMode",
        "dataSource",
        "dataSourceRef",
    ],
    "PersistentVolume": [
        "capacity",
        "accessModes",
        "persistentVolumeReclaimPolicy",
        "storageClassName",
        "volumeMode",
        "mountOptions",
        "nodeAffinity",
    ],
    "ServiceAccount": [
        "secrets",
        "imagePullSecrets",
        "automountServiceAccountToken",
    ],
    "HorizontalPodAutoscaler": [
        "scaleTargetRef",
        "minReplicas",
        "maxReplicas",
        "metrics",
        "behavior",
    ],
    "NetworkPolicy": [
        "podSelector",
        "policyTypes",
        "ingress",
        "egress",
    ],
    "ReplicaSet": [
        "replicas",
        "selector",
        "minReadySeconds",
        "template",
    ],
    "PodDisruptionBudget": [
        "selector",
        "minAvailable",
        "maxUnavailable",
    ],
    # RBAC resources (no spec, but recognized for rules/subjects/roleRef formatting)
    "Role": [],
    "ClusterRole": [],
    "RoleBinding": [],
    "ClusterRoleBinding": [],
}

CONTAINER_ORDER = [
    "name",
    "image",
    "imagePullPolicy",
    "command",
    "args",
    "workingDir",
    "ports",
    "envFrom",
    "env",
    "resources",
    "volumeMounts",
    "volumeDevices",
    "livenessProbe",
    "readinessProbe",
    "startupProbe",
    "lifecycle",
    "securityContext",
    "stdin",
    "stdinOnce",
    "tty",
    "terminationMessagePath",
    "terminationMessagePolicy",
]

RESOURCES_ORDER = ["requests", "limits"]

PROBE_ORDER = [
    "httpGet",
    "tcpSocket",
    "exec",
    "grpc",
    "initialDelaySeconds",
    "periodSeconds",
    "timeoutSeconds",
    "successThreshold",
    "failureThreshold",
    "terminationGracePeriodSeconds",
]

HTTP_GET_ORDER = ["path", "port", "host", "scheme", "httpHeaders"]

PORT_ORDER = [
    "name",
    "containerPort",
    "hostPort",
    "protocol",
    "port",
    "targetPort",
    "nodePort",
]

ENV_ORDER = ["name", "value", "valueFrom"]

VOLUME_MOUNT_ORDER = [
    "name",
    "mountPath",
    "subPath",
    "subPathExpr",
    "readOnly",
    "mountPropagation",
]

VOLUME_ORDER = [
    "name",
    "configMap",
    "secret",
    "persistentVolumeClaim",
    "emptyDir",
    "hostPath",
    "projected",
    "downwardAPI",
    "nfs",
    "csi",
]

INGRESS_RULE_ORDER = ["host", "http"]
INGRESS_PATH_ORDER = ["path", "pathType", "backend"]
INGRESS_TLS_ORDER = ["hosts", "secretName"]

SELECTOR_ORDER = ["matchLabels", "matchExpressions"]

SERVICE_PORT_ORDER = ["name", "port", "targetPort", "protocol", "nodePort", "appProtocol"]

# RBAC ordering
RBAC_RULE_ORDER = [
    "apiGroups",
    "resources",
    "resourceNames",
    "verbs",
    "nonResourceURLs",
]

SUBJECT_ORDER = [
    "kind",
    "apiGroup",
    "name",
    "namespace",
]

ROLE_REF_ORDER = [
    "kind",
    "apiGroup",
    "name",
]


def copy_yaml_comments(source, dest, key_type: str = "map"):
    """
    Copy ruamel.yaml comments from source to dest.

    Args:
        source: Source CommentedMap or CommentedSeq
        dest: Destination CommentedMap or CommentedSeq
        key_type: "map" for dict keys, "seq" for list indices
    """
    if hasattr(source, "ca") and source.ca:
        dest.ca.comment = source.ca.comment
        if key_type == "map":
            for key in dest:
                if key in source.ca.items:
                    dest.ca.items[key] = source.ca.items[key]
        else:  # seq
            for idx in source.ca.items:
                if idx < len(dest):
                    dest.ca.items[idx] = source.ca.items[idx]
        if hasattr(source.ca, "end") and source.ca.end:
            dest.ca.end = source.ca.end


def sort_map(data: CommentedMap, key_order: list) -> CommentedMap:
    """Sort a CommentedMap according to key_order, preserving comments."""
    if not isinstance(data, CommentedMap):
        return data

    result = CommentedMap()

    # First add keys in specified order
    for key in key_order:
        if key in data:
            result[key] = data[key]

    # Then add remaining keys in original order (not alphabetically, to preserve intent)
    for key in data.keys():
        if key not in result:
            result[key] = data[key]

    copy_yaml_comments(data, result, key_type="map")
    return result


def format_list(items: CommentedSeq, item_formatter) -> CommentedSeq:
    """Format each item in a list."""
    if not isinstance(items, (list, CommentedSeq)):
        return items

    result = CommentedSeq()
    for item in items:
        if isinstance(item, CommentedMap):
            result.append(item_formatter(item))
        else:
            result.append(item)

    copy_yaml_comments(items, result, key_type="seq")
    return result


def _format_list_field(obj: CommentedMap, key: str, order: list):
    """Format a list field in-place if present and non-empty."""
    if key in obj and obj[key]:
        obj[key] = format_list(obj[key], lambda item: sort_map(item, order))


def format_container(container: CommentedMap) -> CommentedMap:
    """Format a container spec. Caller must ensure container is a CommentedMap."""
    container = sort_map(container, CONTAINER_ORDER)

    _format_list_field(container, "ports", PORT_ORDER)
    _format_list_field(container, "env", ENV_ORDER)
    _format_list_field(container, "volumeMounts", VOLUME_MOUNT_ORDER)

    if "resources" in container:
        container["resources"] = sort_map(container["resources"], RESOURCES_ORDER)

    for probe_key in ["livenessProbe", "readinessProbe", "startupProbe"]:
        if probe_key in container and container[probe_key]:
            container[probe_key] = sort_map(container[probe_key], PROBE_ORDER)
            if "httpGet" in container[probe_key]:
                container[probe_key]["httpGet"] = sort_map(container[probe_key]["httpGet"], HTTP_GET_ORDER)

    return container


def format_pod_spec(spec: CommentedMap) -> CommentedMap:
    """Format a pod spec (used in Pod, Deployment.spec.template.spec, etc.)."""
    if not isinstance(spec, CommentedMap):
        return spec

    spec = sort_map(spec, SPEC_ORDERS["Pod"])

    for container_key in ["initContainers", "containers"]:
        if container_key in spec and spec[container_key]:
            spec[container_key] = format_list(spec[container_key], format_container)

    _format_list_field(spec, "volumes", VOLUME_ORDER)

    return spec


def format_selector(selector: CommentedMap) -> CommentedMap:
    """Format a selector. Caller must ensure selector is a CommentedMap."""
    return sort_map(selector, SELECTOR_ORDER)


def format_ingress_rules(rules) -> CommentedSeq:
    """Format Ingress rules."""

    def format_rule(rule):
        if not isinstance(rule, CommentedMap):
            return rule
        rule = sort_map(rule, INGRESS_RULE_ORDER)
        if "http" in rule and isinstance(rule["http"], CommentedMap):
            if "paths" in rule["http"]:
                rule["http"]["paths"] = format_list(rule["http"]["paths"], lambda p: sort_map(p, INGRESS_PATH_ORDER))
        return rule

    return format_list(rules, format_rule)


def format_ingress_tls(tls) -> CommentedSeq:
    """Format Ingress TLS entries."""
    return format_list(tls, lambda t: sort_map(t, INGRESS_TLS_ORDER))


def format_template(template: CommentedMap, spec_formatter) -> CommentedMap:
    """
    Format a template (used in Deployment.spec.template, CronJob.spec.jobTemplate, etc.).
    Caller must ensure template is a CommentedMap.

    Args:
        template: The template CommentedMap to format
        spec_formatter: Callable to format the nested spec (e.g., format_pod_spec or format_spec)
    """
    if "metadata" in template:
        template["metadata"] = sort_map(template["metadata"], METADATA_ORDER)
    if "spec" in template:
        template["spec"] = spec_formatter(template["spec"])

    return sort_map(template, ["metadata", "spec"])


def format_spec(spec: CommentedMap, kind: str, config: Optional[Config] = None) -> CommentedMap:
    """Format spec section based on resource kind."""
    if not isinstance(spec, CommentedMap):
        return spec

    spec_order = config.get_spec_order(kind) if config else SPEC_ORDERS.get(kind, [])
    spec = sort_map(spec, spec_order)

    # Format selector if present
    if "selector" in spec and isinstance(spec["selector"], CommentedMap):
        spec["selector"] = format_selector(spec["selector"])

    # Format template.spec for workload resources
    if "template" in spec and isinstance(spec["template"], CommentedMap):
        spec["template"] = format_template(spec["template"], format_pod_spec)

    # Format jobTemplate for CronJob
    if "jobTemplate" in spec and isinstance(spec["jobTemplate"], CommentedMap):
        spec["jobTemplate"] = format_template(
            spec["jobTemplate"],
            lambda s: format_spec(s, "Job", config),
        )

    # Format Ingress specifics
    if kind == "Ingress":
        if "rules" in spec and spec["rules"]:
            spec["rules"] = format_ingress_rules(spec["rules"])
        if "tls" in spec and spec["tls"]:
            spec["tls"] = format_ingress_tls(spec["tls"])

    # Format Service ports
    if kind == "Service" and "ports" in spec and spec["ports"]:
        spec["ports"] = format_list(spec["ports"], lambda p: sort_map(p, SERVICE_PORT_ORDER))

    return spec


def is_sops_encrypted(doc: CommentedMap) -> bool:
    """Check if document is SOPS-encrypted (has 'sops' metadata block)."""
    return (
        isinstance(doc, CommentedMap)
        and "sops" in doc
        and isinstance(doc.get("sops"), CommentedMap)
    )


def is_k8s_manifest(doc: CommentedMap, config: Optional[Config] = None) -> bool:
    """
    Check if document is a supported Kubernetes manifest.
    Requirements:
    - apiVersion exists and is a string
    - kind exists and is a supported type (built-in or from config)
    """
    if not isinstance(doc, CommentedMap):
        return False

    api_version = doc.get("apiVersion")
    kind = doc.get("kind")

    # apiVersion must be a string
    if not isinstance(api_version, str):
        return False

    # kind must be a supported type
    if not isinstance(kind, str):
        return False

    if config:
        return config.is_supported_kind(kind)
    return kind in SPEC_ORDERS


def format_document(doc: CommentedMap, config: Optional[Config] = None) -> CommentedMap:
    """Format a single K8s document."""
    if not isinstance(doc, CommentedMap):
        return doc

    # Skip SOPS-encrypted documents
    if is_sops_encrypted(doc):
        return doc

    # Skip non-K8s documents
    if not is_k8s_manifest(doc, config):
        return doc

    kind = doc.get("kind", "")

    # Sort top-level keys
    doc = sort_map(doc, TOP_LEVEL_ORDER)

    # Format metadata
    if "metadata" in doc and isinstance(doc["metadata"], CommentedMap):
        doc["metadata"] = sort_map(doc["metadata"], METADATA_ORDER)

    # Format spec
    if "spec" in doc and isinstance(doc["spec"], CommentedMap):
        doc["spec"] = format_spec(doc["spec"], kind, config)

    # Format RBAC resources (Role, ClusterRole, RoleBinding, ClusterRoleBinding)
    if kind in ("Role", "ClusterRole"):
        _format_list_field(doc, "rules", RBAC_RULE_ORDER)

    if kind in ("RoleBinding", "ClusterRoleBinding"):
        _format_list_field(doc, "subjects", SUBJECT_ORDER)
        if "roleRef" in doc and isinstance(doc["roleRef"], CommentedMap):
            doc["roleRef"] = sort_map(doc["roleRef"], ROLE_REF_ORDER)

    return doc


def format_yaml_content(content: str, config: Optional[Config] = None) -> tuple[str, bool]:
    """
    Format YAML content and return (formatted_string, has_k8s_manifests).
    Returns the original content unchanged if no K8s manifests are found.
    """
    # Use config formatting options or defaults
    indent = config.indent if config else 2
    sequence_indent = config.sequence_indent if config else 2
    sequence_offset = config.sequence_offset if config else 0
    line_width = config.line_width if config else 4096

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = line_width
    yaml.indent(mapping=indent, sequence=sequence_indent, offset=sequence_offset)

    # Parse all documents
    docs = list(yaml.load_all(content))

    if not docs:
        return content, False

    # Check if any document is a K8s manifest
    has_k8s_manifests = any(
        is_k8s_manifest(doc, config) and not is_sops_encrypted(doc) for doc in docs if doc is not None
    )

    if not has_k8s_manifests:
        return content, False

    # Format each document
    formatted_docs = []
    for doc in docs:
        if doc is not None:
            formatted_docs.append(format_document(doc, config))

    if not formatted_docs:
        return content, False

    # Serialize back to string
    output = StringIO()
    yaml.dump_all(formatted_docs, output)
    result = output.getvalue()

    # Ensure file ends with newline
    if result and not result.endswith("\n"):
        result += "\n"

    return result, True


def format_file(
    filepath: Path,
    check_only: bool = False,
    show_diff: bool = False,
    verbose: bool = False,
    config: Optional[Config] = None,
) -> bool:
    """
    Format a single file.

    Returns True if file was (or would be) modified.
    """
    try:
        original = filepath.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, UnicodeDecodeError, OSError) as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
        return False

    try:
        formatted, has_k8s = format_yaml_content(original, config)
    except (YAMLError, YAMLStreamError) as e:
        # Extract line/column info from ruamel.yaml errors
        error_msg = str(e)
        if hasattr(e, "problem_mark") and e.problem_mark:
            mark = e.problem_mark
            error_msg = f"line {mark.line + 1}, column {mark.column + 1}: {e.problem or 'syntax error'}"
            if hasattr(e, "context") and e.context:
                error_msg += f" ({e.context})"
        print(f"YAML error in {filepath}: {error_msg}", file=sys.stderr)
        return False
    except Exception as e:
        # Catch-all for unexpected errors (include type for debugging)
        print(f"Unexpected error processing {filepath} ({type(e).__name__}): {e}", file=sys.stderr)
        return False

    # Skip non-K8s files entirely
    if not has_k8s:
        if verbose:
            print(f"Skipped (not a K8s manifest): {filepath}")
        return False

    changed = original != formatted

    if show_diff and changed:
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            formatted.splitlines(keepends=True),
            fromfile=str(filepath),
            tofile=str(filepath),
        )
        sys.stdout.writelines(diff)

    if check_only:
        if changed:
            print(f"Would reformat: {filepath}")
        return changed

    if changed:
        try:
            filepath.write_text(formatted, encoding="utf-8")
            print(f"Reformatted: {filepath}")
        except (PermissionError, OSError) as e:
            print(f"Error writing {filepath}: {e}", file=sys.stderr)
            return False

    return changed


def main():
    parser = argparse.ArgumentParser(description="Format Kubernetes YAML files with idiomatic key ordering.")
    parser.add_argument("files", nargs="*", type=Path, help="YAML files to format")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if files need formatting (exit 1 if changes needed)",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Show diff without modifying files",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show skipped files (non-K8s, SOPS-encrypted)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config file (default: auto-discover .k8s-yaml-fmt.yaml)",
    )

    args = parser.parse_args()

    if not args.files:
        parser.print_help()
        sys.exit(0)

    # Load configuration
    config = load_config(args.config)
    if args.verbose and config.additional_kinds:
        print(f"Loaded {len(config.additional_kinds)} additional kind(s) from config")

    any_changed = False
    any_error = False

    for filepath in args.files:
        if not filepath.exists():
            print(f"File not found: {filepath}", file=sys.stderr)
            any_error = True
            continue

        if filepath.suffix.lower() not in (".yaml", ".yml"):
            continue

        try:
            changed = format_file(
                filepath,
                check_only=args.check or args.diff,
                show_diff=args.diff,
                verbose=args.verbose,
                config=config,
            )
            any_changed = any_changed or changed
        except Exception as e:
            print(f"Error processing {filepath}: {e}", file=sys.stderr)
            any_error = True

    if any_error:
        sys.exit(2)

    if (args.check or args.diff) and any_changed:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
