# Kubernetes

Raw Kubernetes manifests for cluster-level resources that fall outside the
`ai-ios` Helm release (e.g. cluster bootstrap, RBAC, network policies, CRDs).
Empty in the platform foundation phase — the application resources
(namespace, ConfigMap, Secret, Deployments, Services, Ingress) are defined
in [`infrastructure/helm/ai-ios`](../helm/ai-ios) instead. Populated as
cluster-level needs arise in a future infrastructure prompt.
