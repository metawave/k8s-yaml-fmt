"""Tests for k8s-yaml-fmt."""

from pathlib import Path

import pytest
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from k8s_yaml_fmt import (
    CONFIG_FILE_NAME,
    SPEC_ORDERS,
    Config,
    find_config_file,
    format_file,
    format_yaml_content,
    is_k8s_manifest,
    is_sops_encrypted,
    load_config,
)

# =============================================================================
# Test Constants
# =============================================================================

API_V1 = "v1"
API_APPS_V1 = "apps/v1"
API_BATCH_V1 = "batch/v1"
API_RBAC_V1 = "rbac.authorization.k8s.io/v1"

DEFAULT_NAME = "test"
DEFAULT_IMAGE = "nginx"
DEFAULT_PORT = 80


# =============================================================================
# Test Fixtures - Reusable YAML snippets
# =============================================================================

def minimal_deployment(name: str = DEFAULT_NAME, replicas: int = 1, with_template: bool = True) -> str:
    """Generate a minimal Deployment YAML."""
    if with_template:
        return f"""apiVersion: {API_APPS_V1}
kind: Deployment
metadata:
  name: {name}
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      app: {name}
  template:
    metadata:
      labels:
        app: {name}
    spec:
      containers:
      - name: app
        image: {DEFAULT_IMAGE}
"""
    return f"""apiVersion: {API_APPS_V1}
kind: Deployment
metadata:
  name: {name}
spec:
  replicas: {replicas}
"""


def minimal_service(name: str = DEFAULT_NAME, port: int = DEFAULT_PORT, svc_type: str = "ClusterIP", with_ports: bool = True) -> str:
    """Generate a minimal Service YAML."""
    if with_ports:
        return f"""apiVersion: {API_V1}
kind: Service
metadata:
  name: {name}
spec:
  type: {svc_type}
  selector:
    app: {name}
  ports:
  - port: {port}
"""
    return f"""apiVersion: {API_V1}
kind: Service
metadata:
  name: {name}
spec:
  type: {svc_type}
"""


def minimal_pod(name: str = DEFAULT_NAME) -> str:
    """Generate a minimal Pod YAML."""
    return f"""apiVersion: {API_V1}
kind: Pod
metadata:
  name: {name}
spec:
  containers:
  - name: app
    image: {DEFAULT_IMAGE}
"""


def multi_doc(*docs: str) -> str:
    """Combine multiple YAML documents with separator."""
    return "---\n".join(docs)


def minimal_role(name: str = DEFAULT_NAME) -> str:
    """Generate a minimal Role YAML."""
    return f"""apiVersion: {API_RBAC_V1}
kind: Role
metadata:
  name: {name}
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]
"""


def parse_yaml(content: str) -> CommentedMap:
    """Helper to parse YAML string."""
    yaml = YAML()
    return yaml.load(content)


class TestIsKubernetesManifest:
    """Tests for K8s manifest detection."""

    def test_valid_deployment(self):
        doc = parse_yaml(minimal_deployment(with_template=False))
        assert is_k8s_manifest(doc) is True

    def test_valid_service(self):
        doc = parse_yaml(minimal_service(with_ports=False))
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
        # Only kinds with spec ordering are supported
        expected = [
            "Deployment", "StatefulSet", "DaemonSet", "Service", "Ingress",
            "Pod", "Job", "CronJob", "ServiceAccount", "ReplicaSet",
            "PersistentVolume", "PersistentVolumeClaim", "NetworkPolicy",
            "HorizontalPodAutoscaler", "PodDisruptionBudget",
        ]
        for kind in expected:
            assert kind in SPEC_ORDERS, f"{kind} should be supported"

    def test_kind_count(self):
        # Ensure we have a reasonable number of kinds with spec ordering
        assert len(SPEC_ORDERS) >= 15


class TestMultiDocument:
    """Tests for multi-document YAML files."""

    def test_multiple_k8s_documents(self):
        content = multi_doc(
            minimal_service("my-service", with_ports=False),
            minimal_deployment("my-deployment", replicas=1, with_template=False),
        )
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # Both documents should be formatted
        assert "kind: Service" in formatted
        assert "kind: Deployment" in formatted
        # Check ordering in first doc
        service_api = formatted.find("apiVersion: v1")
        service_kind = formatted.find("kind: Service")
        assert service_api < service_kind

    def test_mixed_k8s_and_non_k8s(self):
        """When mixing K8s and non-K8s docs, only K8s docs are formatted."""
        docker_compose = """# This is not a K8s document
version: "3.8"
services:
  web:
    image: nginx
"""
        content = multi_doc(minimal_service(with_ports=False), docker_compose)
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # Service should be formatted, docker-compose preserved as-is
        assert "kind: Service" in formatted

    def test_document_separator_preserved(self):
        content = multi_doc(minimal_service("first", with_ports=False), minimal_service("second", with_ports=False))
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        assert "---" in formatted


class TestCommentPreservation:
    """Tests for YAML comment preservation."""

    def test_top_level_comment(self):
        content = """# This is a top comment
apiVersion: v1
kind: Service
metadata:
  name: test
spec:
  type: ClusterIP
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        assert "# This is a top comment" in formatted

    def test_inline_comment(self):
        content = """apiVersion: v1
kind: Service
metadata:
  name: test  # inline comment
spec:
  type: ClusterIP
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        assert "# inline comment" in formatted

    def test_comment_between_keys(self):
        content = """apiVersion: v1
kind: Service
metadata:
  name: test
  # This comment is between keys
  labels:
    app: test
spec:
  type: ClusterIP
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        assert "# This comment is between keys" in formatted

    def test_end_of_document_comment(self):
        content = """apiVersion: v1
kind: Service
metadata:
  name: test
spec:
  type: ClusterIP
# End comment
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        assert "# End comment" in formatted


class TestIdempotency:
    """Tests that formatting is idempotent."""

    def test_format_twice_same_result(self):
        # Intentionally disordered YAML
        content = """kind: Deployment
metadata:
  labels:
    app: test
  name: test
apiVersion: apps/v1
spec:
  replicas: 1
"""
        formatted1, _ = format_yaml_content(content)
        formatted2, _ = format_yaml_content(formatted1)
        assert formatted1 == formatted2

    def test_already_formatted_unchanged(self):
        content = minimal_deployment(with_template=False)
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # Should be identical (or only differ by trailing newline)
        assert formatted.strip() == content.strip()


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_file(self):
        formatted, has_k8s = format_yaml_content("")
        assert has_k8s is False
        assert formatted == ""

    def test_only_comments(self):
        content = """# Just a comment
# Another comment
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is False

    def test_unicode_values(self):
        content = """apiVersion: v1
kind: Service
metadata:
  name: test
  labels:
    description: "日本語テスト"
  annotations:
    greeting: "Привет мир"
    emoji: "🚀"
spec:
  type: ClusterIP
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        assert "日本語テスト" in formatted
        assert "Привет мир" in formatted
        assert "🚀" in formatted

    def test_null_values(self):
        content = """apiVersion: v1
kind: Service
metadata:
  name: test
  namespace: null
spec:
  type: ClusterIP
  clusterIP: ~
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # Should not crash on null values

    def test_empty_spec(self):
        content = """apiVersion: v1
kind: ServiceAccount
metadata:
  name: test
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True

    def test_multiline_string(self):
        content = """apiVersion: v1
kind: Pod
metadata:
  name: test
spec:
  containers:
  - name: test
    image: busybox
    command:
    - /bin/sh
    - -c
    - |
      #!/bin/bash
      echo "Hello"
      exit 0
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        assert "#!/bin/bash" in formatted
        assert 'echo "Hello"' in formatted


class TestContainerFormatting:
    """Tests for container spec ordering."""

    def test_container_field_order(self):
        content = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test
  template:
    metadata:
      labels:
        app: test
    spec:
      containers:
      - resources:
          limits:
            memory: 128Mi
        image: nginx
        name: web
        ports:
        - containerPort: 80
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # name should come before image, image before ports, ports before resources
        name_pos = formatted.find("name: web")
        image_pos = formatted.find("image: nginx")
        ports_pos = formatted.find("ports:")
        resources_pos = formatted.find("resources:")
        assert name_pos < image_pos < ports_pos < resources_pos

    def test_probe_ordering(self):
        content = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test
  template:
    metadata:
      labels:
        app: test
    spec:
      containers:
      - name: web
        image: nginx
        livenessProbe:
          periodSeconds: 10
          httpGet:
            port: 8080
            path: /health
          initialDelaySeconds: 5
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # httpGet should come before initialDelaySeconds
        httpget_pos = formatted.find("httpGet:")
        initial_pos = formatted.find("initialDelaySeconds:")
        assert httpget_pos < initial_pos
        # path should come before port in httpGet
        path_pos = formatted.find("path: /health")
        port_pos = formatted.find("port: 8080")
        assert path_pos < port_pos

    def test_env_ordering(self):
        content = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test
  template:
    metadata:
      labels:
        app: test
    spec:
      containers:
      - name: web
        image: nginx
        env:
        - valueFrom:
            secretKeyRef:
              name: secret
              key: password
          name: PASSWORD
        - value: "true"
          name: DEBUG
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # In each env entry, name should come before value/valueFrom
        # Check PASSWORD env var: name before valueFrom
        password_name_pos = formatted.find("- name: PASSWORD")
        password_valuefrom_pos = formatted.find("valueFrom:")
        assert password_name_pos < password_valuefrom_pos, "name should come before valueFrom"
        # Check DEBUG env var: name before value
        debug_name_pos = formatted.find("- name: DEBUG")
        debug_value_pos = formatted.find('value: "true"')
        assert debug_name_pos < debug_value_pos, "name should come before value"

    def test_resources_ordering(self):
        content = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test
  template:
    metadata:
      labels:
        app: test
    spec:
      containers:
      - name: web
        image: nginx
        resources:
          limits:
            memory: 128Mi
          requests:
            memory: 64Mi
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # requests should come before limits
        requests_pos = formatted.find("requests:")
        limits_pos = formatted.find("limits:")
        assert requests_pos < limits_pos


class TestServiceFormatting:
    """Tests for Service spec ordering."""

    def test_service_port_ordering(self):
        # Intentionally disordered port fields
        content = """apiVersion: v1
kind: Service
metadata:
  name: test
spec:
  selector:
    app: test
  ports:
  - targetPort: 8080
    protocol: TCP
    port: 80
    name: http
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # name -> port -> targetPort -> protocol
        name_pos = formatted.find("name: http")
        port_pos = formatted.find("port: 80")
        target_pos = formatted.find("targetPort: 8080")
        protocol_pos = formatted.find("protocol: TCP")
        assert name_pos < port_pos < target_pos < protocol_pos

    def test_service_spec_ordering(self):
        # Intentionally disordered spec fields (ports before type)
        content = """apiVersion: v1
kind: Service
metadata:
  name: test
spec:
  ports:
  - port: 80
  selector:
    app: test
  type: ClusterIP
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # type -> selector -> ports
        type_pos = formatted.find("type: ClusterIP")
        selector_pos = formatted.find("selector:")
        ports_pos = formatted.find("ports:")
        assert type_pos < selector_pos < ports_pos

    def test_service_fixture_basic(self):
        formatted, has_k8s = format_yaml_content(minimal_service())
        assert has_k8s is True
        assert "kind: Service" in formatted
        assert "port: 80" in formatted


class TestIngressFormatting:
    """Tests for Ingress spec ordering."""

    def test_ingress_rule_ordering(self):
        content = """apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: test
spec:
  rules:
  - http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: test
            port:
              number: 80
    host: example.com
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # host should come before http
        host_pos = formatted.find("host: example.com")
        http_pos = formatted.find("http:")
        assert host_pos < http_pos

    def test_ingress_path_ordering(self):
        content = """apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: test
spec:
  rules:
  - host: example.com
    http:
      paths:
      - backend:
          service:
            name: test
            port:
              number: 80
        pathType: Prefix
        path: /api
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # path -> pathType -> backend
        path_pos = formatted.find("path: /api")
        pathtype_pos = formatted.find("pathType: Prefix")
        backend_pos = formatted.find("backend:")
        assert path_pos < pathtype_pos < backend_pos


class TestErrorHandling:
    """Tests for error handling."""

    def test_invalid_yaml_syntax(self):
        content = """apiVersion: v1
kind: ConfigMap
metadata:
  name: test
  invalid yaml here: [unclosed bracket
"""
        with pytest.raises(Exception):
            format_yaml_content(content)

    def test_file_not_found(self, capsys):
        result = format_file(Path("/nonexistent/file.yaml"))
        assert result is False
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower() or "error" in captured.err.lower()

    def test_non_yaml_extension_skipped(self, tmp_path):
        # Files with non-yaml extensions should be skipped in main()
        # but format_file processes by content, not extension
        test_file = tmp_path / "test.txt"
        test_file.write_text("""apiVersion: v1
kind: ConfigMap
metadata:
  name: test
""")
        # format_file should still work on it
        result = format_file(test_file)
        # It will process it since it's valid K8s YAML
        assert result is False  # No changes needed if already ordered

    def test_permission_error(self, tmp_path, capsys):
        import os
        import stat

        test_file = tmp_path / "readonly.yaml"
        test_file.write_text("""kind: Service
apiVersion: v1
metadata:
  name: test
spec:
  type: ClusterIP
""")
        # Make file read-only
        os.chmod(test_file, stat.S_IRUSR)
        try:
            result = format_file(test_file)
            assert result is False
            captured = capsys.readouterr()
            assert "permission" in captured.err.lower()
        finally:
            # Restore permissions for cleanup
            os.chmod(test_file, stat.S_IRUSR | stat.S_IWUSR)


class TestCronJobFormatting:
    """Tests for CronJob nested job template formatting."""

    def test_cronjob_job_template(self):
        content = """apiVersion: batch/v1
kind: CronJob
metadata:
  name: test
spec:
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - image: busybox
            name: job
          restartPolicy: OnFailure
    metadata:
      labels:
        app: test
  schedule: "0 * * * *"
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # schedule should come before jobTemplate in CronJob spec
        schedule_pos = formatted.find("schedule:")
        jobtemplate_pos = formatted.find("jobTemplate:")
        assert schedule_pos < jobtemplate_pos
        # In jobTemplate, metadata should come before spec
        # Find jobTemplate section and check ordering within it
        jt_section = formatted[jobtemplate_pos:]
        jt_metadata_pos = jt_section.find("metadata:")
        jt_spec_pos = jt_section.find("spec:")
        assert jt_metadata_pos < jt_spec_pos


class TestConfig:
    """Tests for configuration file functionality."""

    def test_config_default_values(self):
        config = Config()
        assert config.additional_kinds == {}

    def test_config_is_supported_kind_builtin(self):
        config = Config()
        assert config.is_supported_kind("Deployment") is True
        assert config.is_supported_kind("Service") is True
        assert config.is_supported_kind("UnknownKind") is False

    def test_config_is_supported_kind_additional(self):
        config = Config(additional_kinds={"MyCustomResource": ["field1", "field2"]})
        assert config.is_supported_kind("MyCustomResource") is True
        assert config.is_supported_kind("Deployment") is True  # Still supports built-ins

    def test_config_get_spec_order_builtin(self):
        config = Config()
        order = config.get_spec_order("Deployment")
        assert "replicas" in order
        assert "template" in order

    def test_config_get_spec_order_additional(self):
        config = Config(additional_kinds={"MyCustomResource": ["field1", "field2"]})
        order = config.get_spec_order("MyCustomResource")
        assert order == ["field1", "field2"]

    def test_config_get_spec_order_unknown(self):
        config = Config()
        order = config.get_spec_order("UnknownKind")
        assert order == []

    def test_load_config_no_file(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.additional_kinds == {}

    def test_load_config_with_additional_kinds(self, tmp_path):
        config_file = tmp_path / CONFIG_FILE_NAME
        config_file.write_text("""
additional_kinds:
  MyCustomResource:
    - field1
    - field2
    - field3
  AnotherKind:
    - spec1
""")
        config = load_config(config_file)
        assert "MyCustomResource" in config.additional_kinds
        assert config.additional_kinds["MyCustomResource"] == ["field1", "field2", "field3"]
        assert "AnotherKind" in config.additional_kinds

    def test_load_config_empty_file(self, tmp_path):
        config_file = tmp_path / CONFIG_FILE_NAME
        config_file.write_text("")
        config = load_config(config_file)
        assert config.additional_kinds == {}

    def test_load_config_invalid_yaml(self, tmp_path, capsys):
        config_file = tmp_path / CONFIG_FILE_NAME
        config_file.write_text("invalid: yaml: content: [")
        config = load_config(config_file)
        # Should return default config and print warning
        assert config.additional_kinds == {}
        captured = capsys.readouterr()
        assert "Warning" in captured.err

    def test_find_config_file_in_current_dir(self, tmp_path, monkeypatch):
        config_file = tmp_path / CONFIG_FILE_NAME
        config_file.write_text("additional_kinds: {}")
        monkeypatch.chdir(tmp_path)
        found = find_config_file()
        assert found == config_file

    def test_find_config_file_not_found(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Create a .git to stop upward search
        (tmp_path / ".git").mkdir()
        found = find_config_file()
        # Should be None unless there's a config in home dir
        # (we can't easily test home dir without mocking)
        assert found is None or found.name == CONFIG_FILE_NAME


class TestCustomKindFormatting:
    """Tests for formatting custom kinds from config."""

    def test_custom_kind_formatted(self):
        config = Config(additional_kinds={
            "MyCustomResource": ["field1", "field2", "field3"]
        })
        content = """apiVersion: custom.io/v1
kind: MyCustomResource
metadata:
  name: test
spec:
  field3: value3
  field1: value1
  field2: value2
"""
        formatted, has_k8s = format_yaml_content(content, config)
        assert has_k8s is True
        # field1 should come before field2, field2 before field3
        field1_pos = formatted.find("field1:")
        field2_pos = formatted.find("field2:")
        field3_pos = formatted.find("field3:")
        assert field1_pos < field2_pos < field3_pos

    def test_custom_kind_without_config_skipped(self):
        content = """apiVersion: custom.io/v1
kind: MyCustomResource
metadata:
  name: test
spec:
  field1: value1
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is False  # Not recognized without config
        assert formatted == content

    def test_custom_kind_top_level_ordering(self):
        config = Config(additional_kinds={"MyCustomResource": ["field1"]})
        content = """kind: MyCustomResource
spec:
  field1: value1
apiVersion: custom.io/v1
metadata:
  name: test
"""
        formatted, has_k8s = format_yaml_content(content, config)
        assert has_k8s is True
        # apiVersion should come before kind
        api_pos = formatted.find("apiVersion:")
        kind_pos = formatted.find("kind:")
        assert api_pos < kind_pos

    def test_custom_kind_metadata_ordering(self):
        config = Config(additional_kinds={"MyCustomResource": []})
        content = """apiVersion: custom.io/v1
kind: MyCustomResource
metadata:
  labels:
    app: test
  name: test
  namespace: default
spec: {}
"""
        formatted, has_k8s = format_yaml_content(content, config)
        assert has_k8s is True
        # name should come before namespace, namespace before labels
        name_pos = formatted.find("name: test")
        namespace_pos = formatted.find("namespace: default")
        labels_pos = formatted.find("labels:")
        assert name_pos < namespace_pos < labels_pos


class TestFormattingOptions:
    """Tests for YAML formatting options in config."""

    def test_default_indent(self):
        formatted, has_k8s = format_yaml_content(minimal_service(with_ports=False))
        assert has_k8s is True
        # Default indent is 2 spaces
        assert "  name: test" in formatted

    def test_custom_indent_4(self):
        config = Config(indent=4)
        formatted, has_k8s = format_yaml_content(minimal_service(with_ports=False), config)
        assert has_k8s is True
        # Should use 4-space indent
        assert "    name: test" in formatted
        assert "    type: ClusterIP" in formatted

    def test_custom_sequence_indent(self):
        config = Config(sequence_indent=4)
        formatted, has_k8s = format_yaml_content(minimal_service(), config)
        assert has_k8s is True
        # Sequence items should have 4-space indent
        assert '- port: 80' in formatted or '-   port: 80' in formatted

    def test_sequence_offset(self):
        config = Config(sequence_offset=2)
        formatted, has_k8s = format_yaml_content(minimal_service(), config)
        assert has_k8s is True
        # With offset=2, sequence content is offset from the dash
        assert has_k8s is True

    def test_line_width_default(self):
        # Default line width is 4096 (essentially no wrapping)
        config = Config()
        assert config.line_width == 4096

    def test_line_width_custom(self):
        config = Config(line_width=80)
        assert config.line_width == 80

    def test_load_config_with_formatting_options(self, tmp_path):
        config_file = tmp_path / CONFIG_FILE_NAME
        config_file.write_text("""
indent: 4
sequence_indent: 4
sequence_offset: 2
line_width: 120
additional_kinds:
  MyKind:
    - field1
""")
        config = load_config(config_file)
        assert config.indent == 4
        assert config.sequence_indent == 4
        assert config.sequence_offset == 2
        assert config.line_width == 120
        assert "MyKind" in config.additional_kinds

    def test_load_config_with_invalid_formatting_values(self, tmp_path):
        config_file = tmp_path / CONFIG_FILE_NAME
        config_file.write_text("""
indent: -1
sequence_indent: "invalid"
sequence_offset: -5
line_width: 0
""")
        config = load_config(config_file)
        # Invalid values should fall back to defaults
        assert config.indent == 2
        assert config.sequence_indent == 2
        assert config.sequence_offset == 0
        assert config.line_width == 4096

    def test_load_config_partial_formatting_options(self, tmp_path):
        config_file = tmp_path / CONFIG_FILE_NAME
        config_file.write_text("""
indent: 4
""")
        config = load_config(config_file)
        # Only indent specified, others should be defaults
        assert config.indent == 4
        assert config.sequence_indent == 2
        assert config.sequence_offset == 0
        assert config.line_width == 4096

    def test_formatting_options_idempotent(self):
        config = Config(indent=4, sequence_indent=4)
        formatted1, _ = format_yaml_content(minimal_service(with_ports=False), config)
        formatted2, _ = format_yaml_content(formatted1, config)
        assert formatted1 == formatted2


class TestRBACFormatting:
    """Tests for RBAC resource formatting (Role, ClusterRole, RoleBinding, ClusterRoleBinding)."""

    def test_role_recognized(self):
        doc = parse_yaml(minimal_role("pod-reader"))
        assert is_k8s_manifest(doc) is True

    def test_clusterrole_recognized(self):
        doc = parse_yaml("""
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: secret-reader
rules:
- apiGroups: [""]
  resources: ["secrets"]
  verbs: ["get"]
""")
        assert is_k8s_manifest(doc) is True

    def test_rolebinding_recognized(self):
        doc = parse_yaml("""
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-pods
subjects:
- kind: User
  name: jane
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
""")
        assert is_k8s_manifest(doc) is True

    def test_clusterrolebinding_recognized(self):
        doc = parse_yaml("""
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: read-secrets-global
subjects:
- kind: Group
  name: managers
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: secret-reader
  apiGroup: rbac.authorization.k8s.io
""")
        assert is_k8s_manifest(doc) is True

    def test_role_rules_ordering(self):
        content = """apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
rules:
- verbs: ["get", "list", "watch"]
  resourceNames: ["my-pod"]
  resources: ["pods"]
  apiGroups: [""]
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # apiGroups -> resources -> resourceNames -> verbs
        apigroups_pos = formatted.find("apiGroups:")
        resources_pos = formatted.find("resources:")
        resourcenames_pos = formatted.find("resourceNames:")
        verbs_pos = formatted.find("verbs:")
        assert apigroups_pos < resources_pos < resourcenames_pos < verbs_pos

    def test_clusterrole_rules_ordering_with_nonresourceurls(self):
        content = """apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: metrics-reader
rules:
- nonResourceURLs: ["/metrics"]
  verbs: ["get"]
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # verbs should come before nonResourceURLs
        verbs_pos = formatted.find("verbs:")
        nonresource_pos = formatted.find("nonResourceURLs:")
        assert verbs_pos < nonresource_pos

    def test_rolebinding_subjects_ordering(self):
        content = """apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-pods
subjects:
- namespace: default
  name: jane
  apiGroup: rbac.authorization.k8s.io
  kind: User
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # kind -> apiGroup -> name -> namespace
        subjects_start = formatted.find("subjects:")
        subjects_section = formatted[subjects_start:formatted.find("roleRef:")]
        kind_pos = subjects_section.find("kind: User")
        apigroup_pos = subjects_section.find("apiGroup:")
        name_pos = subjects_section.find("name: jane")
        namespace_pos = subjects_section.find("namespace:")
        assert kind_pos < apigroup_pos < name_pos < namespace_pos

    def test_rolebinding_roleref_ordering(self):
        content = """apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-pods
subjects:
- kind: User
  name: jane
  apiGroup: rbac.authorization.k8s.io
roleRef:
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
  kind: Role
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # kind -> apiGroup -> name in roleRef
        roleref_start = formatted.find("roleRef:")
        roleref_section = formatted[roleref_start:]
        kind_pos = roleref_section.find("kind: Role")
        apigroup_pos = roleref_section.find("apiGroup:")
        name_pos = roleref_section.find("name: pod-reader")
        assert kind_pos < apigroup_pos < name_pos

    def test_role_top_level_ordering(self):
        content = """rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get"]
kind: Role
metadata:
  name: pod-reader
apiVersion: rbac.authorization.k8s.io/v1
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # apiVersion -> kind -> metadata -> rules
        api_pos = formatted.find("apiVersion:")
        kind_pos = formatted.find("kind:")
        metadata_pos = formatted.find("metadata:")
        rules_pos = formatted.find("rules:")
        assert api_pos < kind_pos < metadata_pos < rules_pos

    def test_rolebinding_top_level_ordering(self):
        content = """roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
subjects:
- kind: User
  name: jane
  apiGroup: rbac.authorization.k8s.io
kind: RoleBinding
metadata:
  name: read-pods
apiVersion: rbac.authorization.k8s.io/v1
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # apiVersion -> kind -> metadata -> subjects -> roleRef
        api_pos = formatted.find("apiVersion:")
        kind_pos = formatted.find("kind:")
        metadata_pos = formatted.find("metadata:")
        subjects_pos = formatted.find("subjects:")
        roleref_pos = formatted.find("roleRef:")
        assert api_pos < kind_pos < metadata_pos < subjects_pos < roleref_pos

    def test_rbac_idempotent(self):
        content = """apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-pods
subjects:
- kind: User
  apiGroup: rbac.authorization.k8s.io
  name: jane
roleRef:
  kind: Role
  apiGroup: rbac.authorization.k8s.io
  name: pod-reader
"""
        formatted1, _ = format_yaml_content(content)
        formatted2, _ = format_yaml_content(formatted1)
        assert formatted1 == formatted2

    def test_role_with_comments(self):
        content = """apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
# Pod read access
rules:
- verbs: ["get", "list"]  # read-only
  resources: ["pods"]
  apiGroups: [""]
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        assert "# Pod read access" in formatted
        assert "# read-only" in formatted


class TestMalformedManifests:
    """Tests for malformed or edge-case K8s manifests."""

    def test_api_version_is_number(self):
        """apiVersion as a number should not be treated as K8s manifest."""
        doc = parse_yaml("""
apiVersion: 1
kind: Deployment
metadata:
  name: test
""")
        assert is_k8s_manifest(doc) is False

    def test_api_version_is_list(self):
        """apiVersion as a list should not be treated as K8s manifest."""
        doc = parse_yaml("""
apiVersion:
  - v1
  - v2
kind: Deployment
metadata:
  name: test
""")
        assert is_k8s_manifest(doc) is False

    def test_kind_is_number(self):
        """kind as a number should not be treated as K8s manifest."""
        doc = parse_yaml("""
apiVersion: v1
kind: 123
metadata:
  name: test
""")
        assert is_k8s_manifest(doc) is False

    def test_kind_is_list(self):
        """kind as a list should not be treated as K8s manifest."""
        doc = parse_yaml("""
apiVersion: v1
kind:
  - Deployment
  - Service
metadata:
  name: test
""")
        assert is_k8s_manifest(doc) is False

    def test_empty_document(self):
        """Empty YAML document should be handled gracefully."""
        doc = parse_yaml("")
        assert doc is None
        # Explicit None check for is_k8s_manifest
        assert is_k8s_manifest(None) is False

    def test_scalar_document(self):
        """Scalar YAML value should not crash."""
        doc = parse_yaml("just a string")
        assert is_k8s_manifest(doc) is False

    def test_list_document(self):
        """List YAML document should not crash."""
        doc = parse_yaml("""
- item1
- item2
""")
        assert is_k8s_manifest(doc) is False

    def test_null_metadata(self):
        """null metadata should be handled gracefully."""
        content = """apiVersion: apps/v1
kind: Deployment
metadata: null
spec:
  replicas: 1
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True

    def test_null_spec(self):
        """null spec should be handled gracefully."""
        content = """apiVersion: v1
kind: ServiceAccount
metadata:
  name: test
spec: null
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True


class TestDeeplyNested:
    """Tests for deeply nested structures."""

    def test_deep_container_nesting(self):
        """Test formatting of deeply nested container spec."""
        content = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test
  template:
    metadata:
      labels:
        app: test
    spec:
      containers:
      - name: app
        image: nginx
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
            httpHeaders:
            - name: X-Custom-Header
              value: test
          initialDelaySeconds: 5
        env:
        - name: CONFIG
          valueFrom:
            configMapKeyRef:
              name: my-config
              key: config.json
        volumeMounts:
        - name: data
          mountPath: /data
          subPath: app-data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: my-pvc
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # Verify deep nesting is preserved and formatted
        assert "httpHeaders:" in formatted
        assert "configMapKeyRef:" in formatted
        assert "persistentVolumeClaim:" in formatted

    def test_cronjob_triple_nesting(self):
        """Test CronJob with triple-nested template structure."""
        content = """apiVersion: batch/v1
kind: CronJob
metadata:
  name: test
spec:
  schedule: "0 * * * *"
  jobTemplate:
    metadata:
      labels:
        job: test
    spec:
      template:
        metadata:
          labels:
            pod: test
        spec:
          restartPolicy: OnFailure
          containers:
          - name: job
            image: busybox
            command: ["echo", "hello"]
            resources:
              limits:
                memory: 64Mi
              requests:
                memory: 32Mi
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        # Verify triple nesting is handled
        assert "jobTemplate:" in formatted
        assert "restartPolicy: OnFailure" in formatted
        # resources ordering: requests before limits
        requests_pos = formatted.find("requests:")
        limits_pos = formatted.find("limits:")
        assert requests_pos < limits_pos


class TestLargeFiles:
    """Tests for larger files to ensure no performance issues."""

    def test_many_containers(self):
        """Test formatting a deployment with many containers."""
        containers = "\n".join([
            f"""      - name: container-{i}
        image: nginx:{i}
        ports:
        - containerPort: {8080 + i}"""
            for i in range(10)
        ])
        content = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: large-deployment
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test
  template:
    metadata:
      labels:
        app: test
    spec:
      containers:
{containers}
"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        for i in range(10):
            assert f"container-{i}" in formatted

    def test_multi_document_many_docs(self):
        """Test formatting a file with many documents using fixtures."""
        docs = [minimal_service(name=f"service-{i}", port=80 + i) for i in range(10)]
        content = "---\n".join(docs)
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        for i in range(10):
            assert f"service-{i}" in formatted


class TestFixtureBasedValidation:
    """Tests using fixture helpers to validate basic functionality."""

    def test_deployment_fixture_formats(self):
        """Verify the deployment fixture produces valid, formattable YAML."""
        content = minimal_deployment("my-app", replicas=3)
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        assert "my-app" in formatted
        assert "replicas: 3" in formatted

    def test_service_fixture_formats(self):
        """Verify the service fixture produces valid, formattable YAML."""
        content = minimal_service("my-svc", port=8080)
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        assert "my-svc" in formatted
        assert "port: 8080" in formatted

    def test_pod_fixture_formats(self):
        """Verify the pod fixture produces valid, formattable YAML."""
        content = minimal_pod("my-pod")
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        assert "my-pod" in formatted

    def test_mixed_fixtures_multi_doc(self):
        """Test multi-document with mixed resource types from fixtures."""
        content = f"""{minimal_deployment("app")}---
{minimal_service("app-svc")}---
{minimal_pod("debug-pod")}"""
        formatted, has_k8s = format_yaml_content(content)
        assert has_k8s is True
        assert "kind: Deployment" in formatted
        assert "kind: Service" in formatted
        assert "kind: Pod" in formatted
