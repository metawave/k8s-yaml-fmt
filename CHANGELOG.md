# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2024-12-22

### Added

- Initial release
- Kubernetes YAML formatting with idiomatic key ordering
- Support for 25 resource kinds: Deployment, StatefulSet, DaemonSet, Service, Ingress, ConfigMap, Secret, Pod, Job, CronJob, and more
- Automatic detection of Kubernetes manifests (skips docker-compose, GitHub Actions, etc.)
- SOPS-encrypted file detection and skip
- Multi-document YAML support
- Comment preservation
- Pre-commit hook integration
- CLI with `--check` and `--diff` modes
