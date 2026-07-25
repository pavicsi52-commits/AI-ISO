# Helm

Helm charts for AI-IOS. `ai-ios/` is the base chart from Prompt 011
(namespace, ConfigMap, Secret template, Deployment/Service for `gateway`
and `frontend`, and an optional Ingress). Future services are added as
additional templates in this same chart, following the same pattern.

Validate locally:

```bash
helm lint infrastructure/helm/ai-ios
helm template ai-ios infrastructure/helm/ai-ios
```

Secrets in `values.yaml` are intentionally empty — populate them via an
untracked values override file or `--set-string`, never by editing
`values.yaml` directly.
