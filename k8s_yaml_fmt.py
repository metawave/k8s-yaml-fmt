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
"""

import sys
import argparse
from pathlib import Path
from io import StringIO
import difflib

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

# Key ordering definitions
TOP_LEVEL_ORDER = [
    "apiVersion",
    "kind",
    "metadata",
    "spec",
    "data",
    "stringData",
    "binaryData",
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
    "ConfigMap": [],
    "Secret": [],
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
    "Role": [],
    "ClusterRole": [],
    "RoleBinding": [],
    "ClusterRoleBinding": [],
    "Namespace": [],
    "ReplicaSet": [
        "replicas",
        "selector",
        "minReadySeconds",
        "template",
    ],
    "Endpoints": [],
    "ResourceQuota": [],
    "LimitRange": [],
    "PodDisruptionBudget": [
        "selector",
        "minAvailable",
        "maxUnavailable",
    ],
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

POD_TEMPLATE_SPEC_ORDER = SPEC_ORDERS["Pod"]

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

    # Preserve comments
    if hasattr(data, "ca") and data.ca:
        result.ca.comment = data.ca.comment
        for key in result:
            if key in data.ca.items:
                result.ca.items[key] = data.ca.items[key]

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

    # Preserve comments
    if hasattr(items, "ca") and items.ca:
        result.ca.comment = items.ca.comment
        for idx in items.ca.items:
            if idx < len(result):
                result.ca.items[idx] = items.ca.items[idx]

    return result


def format_container(container: CommentedMap) -> CommentedMap:
    """Format a container spec."""
    if not isinstance(container, CommentedMap):
        return container

    container = sort_map(container, CONTAINER_ORDER)

    if "ports" in container and container["ports"]:
        container["ports"] = format_list(
            container["ports"], lambda p: sort_map(p, PORT_ORDER)
        )

    if "env" in container and container["env"]:
        container["env"] = format_list(
            container["env"], lambda e: sort_map(e, ENV_ORDER)
        )

    if "volumeMounts" in container and container["volumeMounts"]:
        container["volumeMounts"] = format_list(
            container["volumeMounts"], lambda vm: sort_map(vm, VOLUME_MOUNT_ORDER)
        )

    if "resources" in container:
        container["resources"] = sort_map(container["resources"], RESOURCES_ORDER)

    for probe_key in ["livenessProbe", "readinessProbe", "startupProbe"]:
        if probe_key in container and container[probe_key]:
            container[probe_key] = sort_map(container[probe_key], PROBE_ORDER)
            if "httpGet" in container[probe_key]:
                container[probe_key]["httpGet"] = sort_map(
                    container[probe_key]["httpGet"], HTTP_GET_ORDER
                )

    return container


def format_pod_spec(spec: CommentedMap) -> CommentedMap:
    """Format a pod spec (used in Pod, Deployment.spec.template.spec, etc.)."""
    if not isinstance(spec, CommentedMap):
        return spec

    spec = sort_map(spec, POD_TEMPLATE_SPEC_ORDER)

    for container_key in ["initContainers", "containers"]:
        if container_key in spec and spec[container_key]:
            spec[container_key] = format_list(spec[container_key], format_container)

    if "volumes" in spec and spec["volumes"]:
        spec["volumes"] = format_list(
            spec["volumes"], lambda v: sort_map(v, VOLUME_ORDER)
        )

    return spec


def format_selector(selector: CommentedMap) -> CommentedMap:
    """Format a selector."""
    if not isinstance(selector, CommentedMap):
        return selector
    return sort_map(selector, SELECTOR_ORDER)


def format_ingress_rules(rules) -> CommentedSeq:
    """Format Ingress rules."""
    def format_rule(rule):
        if not isinstance(rule, CommentedMap):
            return rule
        rule = sort_map(rule, INGRESS_RULE_ORDER)
        if "http" in rule and isinstance(rule["http"], CommentedMap):
            if "paths" in rule["http"]:
                rule["http"]["paths"] = format_list(
                    rule["http"]["paths"],
                    lambda p: sort_map(p, INGRESS_PATH_ORDER)
                )
        return rule

    return format_list(rules, format_rule)


def format_ingress_tls(tls) -> CommentedSeq:
    """Format Ingress TLS entries."""
    return format_list(tls, lambda t: sort_map(t, INGRESS_TLS_ORDER))


def format_spec(spec: CommentedMap, kind: str) -> CommentedMap:
    """Format spec section based on resource kind."""
    if not isinstance(spec, CommentedMap):
        return spec

    spec_order = SPEC_ORDERS.get(kind, [])
    spec = sort_map(spec, spec_order)

    # Format selector if present
    if "selector" in spec and isinstance(spec["selector"], CommentedMap):
        spec["selector"] = format_selector(spec["selector"])

    # Format template.spec for workload resources
    if "template" in spec and isinstance(spec["template"], CommentedMap):
        template = spec["template"]
        if "metadata" in template:
            template["metadata"] = sort_map(template["metadata"], METADATA_ORDER)
        if "spec" in template:
            template["spec"] = format_pod_spec(template["spec"])
        spec["template"] = sort_map(template, ["metadata", "spec"])

    # Format jobTemplate for CronJob
    if "jobTemplate" in spec and isinstance(spec["jobTemplate"], CommentedMap):
        job_template = spec["jobTemplate"]
        if "metadata" in job_template:
            job_template["metadata"] = sort_map(job_template["metadata"], METADATA_ORDER)
        if "spec" in job_template:
            job_template["spec"] = format_spec(job_template["spec"], "Job")
        spec["jobTemplate"] = sort_map(job_template, ["metadata", "spec"])

    # Format Ingress specifics
    if kind == "Ingress":
        if "rules" in spec and spec["rules"]:
            spec["rules"] = format_ingress_rules(spec["rules"])
        if "tls" in spec and spec["tls"]:
            spec["tls"] = format_ingress_tls(spec["tls"])

    # Format Service ports
    if kind == "Service" and "ports" in spec and spec["ports"]:
        spec["ports"] = format_list(
            spec["ports"], lambda p: sort_map(p, SERVICE_PORT_ORDER)
        )

    return spec


def is_sops_encrypted(doc: CommentedMap) -> bool:
    """Check if document is SOPS-encrypted (has 'sops' metadata block)."""
    if not isinstance(doc, CommentedMap):
        return False
    if "sops" in doc:
        sops_block = doc["sops"]
        # Verify it's a real SOPS block (has typical fields)
        if isinstance(sops_block, CommentedMap):
            return any(key in sops_block for key in ["kms", "gcp_kms", "azure_kv", "age", "pgp", "mac", "version"])
    return False


# Supported Kubernetes resource kinds
SUPPORTED_KINDS = set(SPEC_ORDERS.keys())


def is_k8s_manifest(doc: CommentedMap) -> bool:
    """
    Check if document is a supported Kubernetes manifest.
    
    Requirements:
    - apiVersion exists and is a string
    - kind exists and is a supported type (in SPEC_ORDERS)
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
    
    return kind in SUPPORTED_KINDS


def format_document(doc: CommentedMap) -> CommentedMap:
    """Format a single K8s document."""
    if not isinstance(doc, CommentedMap):
        return doc

    # Skip SOPS-encrypted documents
    if is_sops_encrypted(doc):
        return doc

    # Skip non-K8s documents
    if not is_k8s_manifest(doc):
        return doc

    kind = doc.get("kind", "")

    # Sort top-level keys
    doc = sort_map(doc, TOP_LEVEL_ORDER)

    # Format metadata
    if "metadata" in doc and isinstance(doc["metadata"], CommentedMap):
        doc["metadata"] = sort_map(doc["metadata"], METADATA_ORDER)

    # Format spec
    if "spec" in doc and isinstance(doc["spec"], CommentedMap):
        doc["spec"] = format_spec(doc["spec"], kind)

    return doc


def format_yaml_content(content: str) -> tuple[str, bool]:
    """
    Format YAML content and return (formatted_string, has_k8s_manifests).
    
    Returns the original content unchanged if no K8s manifests are found.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096  # Prevent line wrapping
    yaml.indent(mapping=2, sequence=2, offset=0)

    # Parse all documents
    docs = list(yaml.load_all(content))

    if not docs:
        return content, False

    # Check if any document is a K8s manifest
    has_k8s_manifests = any(
        is_k8s_manifest(doc) and not is_sops_encrypted(doc)
        for doc in docs
        if doc is not None
    )
    
    if not has_k8s_manifests:
        return content, False

    # Format each document
    formatted_docs = []
    for doc in docs:
        if doc is not None:
            formatted_docs.append(format_document(doc))

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


def format_file(filepath: Path, check_only: bool = False, show_diff: bool = False, verbose: bool = False) -> bool:
    """
    Format a single file.

    Returns True if file was (or would be) modified.
    """
    try:
        original = filepath.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
        return False

    try:
        formatted, has_k8s = format_yaml_content(original)
    except Exception as e:
        print(f"Error parsing {filepath}: {e}", file=sys.stderr)
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
        except Exception as e:
            print(f"Error writing {filepath}: {e}", file=sys.stderr)
            return False

    return changed


def main():
    parser = argparse.ArgumentParser(
        description="Format Kubernetes YAML files with idiomatic key ordering."
    )
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
        "-v", "--verbose",
        action="store_true",
        help="Show skipped files (non-K8s, SOPS-encrypted)",
    )

    args = parser.parse_args()

    if not args.files:
        parser.print_help()
        sys.exit(0)

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
