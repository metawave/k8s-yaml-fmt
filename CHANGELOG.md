# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2024-12-22

### Added

- Initial release
- Kubernetes YAML formatting with idiomatic key ordering
- Support for 19 resource kinds: Deployment, StatefulSet, DaemonSet, ReplicaSet, Pod, Job, CronJob, Service, Ingress, PersistentVolume, PersistentVolumeClaim, ServiceAccount, HorizontalPodAutoscaler, NetworkPolicy, PodDisruptionBudget, Role, ClusterRole, RoleBinding, ClusterRoleBinding
- Configuration file support (`.k8s-yaml-fmt.yaml`) for custom resource kinds and formatting options
- Automatic detection of Kubernetes manifests (skips non-K8s YAML files)
- SOPS-encrypted file detection and skip
- Multi-document YAML support
- Comment preservation
- Pre-commit hook integration
- CLI with `--check`, `--diff`, `--verbose`, and `--config` options
