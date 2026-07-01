#!/usr/bin/env bash
set -eu

usage() {
  cat <<'USAGE'
Usage:
  scripts/run-jira-mcp-docker.sh [options]

Runs the existing mcp-atlassian Docker MCP server with framework guardrails.
The wrapper is read-only by default and passes Jira credentials through Docker
environment variables or an env file.

Options:
  --env-file <path>    Env file for Docker. Defaults to mcp/env/jira-mcp.env when present.
  --image <image>      Docker image. Defaults to ghcr.io/sooperset/mcp-atlassian:latest.
  --allow-writes       Do not force READ_ONLY_MODE=true. Requires human approval by policy.
  --dry-run            Print the docker command without executing it.
  --check-access       Verify Jira credentials with a read-only REST call, without Docker or agents.
  --issue <KEY>        With --check-access, also verify read access to a specific Jira issue.
  --get-issue <KEY>    Print a read-only Jira issue JSON payload for agent use.
  --fetch-epic-story-pack <KEY>
                       Resolve the issue's epic when possible, fetch sibling stories,
                       and write a normalized Markdown pack under .mana/.
  --output <path>      Output path for --fetch-epic-story-pack.
  --help               Show this help.

Required Jira configuration:
  Jira Server/Data Center:
    JIRA_URL=https://jira.your-company.com
    JIRA_PERSONAL_TOKEN=...
    # JIRA_ACCESS_TOKEN is accepted as an alias.

  Jira Cloud:
    JIRA_URL=https://your-company.atlassian.net
    JIRA_USERNAME=your.email@company.com
    JIRA_API_TOKEN=...

Optional restrictions:
  JIRA_PROJECTS_FILTER=PROJ,DEV
  TOOLSETS=default
  ENABLED_TOOLS=jira_get_issue,jira_search,jira_search_fields
USAGE
}

root="$(cd "$(dirname "$0")/.." && pwd)"
image="${MCP_ATLASSIAN_IMAGE:-ghcr.io/sooperset/mcp-atlassian:latest}"
env_file=""
allow_writes=false
dry_run=false
check_access=false
check_issue=""
get_issue=""
fetch_epic_story_pack=""
epic_story_pack_output=""

if [ -f "$root/mcp/env/jira-mcp.env" ]; then
  env_file="$root/mcp/env/jira-mcp.env"
fi

while [ "$#" -gt 0 ]; do
  case "$1" in
    --env-file)
      env_file="${2:-}"
      [ -n "$env_file" ] || { echo "ERROR: --env-file requires a path" >&2; exit 2; }
      shift 2
      ;;
    --image)
      image="${2:-}"
      [ -n "$image" ] || { echo "ERROR: --image requires an image" >&2; exit 2; }
      shift 2
      ;;
    --allow-writes)
      allow_writes=true
      shift
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    --check-access)
      check_access=true
      shift
      ;;
    --issue|--jira-key|--jira-issue)
      check_issue="${2:-}"
      [ -n "$check_issue" ] || { echo "ERROR: $1 requires a Jira issue key" >&2; exit 2; }
      shift 2
      ;;
    --get-issue|--read-issue)
      get_issue="${2:-}"
      [ -n "$get_issue" ] || { echo "ERROR: $1 requires a Jira issue key" >&2; exit 2; }
      shift 2
      ;;
    --fetch-epic-story-pack)
      fetch_epic_story_pack="${2:-}"
      [ -n "$fetch_epic_story_pack" ] || { echo "ERROR: $1 requires a Jira issue key" >&2; exit 2; }
      shift 2
      ;;
    --output)
      epic_story_pack_output="${2:-}"
      [ -n "$epic_story_pack_output" ] || { echo "ERROR: --output requires a path" >&2; exit 2; }
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -n "$env_file" ] && [ ! -f "$env_file" ]; then
  echo "ERROR: env file not found: $env_file" >&2
  exit 2
fi
if [ -n "$check_issue" ] && [ "$check_access" != true ]; then
  echo "ERROR: --issue requires --check-access. Use --get-issue <KEY> to read a Jira story." >&2
  exit 2
fi
if [ "$check_access" = true ] && [ -n "$get_issue" ]; then
  echo "ERROR: choose either --check-access or --get-issue, not both" >&2
  exit 2
fi
if [ "$check_access" = true ] && [ -n "$fetch_epic_story_pack" ]; then
  echo "ERROR: choose either --check-access or --fetch-epic-story-pack, not both" >&2
  exit 2
fi
if [ -n "$get_issue" ] && [ -n "$fetch_epic_story_pack" ]; then
  echo "ERROR: choose either --get-issue or --fetch-epic-story-pack, not both" >&2
  exit 2
fi
if [ -n "$epic_story_pack_output" ] && [ -z "$fetch_epic_story_pack" ]; then
  echo "ERROR: --output requires --fetch-epic-story-pack" >&2
  exit 2
fi

load_jira_env() {
  if [ -n "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$env_file"
    set +a
  fi
}

prepare_jira_curl_config() {
  if ! command -v curl >/dev/null 2>&1; then
    echo "ERROR: curl is required for Jira REST commands" >&2
    exit 1
  fi

  jira_url="${JIRA_URL:-}"
  jira_url="${jira_url%/}"
  if [ -z "$jira_url" ]; then
    echo "ERROR: JIRA_URL is required for Jira REST commands" >&2
    exit 2
  fi
  personal_token="${JIRA_PERSONAL_TOKEN:-${JIRA_ACCESS_TOKEN:-}}"
  auth_mode=""
  is_atlassian_cloud=false
  case "$jira_url" in
    *".atlassian.net") is_atlassian_cloud=true ;;
  esac

  curl_config="$(mktemp)"
  trap 'rm -f "$curl_config"' EXIT
  chmod 600 "$curl_config"
  {
    printf '%s\n' 'silent'
    printf '%s\n' 'show-error'
    printf '%s\n' 'header = "Accept: application/json"'
    if [ "${JIRA_SSL_VERIFY:-true}" = "false" ]; then
      printf '%s\n' 'insecure'
    fi
    if [ "$is_atlassian_cloud" = true ] && [ -n "${JIRA_USERNAME:-}" ] && [ -n "${JIRA_API_TOKEN:-}" ]; then
      auth_mode="basic"
      basic_auth="$(printf '%s:%s' "$JIRA_USERNAME" "$JIRA_API_TOKEN" | base64 | tr -d '\n')"
      printf 'header = "Authorization: Basic %s"\n' "$basic_auth"
    elif [ -n "$personal_token" ]; then
      auth_mode="bearer"
      printf 'header = "Authorization: Bearer %s"\n' "$personal_token"
    elif [ -n "${JIRA_USERNAME:-}" ] && [ -n "${JIRA_API_TOKEN:-}" ]; then
      auth_mode="basic"
      basic_auth="$(printf '%s:%s' "$JIRA_USERNAME" "$JIRA_API_TOKEN" | base64 | tr -d '\n')"
      printf 'header = "Authorization: Basic %s"\n' "$basic_auth"
    else
      echo "ERROR: JIRA_PERSONAL_TOKEN, JIRA_ACCESS_TOKEN, or JIRA_USERNAME/JIRA_API_TOKEN is required for Jira REST commands" >&2
      exit 2
    fi
  } > "$curl_config"

  echo "Jira access target: $jira_url" >&2
  echo "Jira access auth mode: $auth_mode" >&2
  if [ "$is_atlassian_cloud" = true ] && [ "$auth_mode" = "bearer" ]; then
    echo "WARN: Atlassian Cloud site REST APIs usually require JIRA_USERNAME plus JIRA_API_TOKEN; Bearer tokens against *.atlassian.net commonly return 403." >&2
  fi
}

if [ "$check_access" = true ]; then
  load_jira_env
  prepare_jira_curl_config

  myself_endpoint="$jira_url/rest/api/2/myself"
  status="$(curl --config "$curl_config" --output /dev/null --write-out "%{http_code}" "$myself_endpoint" || true)"
  auth_check_passed=false
  case "$status" in
    200)
      echo "Jira auth check passed: authenticated read access to $jira_url"
      auth_check_passed=true
      ;;
    401|403)
      if [ -n "$check_issue" ]; then
        echo "WARN: Jira /myself check returned HTTP $status; checking issue $check_issue directly." >&2
      else
        echo "ERROR: Jira access check failed with HTTP $status: credentials rejected or insufficient permission" >&2
        exit 1
      fi
      ;;
    000)
      echo "ERROR: Jira access check failed: could not reach $jira_url" >&2
      exit 1
      ;;
    *)
      echo "ERROR: Jira access check failed with HTTP $status" >&2
      exit 1
      ;;
  esac

  if [ -n "$check_issue" ]; then
    issue_endpoint="$jira_url/rest/api/2/issue/$check_issue"
    echo "Jira issue check endpoint: $issue_endpoint"
    issue_status="$(curl --config "$curl_config" --output /dev/null --write-out "%{http_code}" "$issue_endpoint" || true)"
    case "$issue_status" in
      200)
        echo "Jira issue check passed: read access to $check_issue"
        echo "Jira access check passed"
        exit 0
        ;;
      401|403)
        echo "ERROR: Jira issue check failed for $check_issue with HTTP $issue_status: insufficient permission" >&2
        exit 1
        ;;
      404)
        echo "ERROR: Jira issue check failed for $check_issue with HTTP 404: issue not found or not visible" >&2
        exit 1
        ;;
      000)
        echo "ERROR: Jira issue check failed: could not reach $jira_url" >&2
        exit 1
        ;;
      *)
        echo "ERROR: Jira issue check failed for $check_issue with HTTP $issue_status" >&2
        exit 1
        ;;
    esac
  fi

  if [ "$auth_check_passed" != true ]; then
    echo "ERROR: Jira access check failed" >&2
    exit 1
  fi
  echo "Jira access check passed"
  exit 0
fi

if [ -n "$get_issue" ]; then
  load_jira_env
  prepare_jira_curl_config
  fields="summary,description,issuetype,status,priority,assignee,reporter,labels,components,fixVersions,versions,comment,issuelinks,parent,subtasks,created,updated,resolution"
  issue_endpoint="$jira_url/rest/api/2/issue/$get_issue?fields=$fields&expand=renderedFields"
  response_body="$(mktemp)"
  trap 'rm -f "$curl_config" "$response_body"' EXIT
  echo "Jira issue read target: $jira_url" >&2
  echo "Jira issue read auth mode: $auth_mode" >&2
  echo "Jira issue read key: $get_issue" >&2
  issue_status="$(curl --config "$curl_config" --output "$response_body" --write-out "%{http_code}" "$issue_endpoint" || true)"
  case "$issue_status" in
    200)
      cat "$response_body"
      ;;
    401|403)
      echo "ERROR: Jira issue read failed for $get_issue with HTTP $issue_status: insufficient permission" >&2
      exit 1
      ;;
    404)
      echo "ERROR: Jira issue read failed for $get_issue with HTTP 404: issue not found or not visible" >&2
      exit 1
      ;;
    000)
      echo "ERROR: Jira issue read failed: could not reach $jira_url" >&2
      exit 1
      ;;
    *)
      echo "ERROR: Jira issue read failed for $get_issue with HTTP $issue_status" >&2
      exit 1
      ;;
  esac
  printf '\n'
  exit 0
fi

if [ -n "$fetch_epic_story_pack" ]; then
  load_jira_env
  prepare_jira_curl_config
  if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required for --fetch-epic-story-pack Markdown normalization" >&2
    exit 1
  fi

  JIRA_URL="$jira_url" python3 - "$fetch_epic_story_pack" "$epic_story_pack_output" <<'PY'
import base64
import datetime as dt
import html
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request

source_key = sys.argv[1].strip().upper()
requested_output = sys.argv[2].strip()
jira_url = os.environ["JIRA_URL"].rstrip("/")


def auth_header():
    if jira_url.endswith(".atlassian.net") and os.environ.get("JIRA_USERNAME") and os.environ.get("JIRA_API_TOKEN"):
        token = base64.b64encode(
            f"{os.environ['JIRA_USERNAME']}:{os.environ['JIRA_API_TOKEN']}".encode()
        ).decode()
        return "Basic " + token
    personal = os.environ.get("JIRA_PERSONAL_TOKEN") or os.environ.get("JIRA_ACCESS_TOKEN")
    if personal:
        return "Bearer " + personal
    if os.environ.get("JIRA_USERNAME") and os.environ.get("JIRA_API_TOKEN"):
        token = base64.b64encode(
            f"{os.environ['JIRA_USERNAME']}:{os.environ['JIRA_API_TOKEN']}".encode()
        ).decode()
        return "Basic " + token
    raise SystemExit("ERROR: Jira credentials are required")


AUTH = auth_header()
FIELDS = ",".join(
    [
        "summary",
        "description",
        "issuetype",
        "status",
        "priority",
        "assignee",
        "reporter",
        "labels",
        "components",
        "fixVersions",
        "versions",
        "comment",
        "issuelinks",
        "parent",
        "subtasks",
        "created",
        "updated",
        "resolution",
    ]
)


def request_json(path, params=None):
    query = ""
    if params:
        query = "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        jira_url + path + query,
        headers={"Accept": "application/json", "Authorization": AUTH},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as res:
            return json.load(res)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"ERROR: Jira request failed HTTP {exc.code}: {body[:500]}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"ERROR: Jira request failed: {exc.reason}")


def issue(key):
    return request_json(
        f"/rest/api/2/issue/{urllib.parse.quote(key)}",
        {"fields": FIELDS, "expand": "renderedFields"},
    )


def search(jql):
    return request_json(
        "/rest/api/2/search",
        {"jql": jql, "fields": FIELDS, "expand": "renderedFields", "maxResults": "100"},
    )


def field(data, name, default=None):
    return (data.get("fields") or {}).get(name, default)


def name(value):
    if not value:
        return ""
    return value.get("displayName") or value.get("name") or value.get("key") or ""


def issue_type(data):
    return name(field(data, "issuetype")).lower()


def text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        cleaned = html.unescape(re.sub(r"<[^>]+>", " ", value))
        return re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if isinstance(value, dict):
        if value.get("type") == "doc" and "content" in value:
            return "\n".join(filter(None, (text(item) for item in value.get("content", []))))
        parts = []
        for key in ("text", "content", "value", "name", "displayName"):
            if key in value:
                parts.append(text(value[key]))
        return "\n".join(filter(None, parts)).strip()
    if isinstance(value, list):
        return "\n".join(filter(None, (text(item) for item in value))).strip()
    return str(value)


def wrapped(value):
    value = text(value)
    if not value:
        return "_Not provided._"
    paragraphs = []
    for para in value.splitlines():
        para = para.strip()
        if not para:
            paragraphs.append("")
        elif para.startswith(("-", "*", "#", "|", ">")):
            paragraphs.append(para)
        else:
            paragraphs.append(textwrap.fill(para, width=100))
    return "\n".join(paragraphs).strip()


def bullet_list(values):
    values = [v for v in values if v]
    if not values:
        return "- _None recorded._"
    return "\n".join(f"- {v}" for v in values)


def story_block(data, heading_level=3):
    f = data.get("fields") or {}
    key = data.get("key", "")
    summary = f.get("summary") or ""
    parent = f.get("parent") or {}
    comments = ((f.get("comment") or {}).get("comments") or [])[-3:]
    links = []
    for link in f.get("issuelinks") or []:
        inward = (link.get("inwardIssue") or {}).get("key")
        outward = (link.get("outwardIssue") or {}).get("key")
        link_type = (link.get("type") or {}).get("name") or "link"
        target = inward or outward
        if target:
            links.append(f"{link_type}: {target}")
    rendered = data.get("renderedFields") or {}
    desc = rendered.get("description") or f.get("description")
    lines = [
        f"{'#' * heading_level} {key} - {summary}".rstrip(),
        "",
        f"- Type: `{name(f.get('issuetype')) or 'unknown'}`",
        f"- Status: `{name(f.get('status')) or 'unknown'}`",
        f"- Priority: `{name(f.get('priority')) or 'unknown'}`",
        f"- Assignee: `{name(f.get('assignee')) or 'unassigned'}`",
        f"- Reporter: `{name(f.get('reporter')) or 'unknown'}`",
        f"- Parent epic: `{parent.get('key') or 'not recorded'}`",
        f"- Updated: `{f.get('updated') or 'unknown'}`",
        f"- Components: `{', '.join(c.get('name', '') for c in f.get('components') or []) or 'none'}`",
        f"- Labels: `{', '.join(f.get('labels') or []) or 'none'}`",
        "",
        "#### Description",
        "",
        wrapped(desc),
        "",
        "#### Linked Issues",
        "",
        bullet_list(links),
        "",
        "#### Subtasks",
        "",
        bullet_list(
            f"{s.get('key')} - {(s.get('fields') or {}).get('summary', '')}"
            for s in f.get("subtasks") or []
        ),
        "",
        "#### Recent Comments",
        "",
    ]
    if comments:
        for comment in comments:
            body = text(comment.get("body"))
            lines.extend(
                [
                    f"- {name(comment.get('author')) or 'unknown'} at `{comment.get('updated') or comment.get('created')}`:",
                    "",
                    textwrap.indent(wrapped(body), "  "),
                    "",
                ]
            )
    else:
        lines.append("- _None fetched._")
    return "\n".join(lines).rstrip()


source = issue(source_key)
source_is_epic = issue_type(source) == "epic"
parent = field(source, "parent") or {}
epic_key = source_key if source_is_epic else (parent.get("key") or "")
evidence_gaps = []

if epic_key:
    try:
        results = search(
            f'issuekey = {epic_key} OR parent = {epic_key} OR "Epic Link" = {epic_key} ORDER BY key ASC'
        )
    except SystemExit:
        results = search(f"issuekey = {epic_key} OR parent = {epic_key} ORDER BY key ASC")
    issues = results.get("issues") or []
else:
    issues = [source]
    epic_key = source_key
    evidence_gaps.append(
        "Could not resolve parent epic from the source issue. Pack contains the source issue only."
    )

seen = {}
for item in issues:
    seen[item.get("key")] = item
if source_key not in seen:
    seen[source_key] = source
issues = [seen[k] for k in sorted(seen)]
epic = seen.get(epic_key)
stories = [i for i in issues if i.get("key") != epic_key]

if not stories:
    evidence_gaps.append("No sibling stories were returned by Jira search for the resolved epic.")

output = requested_output
if not output:
    output = os.path.join(
        ".mana",
        "features",
        epic_key,
        "evidence",
        "jira",
        "epic-story-pack.md",
    )
os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

fetched_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
content = [
    f"# Epic Story Pack: {epic_key}",
    "",
    "## Fetch Manifest",
    "",
    f"- Source mode: `jira-readonly-markdown-cache`",
    f"- Fetched at: `{fetched_at}`",
    f"- Jira base: `{jira_url}`",
    f"- Source issue: `{source_key}`",
    f"- Resolved epic: `{epic_key}`",
    f"- Issues fetched: `{', '.join(i.get('key', '') for i in issues)}`",
    f"- Raw JSON stored: `no`",
    "",
    "## Epic",
    "",
    story_block(epic or source, 3),
    "",
    "## Stories",
    "",
]
if stories:
    content.extend(story_block(story, 3) + "\n" for story in stories)
else:
    content.append("_No sibling stories fetched._\n")

content.extend(
    [
        "## Partitioning Review Notes",
        "",
        "Use `epic-story-partitioning` to check:",
        "",
        "- whether each story owns one coherent business slice;",
        "- whether stories overlap in behavior, data ownership, acceptance criteria, or delivery scope;",
        "- whether the epic goal has uncovered gaps;",
        "- whether dependencies or ordering constraints are explicit;",
        "- whether any story is too large, too technical, or not independently testable.",
        "",
        "## Evidence Gaps",
        "",
        bullet_list(evidence_gaps),
        "",
    ]
)

with open(output, "w", encoding="utf-8") as fh:
    fh.write("\n".join(content).rstrip() + "\n")

print(f"Jira epic story pack written: {output}")
print(f"Resolved epic: {epic_key}")
print(f"Issues fetched: {len(issues)}")
PY
  exit 0
fi

cmd=(docker run --rm -i)

if [ -n "$env_file" ]; then
  cmd+=(--env-file "$env_file")
else
  cmd+=(
    -e JIRA_URL
    -e JIRA_USERNAME
    -e JIRA_API_TOKEN
    -e JIRA_PERSONAL_TOKEN
    -e JIRA_ACCESS_TOKEN
    -e JIRA_SSL_VERIFY
    -e JIRA_PROJECTS_FILTER
    -e TOOLSETS
    -e ENABLED_TOOLS
    -e MCP_VERBOSE
  )
fi

if [ "$allow_writes" = true ]; then
  cmd+=(-e READ_ONLY_MODE=false)
else
  cmd+=(-e READ_ONLY_MODE=true)
fi

cmd+=("$image")

if [ "$dry_run" = true ]; then
  printf '%q ' "${cmd[@]}"
  printf '\n'
  exit 0
fi

exec "${cmd[@]}"
