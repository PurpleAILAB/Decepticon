# Cloud Resource Naming Pattern Dictionary

Common naming patterns for cloud resource discovery. Replace `<keyword>` with the target organization name, brand, product, or abbreviation.

## S3 / GCS / Azure Blob Bucket Names

### High-Priority Patterns
```
<keyword>
<keyword>-backup
<keyword>-backups
<keyword>-data
<keyword>-dev
<keyword>-development
<keyword>-staging
<keyword>-stage
<keyword>-stg
<keyword>-prod
<keyword>-production
<keyword>-prd
<keyword>-assets
<keyword>-static
<keyword>-uploads
<keyword>-media
<keyword>-logs
<keyword>-audit
<keyword>-archive
```

### Medium-Priority Patterns
```
<keyword>-internal
<keyword>-private
<keyword>-public
<keyword>-cdn
<keyword>-images
<keyword>-docs
<keyword>-documents
<keyword>-downloads
<keyword>-reports
<keyword>-temp
<keyword>-tmp
<keyword>-test
<keyword>-testing
<keyword>-qa
<keyword>-uat
<keyword>-sandbox
<keyword>-demo
```

### Infrastructure Patterns
```
<keyword>-terraform
<keyword>-tf-state
<keyword>-tfstate
<keyword>-cloudformation
<keyword>-config
<keyword>-configs
<keyword>-secrets
<keyword>-keys
<keyword>-certs
<keyword>-certificates
<keyword>-deploy
<keyword>-deployments
<keyword>-ci
<keyword>-ci-cd
<keyword>-artifacts
<keyword>-releases
<keyword>-packages
```

### Prefix/Suffix Variations
```
www.<keyword>
cdn.<keyword>
api.<keyword>
app.<keyword>
web.<keyword>
mail.<keyword>
<keyword>app
<keyword>web
<keyword>api
<keyword>io
<keyword>cloud
<keyword>online
```

## Azure Storage Account Names

Azure storage accounts are 3-24 chars, lowercase alphanumeric only (no hyphens).

```
<keyword>
<keyword>storage
<keyword>store
<keyword>data
<keyword>backup
<keyword>dev
<keyword>prod
<keyword>stg
<keyword>logs
<keyword>assets
<keyword>static
<keyword>media
```

## Container / Registry Names

### Docker Hub
```
<keyword>
<keyword>-official
<keyword>-images
```

### ECR / ACR / GCR
```
<keyword>
<keyword>-services
<keyword>-microservices
<keyword>-apps
```

## Serverless Function Names

### Common Function Naming
```
<keyword>-api
<keyword>-auth
<keyword>-webhook
<keyword>-handler
<keyword>-processor
<keyword>-worker
<keyword>-cron
<keyword>-scheduler
```
