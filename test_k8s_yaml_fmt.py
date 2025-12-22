"""Tests for k8s-yaml-fmt."""

import pytest
from k8s_yaml_fmt import format_yaml_content, is_k8s_manifest, is_sops_encrypted, SUPPORTED_KINDS
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


def parse_yaml(content: str) -> CommentedMap:
    """Helper to parse YAML string."""
    yaml = YAML()
    return yaml.load(content)


class TestIsKubernetesManifest:
    """Tests for K8s manifest detection."""

    def test_valid_deployment(self):
        doc = parse_yaml("""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test
""")
        assert is_k8s_manifest(doc) is True

    def test_valid_service(self):
        doc = parse_yaml("""
apiVersion: v1
kind: Service
metadata:
  name: test
""")
        assert is_k8s_manifest(doc) is True

    def test_unsupported_kind(self):
        doc = parse_yaml("""
apiVersion: custom.io/v1
kind: MyCustomResource
metadata:
  name: test
""")
        assert is_k8s_manifest(doc) is False

    def test_docker_compose(self):
        doc = parse_yaml("""
version: "3.8"
services:
  web:
    image: nginx
""")
        assert is_k8s_manifest(doc) is False

    def test_github_actions(self):
        doc = parse_yaml("""
name: CI
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
""")
        assert is_k8s_manifest(doc) is False

    def test_missing_api_version(self):
        doc = parse_yaml("""
kind: Deployment
metadata:
  name: test
""")
        assert is_k8s_manifest(doc) is False

    def test_missing_kind(self):
        doc = parse_yaml("""
apiVersion: apps/v1
metadata:
  name: test
""")
        assert is_k8s_manifest(doc) is False


class TestSopsDetection:
    """Tests for SOPS encrypted file detection."""

    def test_sops_encrypted(self):
        doc = parse_yaml("""
apiVersion: v1
kind: Secret
metadata:
  name: test
sops:
  age:
    - recipient: age1abc
  mac: ENC[AES256_GCM,data:abc]
  version: 3.8.1
""")
        assert is_sops_encrypted(doc) is True

    def test_not_sops_encrypted(self):
        doc = parse_yaml("""
apiVersion: v1
kind: Secret
metadata:
  name: test
data:
  password: cGFzc3dvcmQ=
""")
        assert is_sops_encrypted(doc) is False


class TestFormatting:
    """Tests for YAML formatting."""

    def test_top_level_ordering(self):
        content = """
kind: Deployment
metadata:
  name: test
apiVersion: apps/v1
spec:
  replicas: 1
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        lines = formatted.strip().split('\n')
        assert lines[0] == "apiVersion: apps/v1"
        assert lines[1] == "kind: Deployment"

    def test_metadata_ordering(self):
        content = """
apiVersion: apps/v1
kind: Deployment
metadata:
  labels:
    app: test
  namespace: default
  name: test
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # name should come before namespace, namespace before labels
        name_pos = formatted.find("name: test")
        namespace_pos = formatted.find("namespace: default")
        labels_pos = formatted.find("labels:")
        assert name_pos < namespace_pos < labels_pos

    def test_skip_non_k8s(self):
        content = """
version: "3.8"
services:
  web:
    image: nginx
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is False
        assert formatted == content

    def test_skip_sops(self):
        content = """
apiVersion: v1
kind: Secret
metadata:
  name: test
sops:
  mac: ENC[AES256]
  version: 3.8.1
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is False


class TestSupportedKinds:
    """Tests for supported resource kinds."""

    def test_common_kinds_supported(self):
        expected = [
            "Deployment", "StatefulSet", "DaemonSet", "Service", "Ingress",
            "ConfigMap", "Secret", "Pod", "Job", "CronJob", "Namespace",
            "ServiceAccount", "Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding",
        ]
        for kind in expected:
            assert kind in SUPPORTED_KINDS, f"{kind} should be supported"

    def test_kind_count(self):
        # Ensure we have a reasonable number of kinds
        assert len(SUPPORTED_KINDS) >= 20
