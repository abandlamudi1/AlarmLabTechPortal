# Kubernetes Operations Runbook

**Status: ACTIVE — Helm chart implemented in Slice G-part2 (issues #125, #126, #127). Chart lives in `charts/lab-tech-portal/`.**

This document outlines operational procedures for running the Lab Tech Portal on Kubernetes using Helm.

---

## Overview

The Lab Tech Portal is deployed to Kubernetes via the Helm chart at `charts/lab-tech-portal/`:

- **ConfigMap** — all non-secret runtime env vars (Issue #127)
- **Deployments** — `web` (Gunicorn/Flask), `worker` (Celery), `beat` (Celery beat scheduler)
- **HorizontalPodAutoscaler** — web tier scales 2→10 replicas at CPU 70% / memory 80%
- **Service** — ClusterIP, port 80 → 8000
- **Ingress** — nginx or traefik, cert-manager TLS, HTTP→HTTPS redirect
- **SealedSecrets** — secret values managed separately (Issue #51)

---

## Cluster Prerequisites

The following must be installed and configured in the cluster **before** running `helm install`:

### 1. cert-manager

cert-manager automates TLS certificate provisioning via Let's Encrypt or an internal CA.

```bash
# Install cert-manager (v1.14+)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml

# Verify cert-manager pods are running
kubectl get pods -n cert-manager
```

Create a ClusterIssuer for Let's Encrypt production (or substitute your internal CA):

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ops@example.com
    privateKeySecretRef:
      name: letsencrypt-prod-account-key
    solvers:
      - http01:
          ingress:
            class: nginx
```

```bash
kubectl apply -f clusterissuer-letsencrypt.yaml
kubectl describe clusterissuer letsencrypt-prod
```

### 2. Ingress Controller (nginx or traefik)

The Ingress class is configurable via `values.yaml: ingress.className`. Default is `nginx`.

**nginx:**
```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace
```

**traefik:**
```bash
helm repo add traefik https://helm.traefik.io/traefik
helm install traefik traefik/traefik -n traefik --create-namespace
```

### 3. Kubernetes Metrics Server

Required for HPA (HorizontalPodAutoscaler) to read CPU and memory utilisation.

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl get deployment metrics-server -n kube-system
```

### 4. SealedSecrets Controller (Issue #51)

Secret values (SECRET_KEY, OKTA_CLIENT_SECRET, JIRA_PAT, S3_ACCESS_KEY, S3_SECRET_KEY,
ATLASSIAN_MCP_TOKEN, SYSTEM_LOCATOR_DELETE_PIN) are managed via SealedSecrets. Install the
controller before deploying the chart. The Deployments reference a Secret named
`<release-name>-lab-tech-portal-secrets`; the SealedSecret definition is tracked in Issue #51.

---

## Initial Deploy

### Prepare the cluster namespace

```bash
kubectl create namespace lab-portal
```

### Render and inspect manifests (dry run)

```bash
# Render templates locally (no cluster required):
helm template lab-tech-portal charts/lab-tech-portal \
  --namespace lab-portal \
  --set ingress.host=lab-portal.example.com

# Dry-run against a live cluster:
helm template lab-tech-portal charts/lab-tech-portal \
  --namespace lab-portal \
  --set ingress.host=lab-portal.example.com \
  | kubectl apply --dry-run=client -f -
```

### Deploy the full stack

```bash
helm install lab-tech-portal charts/lab-tech-portal \
  --namespace lab-portal \
  --set ingress.host=lab-portal.example.com \
  --set image.tag=v1.0.0
```

Override values per environment:

```bash
# Production example
helm install lab-tech-portal charts/lab-tech-portal \
  --namespace lab-portal \
  -f values-prod.yaml \
  --set image.tag=v1.2.3
```

### Verify deployment

```bash
kubectl get pods -n lab-portal
kubectl get svc -n lab-portal
kubectl get ingress -n lab-portal
kubectl logs -n lab-portal deployment/lab-tech-portal-web -f
```

---

## TLS Certificate Verification

After deploying the Ingress, cert-manager will automatically request a TLS certificate
from the configured ClusterIssuer. This typically completes within 1–2 minutes for
Let's Encrypt HTTP-01 challenges.

### Check certificate provisioning status

```bash
# List Certificate resources in the namespace
kubectl get certificate -n lab-portal

# Describe the certificate for detailed status and events
kubectl describe certificate lab-portal-tls -n lab-portal

# Expected status when ready:
#   Status:
#     Conditions:
#       Message: Certificate is up to date and has not expired
#       Reason:  Ready
#       Status:  "True"
#       Type:    Ready
```

### Verify the certificate is serving correctly

```bash
# Check the TLS secret exists
kubectl get secret lab-portal-tls -n lab-portal

# Test HTTPS from outside the cluster (replace with your hostname)
curl -v https://lab-portal.example.com/healthz

# Expected: HTTP 200 response with a valid TLS certificate.
# The certificate CN should match the ingress host.
```

### Verify HTTP→HTTPS redirect

```bash
curl -v http://lab-portal.example.com/healthz
# Expected: HTTP 301 or 308 redirect to https://lab-portal.example.com/healthz
```

### Troubleshoot certificate issuance failures

```bash
# Check CertificateRequest objects for ACME challenge status
kubectl get certificaterequest -n lab-portal
kubectl describe certificaterequest -n lab-portal <name>

# Check cert-manager controller logs
kubectl logs -n cert-manager deployment/cert-manager --tail=50

# Check the Order resource (ACME HTTP-01 challenge lifecycle)
kubectl get order -n lab-portal
kubectl describe order -n lab-portal <name>
```

---

## Scaling

### Scale the web tier

The web tier scales automatically via HPA (CPU 70% / memory 80%, min 2 / max 10 replicas).

**Note**: With HPA active, changing `replicaCount.web` via `helm upgrade` has limited effect — HPA reconverges the replica count within one sync interval (~15s–30s). To durably change the replica count, update the HPA bounds instead:

```bash
# Update HPA bounds (durable — HPA respects these)
helm upgrade lab-tech-portal charts/lab-tech-portal \
  --namespace lab-portal \
  --reuse-values \
  --set hpa.web.minReplicas=4 \
  --set hpa.web.maxReplicas=10
```

For a temporary scale-up during an incident (without a Helm release), suspend HPA first:

```bash
# Suspend HPA, then scale manually
kubectl patch hpa lab-tech-portal-web-hpa -n lab-portal \
  -p '{"spec":{"minReplicas":4,"maxReplicas":4}}'
# Restore normal HPA bounds when incident is resolved
kubectl patch hpa lab-tech-portal-web-hpa -n lab-portal \
  -p '{"spec":{"minReplicas":2,"maxReplicas":10}}'
```

### Scale Celery workers

```bash
helm upgrade lab-tech-portal charts/lab-tech-portal \
  --namespace lab-portal \
  --reuse-values \
  --set replicaCount.worker=5
```

### Scale beat (must be 1)

Beat is hardcoded to 1 replica in the chart and is not exposed in values.yaml.
Multiple beat instances cause duplicate scheduled task execution. Do not scale it.

---

## Rolling Updates

### Deploy a new image

```bash
<TBD-slice-g-part2>
# kubectl set image deployment/web \
#   web=lab-tech-portal:web-vX.Y.Z \
#   -n lab-portal
#
# Or use kubectl rollout:
# kubectl rollout restart deployment/web -n lab-portal
```

### Monitor rollout progress

```bash
<TBD-slice-g-part2>
# kubectl rollout status deployment/web -n lab-portal
```

### Monitor pod logs during rollout

```bash
<TBD-slice-g-part2>
# kubectl logs -n lab-portal -l app=web --tail=50 -f
```

---

## Rollback

### Rollback to previous image

```bash
<TBD-slice-g-part2>
# kubectl rollout undo deployment/web -n lab-portal
```

### Rollback to a specific revision

```bash
<TBD-slice-g-part2>
# kubectl rollout undo deployment/web --to-revision=2 -n lab-portal
```

### Verify rollback

```bash
<TBD-slice-g-part2>
# kubectl rollout status deployment/web -n lab-portal
# kubectl get pods -n lab-portal
```

---

## Data Management

### Database backup (PostgreSQL)

```bash
<TBD-slice-g-part2>
# kubectl exec -it -n lab-portal postgres-statefulset-0 -- \
#   pg_dump -U postgres lab_tech_portal > backup.sql
```

### Database restore

```bash
<TBD-slice-g-part2>
# kubectl cp backup.sql -n lab-portal postgres-statefulset-0:/tmp/
# kubectl exec -it -n lab-portal postgres-statefulset-0 -- \
#   psql -U postgres lab_tech_portal < /tmp/backup.sql
```

### Export uploaded files

```bash
<TBD-slice-g-part2>
# kubectl cp -n lab-portal web-pod-0:/data/uploads ./uploads-backup
```

### Restore uploaded files

```bash
<TBD-slice-g-part2>
# kubectl cp ./uploads-backup -n lab-portal web-pod-0:/data/uploads
```

---

## Secrets Management

### Rotate sealed secrets

```bash
<TBD-slice-g-part2>
# Update the Secret resource with new values
# kubectl apply -f k8s/secrets.yaml -n lab-portal
# Restart affected pods
# kubectl rollout restart deployment/web -n lab-portal
```

### Update a single environment variable

```bash
<TBD-slice-g-part2>
# kubectl set env deployment/web \
#   SECRET_KEY=<new-value> \
#   -n lab-portal
```

---

## Observability

### View real-time logs

```bash
<TBD-slice-g-part2>
# kubectl logs -n lab-portal -l app=web --tail=100 -f
# kubectl logs -n lab-portal -l app=worker --tail=100 -f
```

### Check pod resource usage

```bash
<TBD-slice-g-part2>
# kubectl top pods -n lab-portal
# kubectl describe node <node-name>
```

### List events in the namespace

```bash
<TBD-slice-g-part2>
# kubectl get events -n lab-portal --sort-by='.lastTimestamp'
```

### Exec into a pod for debugging

```bash
<TBD-slice-g-part2>
# kubectl exec -it -n lab-portal <pod-name> -- /bin/bash
```

---

## Troubleshooting

### Pod stuck in CrashLoopBackOff

```bash
<TBD-slice-g-part2>
# kubectl logs -n lab-portal <pod-name> --previous
# kubectl describe pod -n lab-portal <pod-name>
```

### Service not accessible

```bash
<TBD-slice-g-part2>
# kubectl get svc -n lab-portal
# kubectl get endpoints -n lab-portal
# kubectl port-forward -n lab-portal svc/web 8000:8000
```

### Database connection issues

```bash
<TBD-slice-g-part2>
# Verify StatefulSet is running
# kubectl get statefulsets -n lab-portal
# Check logs
# kubectl logs -n lab-portal postgres-statefulset-0
```

---

## Shutdown and Cleanup

### Delete the entire deployment

```bash
<TBD-slice-g-part2>
# kubectl delete namespace lab-portal
# (This also deletes all PersistentVolumeClaims and other resources in that namespace)
```

### Delete specific resources

```bash
<TBD-slice-g-part2>
# kubectl delete deployment web -n lab-portal
# kubectl delete statefulset postgres -n lab-portal
# kubectl delete pvc -n lab-portal --all
```

---

## See Also

- [../architecture.md](../architecture.md) — system design
- [./DOCKER_RUNBOOK.md](./DOCKER_RUNBOOK.md) — Docker Compose reference
- [./CLEANUP_PLAN.md](./CLEANUP_PLAN.md) — roadmap (Slice G-part2 = Sprint 5+)
- [./CONTAINERIZATION_ROADMAP.md](./CONTAINERIZATION_ROADMAP.md) — technical requirements
