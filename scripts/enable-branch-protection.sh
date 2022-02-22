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

curl -X PUT -u $GITHUB_USER:$GITHUB_TOKEN -H "Accept: application/vnd.github.luke-cage-preview+json" https://api.github.com/repos/$OWNER/$REPO/branches/$BRANCH/protection -d '{"required_status_checks":{"strict":false,"checks":[{"context":"Docs: build check","app_id":null},{"context":"Unmodified Submodules","app_id":null},{"context":"ceph API tests","app_id":null},{"context":"make check","app_id":null},{"context":"Signed-off-by","app_id":null}]},"required_pull_request_reviews":{"dismiss_stale_reviews":false,"require_code_owner_reviews":false,"required_approving_review_count":1},"required_signatures":false,"enforce_admins":true,"required_linear_history":false,"allow_force_pushes":false,"allow_deletions":false,"required_conversation_resolution":false,"restrictions":null}'
