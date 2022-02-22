#!/bin/bash
if [ $# -ne 1 ]; then
  echo "Usage: $(basename $0) BRANCH"
  echo
  echo "Example: \`$(basename $0) quincy"
  echo
  exit 1
else
  BRANCH="$1"
fi
# Uncomment these and write an API token to ~/.github_token to use this script outside of an automated Jenkins job
#GITHUB_USER=foo
#GITHUB_TOKEN=$(cat ~/.github_token)
OWNER=ceph
REPO=ceph

curl -X PUT -u $GITHUB_USER:$GITHUB_TOKEN -H "Accept: application/vnd.github.luke-cage-preview+json" https://api.github.com/repos/$OWNER/$REPO/branches/$BRANCH/protection -d '{"required_status_checks":null,"enforce_admins":true,"required_pull_request_reviews":null,"restrictions":null}'
