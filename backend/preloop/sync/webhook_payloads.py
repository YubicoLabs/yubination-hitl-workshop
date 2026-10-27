"""
Real webhook payload examples from GitLab, GitHub, and Jira.

These are used for testing and understanding the structure of webhook events.
"""

# GitLab Issue Hook - when an issue is opened
GITLAB_ISSUE_OPENED = {
    "object_kind": "issue",
    "event_type": "issue",
    "user": {
        "id": 1,
        "name": "Administrator",
        "username": "root",
        "avatar_url": "https://www.gravatar.com/avatar/avatar.jpg",
        "email": "admin@example.com",
    },
    "project": {
        "id": 1,
        "name": "Gitlab Test",
        "description": "Aut reprehenderit ut est.",
        "web_url": "http://example.com/gitlabhq/gitlab-test",
        "avatar_url": None,
        "git_ssh_url": "git@example.com:gitlabhq/gitlab-test.git",
        "git_http_url": "http://example.com/gitlabhq/gitlab-test.git",
        "namespace": "GitlabHQ",
        "visibility_level": 20,
        "path_with_namespace": "gitlabhq/gitlab-test",
        "default_branch": "master",
    },
    "object_attributes": {
        "id": 301,
        "title": "New API: create/update/delete file",
        "assignee_ids": [51],
        "assignee_id": 51,
        "author_id": 51,
        "project_id": 1,
        "created_at": "2013-12-03T17:15:43Z",
        "updated_at": "2013-12-03T17:15:43Z",
        "position": 0,
        "branch_name": None,
        "description": "Create new API for creating, updating and deleting files in a repository",
        "milestone_id": None,
        "state": "opened",
        "iid": 23,
        "url": "http://example.com/diaspora/issues/23",
        "action": "open",
        "labels": [
            {"id": 206, "title": "API", "color": "#ffffff", "project_id": 14},
            {"id": 207, "title": "Feature", "color": "#ff0000", "project_id": 14},
        ],
    },
    "labels": [
        {"id": 206, "title": "API", "color": "#ffffff", "project_id": 14},
        {"id": 207, "title": "Feature", "color": "#ff0000", "project_id": 14},
    ],
    "assignees": [
        {
            "id": 51,
            "name": "User1",
            "username": "user1",
            "avatar_url": "http://www.gravatar.com/avatar/avatar.jpg",
        }
    ],
    "changes": {},
}

# GitLab Issue Hook - when an issue is closed
GITLAB_ISSUE_CLOSED = {
    "object_kind": "issue",
    "event_type": "issue",
    "user": {
        "id": 1,
        "name": "Administrator",
        "username": "root",
        "avatar_url": "https://www.gravatar.com/avatar/avatar.jpg",
        "email": "admin@example.com",
    },
    "project": {
        "id": 1,
        "name": "Gitlab Test",
        "description": "Aut reprehenderit ut est.",
        "web_url": "http://example.com/gitlabhq/gitlab-test",
        "avatar_url": None,
        "git_ssh_url": "git@example.com:gitlabhq/gitlab-test.git",
        "git_http_url": "http://example.com/gitlabhq/gitlab-test.git",
        "namespace": "GitlabHQ",
        "visibility_level": 20,
        "path_with_namespace": "gitlabhq/gitlab-test",
        "default_branch": "master",
    },
    "object_attributes": {
        "id": 301,
        "title": "New API: create/update/delete file",
        "assignee_ids": [51],
        "assignee_id": 51,
        "author_id": 51,
        "project_id": 1,
        "created_at": "2013-12-03T17:15:43Z",
        "updated_at": "2013-12-03T17:15:43Z",
        "updated_by_id": 1,
        "position": 0,
        "branch_name": None,
        "description": "Create new API for creating, updating and deleting files in a repository",
        "milestone_id": None,
        "state": "closed",
        "iid": 23,
        "url": "http://example.com/diaspora/issues/23",
        "action": "close",
        "labels": [
            {"id": 206, "title": "API", "color": "#ffffff", "project_id": 14},
            {"id": 207, "title": "Feature", "color": "#ff0000", "project_id": 14},
        ],
    },
    "labels": [
        {"id": 206, "title": "API", "color": "#ffffff", "project_id": 14},
        {"id": 207, "title": "Feature", "color": "#ff0000", "project_id": 14},
    ],
    "assignees": [
        {
            "id": 51,
            "name": "User1",
            "username": "user1",
            "avatar_url": "http://www.gravatar.com/avatar/avatar.jpg",
        }
    ],
    "changes": {"state_id": {"previous": 1, "current": 2}},
}

# GitHub Issues Event - when an issue is opened
GITHUB_ISSUE_OPENED = {
    "action": "opened",
    "issue": {
        "id": 1,
        "node_id": "I_kwDOBj-m5s5OX0oZ",
        "number": 1,
        "title": "Test issue",
        "user": {
            "login": "octocat",
            "id": 1,
            "node_id": "MDQ6VXNlcjE=",
            "avatar_url": "https://github.com/images/error/octocat_happy.gif",
            "type": "User",
        },
        "labels": [
            {
                "id": 208045946,
                "node_id": "MDU6TGFiZWwyMDgwNDU5NDY=",
                "url": "https://api.github.com/repos/octocat/Hello-World/labels/bug",
                "name": "bug",
                "color": "d73a4a",
                "default": True,
            }
        ],
        "state": "open",
        "assignee": {
            "login": "octocat",
            "id": 1,
            "node_id": "MDQ6VXNlcjE=",
            "avatar_url": "https://github.com/images/error/octocat_happy.gif",
            "type": "User",
        },
        "assignees": [
            {
                "login": "octocat",
                "id": 1,
                "node_id": "MDQ6VXNlcjE=",
                "avatar_url": "https://github.com/images/error/octocat_happy.gif",
                "type": "User",
            }
        ],
        "milestone": None,
        "comments": 0,
        "created_at": "2023-11-01T08:14:12Z",
        "updated_at": "2023-11-01T08:14:12Z",
        "closed_at": None,
        "author_association": "OWNER",
        "body": "I'm having a problem with this.",
    },
    "repository": {
        "id": 1296269,
        "node_id": "MDEwOlJlcG9zaXRvcnkxMjk2MjY5",
        "name": "Hello-World",
        "full_name": "octocat/Hello-World",
        "owner": {
            "login": "octocat",
            "id": 1,
            "node_id": "MDQ6VXNlcjE=",
            "avatar_url": "https://github.com/images/error/octocat_happy.gif",
            "type": "User",
        },
    },
    "sender": {
        "login": "octocat",
        "id": 1,
        "node_id": "MDQ6VXNlcjE=",
        "avatar_url": "https://github.com/images/error/octocat_happy.gif",
        "type": "User",
    },
}

# GitHub Issues Event - when an issue is closed
GITHUB_ISSUE_CLOSED = {
    "action": "closed",
    "issue": {
        "id": 1,
        "node_id": "I_kwDOBj-m5s5OX0oZ",
        "number": 1,
        "title": "Test issue",
        "user": {
            "login": "octocat",
            "id": 1,
            "node_id": "MDQ6VXNlcjE=",
            "avatar_url": "https://github.com/images/error/octocat_happy.gif",
            "type": "User",
        },
        "labels": [
            {
                "id": 208045946,
                "node_id": "MDU6TGFiZWwyMDgwNDU5NDY=",
                "url": "https://api.github.com/repos/octocat/Hello-World/labels/bug",
                "name": "bug",
                "color": "d73a4a",
                "default": True,
            }
        ],
        "state": "closed",
        "assignee": {
            "login": "octocat",
            "id": 1,
            "node_id": "MDQ6VXNlcjE=",
            "avatar_url": "https://github.com/images/error/octocat_happy.gif",
            "type": "User",
        },
        "assignees": [
            {
                "login": "octocat",
                "id": 1,
                "node_id": "MDQ6VXNlcjE=",
                "avatar_url": "https://github.com/images/error/octocat_happy.gif",
                "type": "User",
            }
        ],
        "milestone": None,
        "comments": 0,
        "created_at": "2023-11-01T08:14:12Z",
        "updated_at": "2023-11-01T08:15:30Z",
        "closed_at": "2023-11-01T08:15:30Z",
        "author_association": "OWNER",
        "body": "I'm having a problem with this.",
    },
    "repository": {
        "id": 1296269,
        "node_id": "MDEwOlJlcG9zaXRvcnkxMjk2MjY5",
        "name": "Hello-World",
        "full_name": "octocat/Hello-World",
        "owner": {
            "login": "octocat",
            "id": 1,
            "node_id": "MDQ6VXNlcjE=",
            "avatar_url": "https://github.com/images/error/octocat_happy.gif",
            "type": "User",
        },
    },
    "sender": {
        "login": "octocat",
        "id": 1,
        "node_id": "MDQ6VXNlcjE=",
        "avatar_url": "https://github.com/images/error/octocat_happy.gif",
        "type": "User",
    },
}

# Jira Issue Created Event
JIRA_ISSUE_CREATED = {
    "timestamp": 1699012345000,
    "webhookEvent": "jira:issue_created",
    "issue_event_type_name": "issue_created",
    "user": {
        "self": "https://your-domain.atlassian.net/rest/api/2/user?accountId=123",
        "accountId": "5b10a2844c20165700ede21g",
        "accountType": "atlassian",
        "emailAddress": "user@example.com",
        "avatarUrls": {
            "48x48": "https://avatar-management--avatars.us-west-2.prod.public.atl-paas.net/123/48"
        },
        "displayName": "User Name",
        "active": True,
        "timeZone": "America/New_York",
        "locale": "en_US",
    },
    "issue": {
        "id": "10001",
        "self": "https://your-domain.atlassian.net/rest/api/2/issue/10001",
        "key": "TEST-1",
        "fields": {
            "issuetype": {
                "self": "https://your-domain.atlassian.net/rest/api/2/issuetype/10001",
                "id": "10001",
                "description": "A task that needs to be done.",
                "iconUrl": "https://your-domain.atlassian.net/secure/viewavatar?size=xsmall&avatarId=10318&avatarType=issuetype",
                "name": "Task",
                "subtask": False,
            },
            "project": {
                "self": "https://your-domain.atlassian.net/rest/api/2/project/10000",
                "id": "10000",
                "key": "TEST",
                "name": "Test Project",
                "projectTypeKey": "software",
            },
            "created": "2023-11-03T12:05:45.123+0000",
            "priority": {
                "self": "https://your-domain.atlassian.net/rest/api/2/priority/3",
                "iconUrl": "https://your-domain.atlassian.net/images/icons/priorities/medium.svg",
                "name": "Medium",
                "id": "3",
            },
            "labels": ["backend", "api"],
            "assignee": {
                "self": "https://your-domain.atlassian.net/rest/api/2/user?accountId=123",
                "accountId": "5b10a2844c20165700ede21g",
                "emailAddress": "assignee@example.com",
                "avatarUrls": {
                    "48x48": "https://avatar-management--avatars.us-west-2.prod.public.atl-paas.net/123/48"
                },
                "displayName": "Assignee Name",
                "active": True,
                "timeZone": "America/New_York",
            },
            "updated": "2023-11-03T12:05:45.123+0000",
            "status": {
                "self": "https://your-domain.atlassian.net/rest/api/2/status/10000",
                "description": "",
                "iconUrl": "https://your-domain.atlassian.net/",
                "name": "To Do",
                "id": "10000",
                "statusCategory": {
                    "self": "https://your-domain.atlassian.net/rest/api/2/statuscategory/2",
                    "id": 2,
                    "key": "new",
                    "colorName": "blue-gray",
                    "name": "To Do",
                },
            },
            "summary": "New issue created",
            "creator": {
                "self": "https://your-domain.atlassian.net/rest/api/2/user?accountId=123",
                "accountId": "5b10a2844c20165700ede21g",
                "emailAddress": "creator@example.com",
                "avatarUrls": {
                    "48x48": "https://avatar-management--avatars.us-west-2.prod.public.atl-paas.net/123/48"
                },
                "displayName": "Creator Name",
                "active": True,
                "timeZone": "America/New_York",
            },
            "reporter": {
                "self": "https://your-domain.atlassian.net/rest/api/2/user?accountId=123",
                "accountId": "5b10a2844c20165700ede21g",
                "emailAddress": "reporter@example.com",
                "avatarUrls": {
                    "48x48": "https://avatar-management--avatars.us-west-2.prod.public.atl-paas.net/123/48"
                },
                "displayName": "Reporter Name",
                "active": True,
                "timeZone": "America/New_York",
            },
        },
    },
}
