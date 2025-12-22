# k8s-yaml-fmt

[![CI](https://github.com/metawave/k8s-yaml-fmt/actions/workflows/ci.yaml/badge.svg)](https://github.com/metawave/k8s-yaml-fmt/actions/workflows/ci.yaml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Kubernetes YAML formatter that enforces idiomatic key ordering.

## Why?

Because `kubectl` output, official docs, and human intuition all expect this order:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: default
  labels:
    app: my-app
spec:
  replicas: 3
  ...
```

But most YAML formatters either sort alphabetically (wrong!) or preserve original order (inconsistent across team members).

## Features

- **K8s-only:** Only formats supported Kubernetes resource kinds, skips everything else
- **SOPS-aware:** Skips SOPS-encrypted files automatically
- **Idiomatic ordering:** `apiVersion` → `kind` → `metadata` → `spec`, and kind-specific field ordering
- **Comment-preserving:** Keeps your YAML comments intact
- **Multi-document:** Handles `---` separated files
- **Configurable:** Customize indent, sequence offset, and line width to match your project style
- **CRD support:** Add custom resource kinds via config file

## Installation

### As a pre-commit hook (recommended)

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/metawave/k8s-yaml-fmt
    rev: v0.1.0
    hooks:
      - id: k8s-yaml-fmt
```

Then run:

```bash
pre-commit install
pre-commit run --all-files
```

### Standalone

```bash
pip install k8s-yaml-fmt
```

Or install from source:

```bash
pip install git+https://github.com/metawave/k8s-yaml-fmt.git
```

## Usage

### Command line

```bash
# Format files in-place
k8s-yaml-fmt deployment.yaml service.yaml

# Check without modifying (exit 1 if changes needed)
k8s-yaml-fmt --check deployment.yaml

# Show diff without modifying
k8s-yaml-fmt --diff deployment.yaml

# Verbose output (show skipped files)
k8s-yaml-fmt -v *.yaml
```

### Pre-commit hooks

Two hooks are available:

| Hook ID | Description |
|---------|-------------|
| `k8s-yaml-fmt` | Format files in-place |
| `k8s-yaml-fmt-check` | Check only, fail if changes needed (for CI) |

#### Limiting to specific directories

```yaml
repos:
  - repo: https://github.com/metawave/k8s-yaml-fmt
    rev: v0.1.0
    hooks:
      - id: k8s-yaml-fmt
        files: ^(k8s|deploy|manifests)/
```

#### Excluding files

```yaml
repos:
  - repo: https://github.com/metawave/k8s-yaml-fmt
    rev: v0.1.0
    hooks:
      - id: k8s-yaml-fmt
        exclude: '\.sops\.yaml$'
```

## Configuration

Create a `.k8s-yaml-fmt.yaml` file in your project root:

```yaml
# Custom resource kinds (CRDs) with their spec field ordering
additional_kinds:
  MyCustomResource:
    - replicas
    - selector
    - template
  AnotherCRD:
    - config
    - settings

# Formatting options (to match your project's YAML style)
indent: 2              # Mapping indent (default: 2)
sequence_indent: 2     # Sequence indent (default: 2)
sequence_offset: 0     # Offset for sequence items (default: 0)
line_width: 4096       # Max line width before wrapping (default: 4096, high = no wrap)
```

### Formatting Options

| Option | Default | Description |
|--------|---------|-------------|
| `indent` | 2 | Number of spaces for mapping (object) indentation |
| `sequence_indent` | 2 | Number of spaces for sequence (list) indentation |
| `sequence_offset` | 0 | Offset for sequence item content from the dash |
| `line_width` | 4096 | Maximum line width before wrapping (high value = no wrapping) |

Example with different indent styles:

```yaml
# Default (indent: 2, sequence_indent: 2, sequence_offset: 0)
spec:
  containers:
  - name: app
    image: nginx

# With sequence_offset: 2
spec:
  containers:
    - name: app
      image: nginx

# With indent: 4
spec:
    containers:
    - name: app
      image: nginx
```

### Config File Discovery

The config file is auto-discovered by searching:
1. Current directory
2. Parent directories (up to git root)
3. Home directory

Or specify explicitly:

```bash
k8s-yaml-fmt --config /path/to/.k8s-yaml-fmt.yaml deployment.yaml
```

## Supported Resources

Only resource kinds with field ordering are formatted (others are skipped):

- **Workloads:** Deployment, StatefulSet, DaemonSet, ReplicaSet, Pod, Job, CronJob
- **Networking:** Service, Ingress, NetworkPolicy
- **Storage:** PersistentVolume, PersistentVolumeClaim
- **Auth:** ServiceAccount, Role, ClusterRole, RoleBinding, ClusterRoleBinding
- **Other:** HorizontalPodAutoscaler, PodDisruptionBudget

Resources without complex fields (ConfigMap, Secret, Namespace, etc.) are skipped since they only benefit from basic YAML formatting.

## Key Ordering

### Top-level

```
apiVersion → kind → metadata → spec → data → stringData → type → rules → status
```

### Metadata

```
name → namespace → labels → annotations → ownerReferences → finalizers
```

### Deployment/StatefulSet/DaemonSet spec

```
replicas → selector → strategy → ... → template (at end for readability)
```

### Container

```
name → image → imagePullPolicy → command → args → workingDir → ports →
envFrom → env → resources → volumeMounts → livenessProbe → readinessProbe → startupProbe
```

### Service ports

```
name → port → targetPort → protocol → nodePort
```

### Role/ClusterRole rules

```
apiGroups → resources → resourceNames → verbs → nonResourceURLs
```

### RoleBinding/ClusterRoleBinding subjects

```
kind → apiGroup → name → namespace
```

### RoleBinding/ClusterRoleBinding roleRef

```
kind → apiGroup → name
```

## Example

Before:
```yaml
kind: Deployment
spec:
  template:
    spec:
      containers:
        - resources:
            limits:
              memory: 128Mi
            requests:
              memory: 64Mi
          name: app
          image: nginx
  replicas: 3
  selector:
    matchLabels:
      app: test
apiVersion: apps/v1
metadata:
  labels:
    app: test
  name: test
```

After:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test
  labels:
    app: test
spec:
  replicas: 3
  selector:
    matchLabels:
      app: test
  template:
    spec:
      containers:
        - name: app
          image: nginx
          resources:
            requests:
              memory: 64Mi
            limits:
              memory: 128Mi
```

## Development

```bash
# Clone
git clone https://github.com/metawave/k8s-yaml-fmt.git
cd k8s-yaml-fmt

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in dev mode with test dependencies
pip install -e ".[dev]"

# Run tests
pytest -v

# Run linter
ruff check k8s_yaml_fmt.py
```

## License

MIT
