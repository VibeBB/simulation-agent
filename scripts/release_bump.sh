#!/usr/bin/env bash
# bump-version step of .github/workflows/release.yml.
# Ported from the bard/fpga wave-d reference: the whole state machine
# lives here so the workflow step is a thin wrapper and pytest can drive
# it with a stubbed `gh` (tests/test_release_bump.py).
#
# Resolves the release version (BUMP kind or an explicit SET_VERSION
# override), checks the v<version> tag is free, commits the version-file
# bump to main — direct push, or a self-approving + dispatched-checks +
# auto-merge fallback pull request when the ruleset rejects the push — and
# writes version/tag/sha to $GITHUB_OUTPUT.
#
# DRY_RUN=true rehearses the release: the version arithmetic and tag check
# run and the would-be outputs are emitted, but nothing is committed,
# pushed, tagged, or released (downstream jobs still exercise the
# verify/install-smoke/build path against HEAD).
#
# Environment inputs: BUMP, SET_VERSION, DRY_RUN, GH_TOKEN,
#   GITHUB_OUTPUT, GITHUB_STEP_SUMMARY, GITHUB_RUN_ID, GITHUB_REPOSITORY,
#   GITHUB_SERVER_URL. RELEASE_BUMP_* variables override the poll/retry
#   budgets (tests collapse them to zero).
set -euo pipefail

RETRY_ATTEMPTS=${RELEASE_BUMP_RETRY_ATTEMPTS:-5}
RETRY_DELAY_SECONDS=${RELEASE_BUMP_RETRY_DELAY_SECONDS:-10}
APPROVE_POLL_ATTEMPTS=${RELEASE_BUMP_APPROVE_POLL_ATTEMPTS:-10}
APPROVE_IDLE_SECONDS=${RELEASE_BUMP_APPROVE_IDLE_SECONDS:-30}
APPROVE_SEEN_SECONDS=${RELEASE_BUMP_APPROVE_SEEN_SECONDS:-10}
RUN_POLL_ATTEMPTS=${RELEASE_BUMP_RUN_POLL_ATTEMPTS:-30}
RUN_POLL_SECONDS=${RELEASE_BUMP_RUN_POLL_SECONDS:-10}
CONCLUSION_POLL_ATTEMPTS=${RELEASE_BUMP_CONCLUSION_POLL_ATTEMPTS:-6}
CONCLUSION_POLL_SECONDS=${RELEASE_BUMP_CONCLUSION_POLL_SECONDS:-10}
MERGE_WAIT_ATTEMPTS=${RELEASE_BUMP_MERGE_WAIT_ATTEMPTS:-40}
MERGE_WAIT_SECONDS=${RELEASE_BUMP_MERGE_WAIT_SECONDS:-30}

retry() {
  # Transient GitHub API/server errors (HTTP 5xx, TLS resets,
  # truncated responses) should not hard-fail the release: retry
  # gh/git calls with backoff before giving up.
  local attempt
  for ((attempt = 1; attempt <= RETRY_ATTEMPTS; attempt++)); do
    "$@" && return 0
    sleep $((attempt * RETRY_DELAY_SECONDS))
  done
  return 1
}

require_tag_free() {
  if git ls-remote --exit-code --tags origin "refs/tags/v$1"; then
    echo "::error::tag v$1 already exists" >&2
    exit 1
  fi
}

emit_outputs() {
  {
    echo "sha=$1"
    echo "version=$2"
    echo "tag=v$2"
  } >> "$GITHUB_OUTPUT"
}

approve_gated_runs() {
  # Pull_request runs on the bot branch queue as
  # approval-gated action_required runs; poll and approve as in
  # publish-sim-images.yml. A rejected approval is non-fatal:
  # the dispatched runs below still satisfy required checks.
  local gated_seen=0
  local empty_streak=0
  local attempt batch gated
  for ((attempt = 1; attempt <= APPROVE_POLL_ATTEMPTS; attempt++)); do
    batch=$(retry gh run list --repo "$GITHUB_REPOSITORY" --branch "$1" \
      --event pull_request --status action_required --json databaseId --jq '.[].databaseId' || true)
    if [ -z "$batch" ]; then
      empty_streak=$((empty_streak + 1))
      if { [ "$gated_seen" -eq 0 ] && [ "$empty_streak" -ge 3 ]; } ||
        { [ "$gated_seen" -eq 1 ] && [ "$empty_streak" -ge 2 ]; }; then
        break
      fi
      sleep "$APPROVE_IDLE_SECONDS"
      continue
    fi
    empty_streak=0
    gated_seen=1
    for gated in $batch; do
      retry gh api -X POST "repos/$GITHUB_REPOSITORY/actions/runs/$gated/approve" || true
    done
    sleep "$APPROVE_SEEN_SECONDS"
  done
}

dispatch_and_watch_checks() {
  # Dispatch ci/workflow-lint on the bump branch and gate on their
  # conclusions; returns non-zero when any run never appears or ends
  # non-success.
  local branch=$1
  local attempt started wf run_id conclusion failed=0
  started=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  retry gh workflow run ci.yml --repo "$GITHUB_REPOSITORY" --ref "$branch"
  retry gh workflow run workflow-lint.yml --repo "$GITHUB_REPOSITORY" --ref "$branch"
  for wf in ci.yml workflow-lint.yml; do
    run_id=""
    for ((attempt = 1; attempt <= RUN_POLL_ATTEMPTS; attempt++)); do
      sleep "$RUN_POLL_SECONDS"
      run_id=$(retry gh run list --repo "$GITHUB_REPOSITORY" --workflow "$wf" --branch "$branch" \
        --event workflow_dispatch --created ">=$started" --json databaseId --jq '.[0].databaseId // empty' || true)
      [ -n "$run_id" ] && break
    done
    if [ -z "$run_id" ]; then
      echo "$wf workflow_dispatch for $branch was not observed; the version-bump PR was left open" >> "$GITHUB_STEP_SUMMARY"
      exit 1
    fi
    echo "$wf run for $branch: ${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${run_id}"
    gh run watch --repo "$GITHUB_REPOSITORY" "$run_id" --interval 30 || true
    # An empty conclusion is a transient API failure, not a run
    # verdict: re-query until the API reports the conclusion.
    conclusion=""
    for ((attempt = 1; attempt <= CONCLUSION_POLL_ATTEMPTS; attempt++)); do
      conclusion=$(retry gh run view --repo "$GITHUB_REPOSITORY" "$run_id" \
        --json conclusion --jq '.conclusion // empty' || true)
      [ -n "$conclusion" ] && break
      sleep "$CONCLUSION_POLL_SECONDS"
    done
    conclusion="${conclusion:-unknown}"
    echo "$wf conclusion for $branch: $conclusion"
    if [ "$conclusion" != "success" ]; then
      failed=1
    fi
  done
  return "$failed"
}

push_bump_via_pr() {
  # No bypass actor is configured, so the pull_request rule
  # rejects a direct push. Route the bump commit through a pull
  # request instead — same self-approve + dispatched checks +
  # auto-merge flow as publish-sim-images.yml.
  local version=$1
  local attempt branch body pr_url merged merged_at
  echo "::warning::direct push to main rejected; routing the version bump through a pull request"
  branch="bot/release-bump-v${version}-${GITHUB_RUN_ID}"
  retry git push origin "HEAD:refs/heads/${branch}"
  body=$(printf '%s\n' \
    "Automated version bump for the Release workflow." \
    "" \
    "version: v${version}" \
    "workflow run: ${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}")
  pr_url=$(retry gh pr create \
    --repo "$GITHUB_REPOSITORY" \
    --base main \
    --head "$branch" \
    --title "Release v${version}: update version files" \
    --body "$body")
  echo "version-bump PR: $pr_url" >> "$GITHUB_STEP_SUMMARY"
  approve_gated_runs "$branch"
  if ! dispatch_and_watch_checks "$branch"; then
    echo "version-bump PR checks failed; the PR was left open for manual review" >> "$GITHUB_STEP_SUMMARY"
    exit 1
  fi
  # Arm auto-merge on the version-bump PR. Checks are already
  # green here so the merge lands immediately; arming failure
  # leaves the PR open for manual merge.
  if ! retry gh pr merge --repo "$GITHUB_REPOSITORY" --auto --squash --delete-branch "$pr_url"; then
    echo "version-bump PR auto-merge could not be armed; the PR was left open for manual review" >> "$GITHUB_STEP_SUMMARY"
    echo "::error::version-bump PR $pr_url was not auto-merged; merge it, then re-run Release with version=${version}."
    exit 1
  fi
  # Wait for the merge to land on main so the release SHA is the
  # real main tip, not the branch head.
  merged=false
  for ((attempt = 1; attempt <= MERGE_WAIT_ATTEMPTS; attempt++)); do
    merged_at=$(retry gh api "repos/$GITHUB_REPOSITORY/pulls/${pr_url##*/}" --jq '.merged_at // empty' || true)
    [ -n "$merged_at" ] && {
      merged=true
      break
    }
    sleep "$MERGE_WAIT_SECONDS"
  done
  if [ "$merged" != true ]; then
    echo "version-bump PR did not merge within the wait; it was left open" >> "$GITHUB_STEP_SUMMARY"
    echo "::error::merge $pr_url, then re-run Release with version=${version}."
    exit 1
  fi
  git fetch -q origin main
  echo "sha=$(git rev-parse origin/main)" >> "$GITHUB_OUTPUT"
}

main() {
  SET_VERSION="${SET_VERSION#v}"
  CURRENT=$(python3 -c 'import tomllib,sys;print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')
  if [ "$DRY_RUN" = "true" ]; then
    # Rehearsal: compute the would-be version and check the tag is
    # free, but write nothing — downstream jobs still exercise the
    # verify/install-smoke/build path against HEAD. --set equal to
    # CURRENT rehearses the consistency-check release below.
    if [ -n "$SET_VERSION" ] && [ "$SET_VERSION" = "$CURRENT" ]; then
      VERSION=$CURRENT
    elif [ -n "$SET_VERSION" ]; then
      VERSION=$(python3 scripts/bump_version.py --dry-run --set "$SET_VERSION")
    else
      VERSION=$(python3 scripts/bump_version.py --dry-run --bump "$BUMP")
    fi
    require_tag_free "$VERSION"
    echo "dry-run: v${VERSION} would release at $(git rev-parse HEAD) (bump=${BUMP}, current=${CURRENT})" >> "$GITHUB_STEP_SUMMARY"
    emit_outputs "$(git rev-parse HEAD)" "$VERSION"
    exit 0
  fi
  SKIP_COMMIT=false
  if [ -n "$SET_VERSION" ]; then
    if [ "$SET_VERSION" = "$CURRENT" ]; then
      VERSION="$CURRENT"
      python3 scripts/bump_version.py --dry-run --bump patch >/dev/null
      SKIP_COMMIT=true
    else
      VERSION=$(python3 scripts/bump_version.py --set "$SET_VERSION")
    fi
  else
    VERSION=$(python3 scripts/bump_version.py --bump "$BUMP")
  fi
  require_tag_free "$VERSION"
  if [ "$SKIP_COMMIT" = true ]; then
    echo "sha=$(git rev-parse HEAD)" >> "$GITHUB_OUTPUT"
  else
    git config user.name "github-actions[bot]"
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    git add plugins/sim/.plugin/plugin.json pyproject.toml \
      src/sim/__init__.py plugins/sim/skills/*/SKILL.md uv.lock
    git commit -m "Release v${VERSION}: update version files"
    if retry git push origin HEAD:main; then
      echo "sha=$(git rev-parse HEAD)" >> "$GITHUB_OUTPUT"
    else
      push_bump_via_pr "$VERSION"
    fi
  fi
  echo "version=${VERSION}" >> "$GITHUB_OUTPUT"
  echo "tag=v${VERSION}" >> "$GITHUB_OUTPUT"
}

main "$@"
