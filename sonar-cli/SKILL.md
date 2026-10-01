---
name: sonar-cli
description: Read and explain SonarQube analysis results and issues with its CLI.
---

## Authentication

Knauf-Group accounts are hosted in the SonarQube Cloud EU region.

```sh
# Log in (opens browser for interactive auth)
sonar auth login -o knauf-group -s https://sonarcloud.io

# Check authentication status
sonar auth status
```

## Find projects and issues

```sh
# List all projects
sonar list projects | jq

# List issues for a project
sonar list issues -p Knauf-Group_pas-frontend --severities HIGH,BLOCKER --statuses OPEN
```

## Secret scanning

Run secret scanning only on individual files, not directories or full repositories.

```sh
# Scan a file for hard-coded secrets
sonar analyze secrets ./Dockerfile
```
