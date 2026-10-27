"""
Event type normalization for webhook events.

Converts tracker-specific event names (GitHub, GitLab, Jira) to normalized event types
that can be used for flow triggers.

Also extracts filter-relevant fields from webhook payloads to enable
conditional flow triggering based on author, labels, assignee, etc.
"""

from typing import Dict, Any


# Mapping of GitLab webhook events to normalized event types
GITLAB_EVENT_MAP: Dict[str, str] = {
    "Issue Hook": "issue_opened",
    "Note Hook": "comment_created",
    "Merge Request Hook": "merge_request_opened",
    "Push Hook": "push",
    "Tag Push Hook": "tag_push",
    "Pipeline Hook": "pipeline",
    "Job Hook": "job",
    "Deployment Hook": "deployment",
    "Release Hook": "release",
}

# Mapping of GitHub webhook events to normalized event types
GITHUB_EVENT_MAP: Dict[str, str] = {
    "issues": "issue_opened",
    "issue_comment": "comment_created",
    "pull_request": "pull_request_opened",
    "push": "push",
    "release": "release",
    "deployment_status": "deployment",
}

# Mapping of Jira webhook events to normalized event types
JIRA_EVENT_MAP: Dict[str, str] = {
    "jira:issue_created": "issue_opened",
    "jira:issue_updated": "issue_updated",
    "jira:issue_deleted": "issue_deleted",
    "comment_created": "comment_created",
    "comment_updated": "comment_updated",
    "comment_deleted": "comment_deleted",
}


def normalize_event_type(
    tracker_type: str, raw_event_type: str, payload: dict = None
) -> str:
    """
    Normalize a tracker-specific event type to a standard event type.

    Args:
        tracker_type: The tracker type (e.g., 'gitlab', 'github', 'jira')
        raw_event_type: The raw event type from the webhook
        payload: Optional webhook payload for additional context

    Returns:
        Normalized event type string
    """
    tracker_type_lower = tracker_type.lower()

    if tracker_type_lower == "gitlab":
        # GitLab events - use the event type from header
        normalized = GITLAB_EVENT_MAP.get(raw_event_type)

        # For GitLab, we can refine based on action in payload
        if normalized == "issue_opened" and payload:
            action = payload.get("object_attributes", {}).get("action")
            if action == "update":
                normalized = "issue_updated"
            elif action == "close":
                normalized = "issue_closed"
            elif action == "reopen":
                normalized = "issue_reopened"
        elif normalized == "merge_request_opened" and payload:
            action = payload.get("object_attributes", {}).get("action")
            if action == "update":
                normalized = "merge_request_updated"
            elif action == "close":
                normalized = "merge_request_closed"
            elif action == "reopen":
                normalized = "merge_request_reopened"
            elif action == "merge":
                normalized = "merge_request_merged"
            elif action == "approved":
                normalized = "merge_request_approved"

        return normalized or raw_event_type

    elif tracker_type_lower == "github":
        # GitHub events - use the event type from header
        normalized = GITHUB_EVENT_MAP.get(raw_event_type)

        # For GitHub, we can refine based on action in payload
        if normalized and payload:
            action = payload.get("action")
            if action:
                # Map specific actions
                if normalized == "issue_opened":
                    if action == "opened":
                        pass  # Keep as issue_opened
                    elif action == "edited":
                        normalized = "issue_updated"
                    elif action == "closed":
                        normalized = "issue_closed"
                    elif action == "reopened":
                        normalized = "issue_reopened"
                    elif action == "labeled":
                        normalized = "issue_labeled"
                    elif action == "unlabeled":
                        normalized = "issue_unlabeled"
                    elif action == "assigned":
                        normalized = "issue_assigned"
                    elif action == "unassigned":
                        normalized = "issue_unassigned"
                elif normalized == "pull_request_opened":
                    if action == "opened":
                        pass  # Keep as pull_request_opened
                    elif action == "edited":
                        # Title, description, or base branch changed
                        normalized = "pull_request_updated"
                    elif action == "synchronize":
                        # New commits pushed to the PR - also treated as "updated"
                        # This matches user expectation that "PR Updated" includes new commits
                        normalized = "pull_request_updated"
                    elif action == "closed":
                        normalized = "pull_request_closed"
                    elif action == "reopened":
                        normalized = "pull_request_reopened"
                    elif action == "review_requested":
                        normalized = "pull_request_review_requested"
                    elif action == "ready_for_review":
                        normalized = "pull_request_ready_for_review"
                elif normalized == "comment_created":
                    if action == "created":
                        pass  # Keep as comment_created
                    elif action == "edited":
                        normalized = "comment_updated"
                    elif action == "deleted":
                        normalized = "comment_deleted"

        return normalized or raw_event_type

    elif tracker_type_lower == "jira":
        # Jira events - already normalized in webhook
        return JIRA_EVENT_MAP.get(raw_event_type, raw_event_type)

    # Unknown tracker type - return as-is
    return raw_event_type


def extract_filter_fields(
    tracker_type: str, raw_event_type: str, payload: dict
) -> Dict[str, Any]:
    """
    Extract filter-relevant fields from webhook payload.

    Returns a dictionary with standardized fields that can be used in trigger_config:
    - author: Username of the person who created the issue/PR
    - assignee: Username of the assigned person (or list of usernames)
    - reviewer: Username of requested reviewer (or list of usernames) for PRs/MRs
    - labels: List of label names
    - milestone: Milestone name
    - priority: Priority level (for Jira)
    - state: Current state/status
    - action: Specific action that triggered the event

    Args:
        tracker_type: The tracker type (e.g., 'gitlab', 'github', 'jira')
        raw_event_type: The raw event type from the webhook
        payload: The webhook payload

    Returns:
        Dictionary with extracted filter fields
    """
    tracker_type_lower = tracker_type.lower()
    filter_fields: Dict[str, Any] = {}

    if tracker_type_lower == "gitlab":
        # Extract from object_attributes for issues/MRs
        obj_attrs = payload.get("object_attributes", {})
        user = payload.get("user", {})

        # Author
        filter_fields["author"] = user.get("username")

        # Assignees (can be multiple in GitLab)
        assignees = payload.get("assignees", [])
        if assignees:
            filter_fields["assignee"] = [a.get("username") for a in assignees]
        elif obj_attrs.get("assignee_id"):
            # Single assignee fallback
            assignee = payload.get("assignee")
            if assignee:
                filter_fields["assignee"] = assignee.get("username")

        # Labels
        labels = payload.get("labels", [])
        if labels:
            filter_fields["labels"] = [label.get("title") for label in labels]

        # Milestone
        milestone = obj_attrs.get("milestone")
        if milestone:
            filter_fields["milestone"] = milestone.get("title")

        # State and action
        filter_fields["state"] = obj_attrs.get("state")
        filter_fields["action"] = obj_attrs.get("action")

        # Merge Request specific fields
        if "merge_request" in payload.get("object_kind", ""):
            # Reviewers (for merge requests)
            reviewers = payload.get("reviewers", [])
            if reviewers:
                filter_fields["reviewer"] = [r.get("username") for r in reviewers]

            # Check if MR is merged
            filter_fields["merged"] = (
                obj_attrs.get("merge_status") == "merged"
                or obj_attrs.get("state") == "merged"
            )

            # Draft status (work_in_progress)
            filter_fields["draft"] = obj_attrs.get(
                "work_in_progress", False
            ) or obj_attrs.get("draft", False)

            # Merge status (can_merge, cannot_merge, etc.)
            filter_fields["merge_status"] = obj_attrs.get("merge_status")

            # Detailed state includes info about approval
            filter_fields["detailed_merge_status"] = obj_attrs.get(
                "detailed_merge_status"
            )

    elif tracker_type_lower == "github":
        # GitHub structure varies by event type
        action = payload.get("action")
        filter_fields["action"] = action

        # Extract from issue object
        if "issue" in payload:
            issue = payload["issue"]

            # Author
            user = issue.get("user", {})
            filter_fields["author"] = user.get("login")

            # Assignees (can be multiple in GitHub)
            assignees = issue.get("assignees", [])
            if assignees:
                filter_fields["assignee"] = [a.get("login") for a in assignees]

            # Labels
            labels = issue.get("labels", [])
            if labels:
                filter_fields["labels"] = [label.get("name") for label in labels]

            # Milestone
            milestone = issue.get("milestone")
            if milestone:
                filter_fields["milestone"] = milestone.get("title")

            # State
            filter_fields["state"] = issue.get("state")

        # Extract from pull_request object
        elif "pull_request" in payload:
            pr = payload["pull_request"]

            # Author
            user = pr.get("user", {})
            filter_fields["author"] = user.get("login")

            # Assignees
            assignees = pr.get("assignees", [])
            if assignees:
                filter_fields["assignee"] = [a.get("login") for a in assignees]

            # Reviewers (requested reviewers for pull requests)
            requested_reviewers = pr.get("requested_reviewers", [])
            if requested_reviewers:
                filter_fields["reviewer"] = [
                    r.get("login") for r in requested_reviewers
                ]

            # For review_requested action, also check top-level requested_reviewer
            # This is the specific reviewer that was just added (not in the PR object)
            if action == "review_requested":
                top_level_reviewer = payload.get("requested_reviewer", {})
                if top_level_reviewer:
                    reviewer_login = top_level_reviewer.get("login")
                    if reviewer_login:
                        # Ensure reviewer list includes the just-added reviewer
                        if "reviewer" not in filter_fields:
                            filter_fields["reviewer"] = []
                        if reviewer_login not in filter_fields["reviewer"]:
                            filter_fields["reviewer"].append(reviewer_login)

            # Labels
            labels = pr.get("labels", [])
            if labels:
                filter_fields["labels"] = [label.get("name") for label in labels]

            # Milestone
            milestone = pr.get("milestone")
            if milestone:
                filter_fields["milestone"] = milestone.get("title")

            # State
            filter_fields["state"] = pr.get("state")

            # Pull Request specific fields
            # Merged status
            filter_fields["merged"] = pr.get("merged", False)

            # Draft status
            filter_fields["draft"] = pr.get("draft", False)

            # Mergeable status (can be merged)
            filter_fields["mergeable"] = pr.get("mergeable")

            # Merge state status (clean, dirty, unstable, blocked, etc.)
            filter_fields["mergeable_state"] = pr.get("mergeable_state")

        # Sender (who triggered the event)
        sender = payload.get("sender", {})
        filter_fields["sender"] = sender.get("login")

    elif tracker_type_lower == "jira":
        # Jira webhook structure
        issue = payload.get("issue", {})
        fields = issue.get("fields", {})
        user = payload.get("user", {})

        # Author/Creator
        creator = fields.get("creator", {})
        filter_fields["author"] = creator.get("displayName") or creator.get("accountId")

        # Reporter
        reporter = fields.get("reporter", {})
        filter_fields["reporter"] = reporter.get("displayName") or reporter.get(
            "accountId"
        )

        # Assignee
        assignee = fields.get("assignee")
        if assignee:
            filter_fields["assignee"] = assignee.get("displayName") or assignee.get(
                "accountId"
            )

        # Labels
        labels = fields.get("labels", [])
        if labels:
            filter_fields["labels"] = labels

        # Priority
        priority = fields.get("priority")
        if priority:
            filter_fields["priority"] = priority.get("name")

        # Status
        status = fields.get("status")
        if status:
            filter_fields["state"] = status.get("name")

        # Issue type
        issue_type = fields.get("issuetype")
        if issue_type:
            filter_fields["issue_type"] = issue_type.get("name")

        # User who triggered the event
        filter_fields["event_user"] = user.get("displayName") or user.get("accountId")

    return filter_fields
