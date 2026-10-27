"""Notification service for approval requests.

This module handles sending notifications through various channels:
- Email (Open Source)
- Mobile Push (Open Source)
- Slack (Open Source)
- Mattermost (Open Source)
- Webhook (Open Source)
"""

import asyncio
import json
import uuid
import logging
from typing import List, Dict, Any, Tuple

import httpx
from sqlalchemy.orm import Session

from preloop.models import models
from preloop.models.crud import notification_preferences

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending approval notifications."""

    def __init__(self, db: Session):
        """Initialize notification service.

        Args:
            db: Database session.
        """
        self.db = db

    async def notify_approval_request(
        self,
        approval_request: models.ApprovalRequest,
        approval_workflow: models.ApprovalWorkflow,
    ) -> Dict[str, Any]:
        """Send notifications for an approval request.

        Mobile-first strategy: push notifications are sent immediately, while
        email is delayed 15 seconds for users who also have push enabled.
        If the approval is resolved within those 15 seconds (e.g. via mobile),
        the email is skipped entirely. Users with only email enabled receive
        their email immediately.

        Args:
            approval_request: The approval request to notify about.
            approval_workflow: The approval workflow containing notification config.

        Returns:
            Dict with notification results per channel.
        """
        results = {}

        # Get list of approvers (expand teams to users)
        approver_user_ids = await self._get_approver_user_ids(approval_workflow)

        # Partition users by which notification channels they have enabled
        push_only, email_only, both = self._partition_users_by_channel(
            approver_user_ids
        )

        # 1. Send push notifications immediately to all push-enabled users
        push_targets = push_only + both
        if push_targets:
            try:
                result = await self._send_push_notifications(
                    approval_request, push_targets
                )
                results["mobile_push"] = result
            except Exception as e:
                logger.error(f"Failed to send push notifications: {str(e)}")
                results["mobile_push"] = {"success": False, "error": str(e)}

        # 2. Send email immediately to users who ONLY have email (no push)
        if email_only:
            try:
                result = await self._send_email_notifications(
                    approval_request, email_only
                )
                results["email_immediate"] = result
            except Exception as e:
                logger.error(f"Failed to send immediate email notifications: {str(e)}")
                results["email_immediate"] = {"success": False, "error": str(e)}

        # 3. Schedule delayed email for users with both push + email
        #    Email is sent after 15s only if the request is still pending
        if both:
            asyncio.create_task(
                self._send_delayed_email(
                    request_id=approval_request.id,
                    approval_request=approval_request,
                    user_ids=both,
                    delay_seconds=15,
                )
            )
            results["email_delayed"] = {
                "scheduled": len(both),
                "delay_seconds": 15,
            }

        # Send to workflow-configured channels (slack, mattermost, webhook)
        # based on what's present in channel_configs
        channel_configs = approval_workflow.channel_configs or {}
        for channel in ["slack", "mattermost", "webhook"]:
            if channel not in channel_configs:
                continue
            try:
                if channel == "slack":
                    result = await self._send_slack_notification(
                        approval_request, approval_workflow
                    )
                    results["slack"] = result
                elif channel == "mattermost":
                    result = await self._send_mattermost_notification(
                        approval_request, approval_workflow
                    )
                    results["mattermost"] = result
                elif channel == "webhook":
                    result = await self._send_webhook_notification(
                        approval_request, approval_workflow
                    )
                    results["webhook"] = result
            except Exception as e:
                logger.error(f"Failed to send {channel} notification: {str(e)}")
                results[channel] = {"success": False, "error": str(e)}

        return results

    async def notify_escalation(
        self,
        approval_request: models.ApprovalRequest,
        approval_workflow: models.ApprovalWorkflow,
    ) -> Dict[str, Any]:
        """Send escalation notifications.

        Args:
            approval_request: The approval request that timed out.
            approval_workflow: The approval workflow containing escalation config.

        Returns:
            Dict with notification results per channel.
        """
        results = {}

        # Get escalation approvers
        escalation_user_ids = await self._get_escalation_user_ids(approval_workflow)

        if not escalation_user_ids:
            logger.warning("No escalation approvers configured")
            return {"error": "No escalation approvers configured"}

        # Send escalation notifications based on each user's preferences
        try:
            result = await self._send_email_notifications(
                approval_request, escalation_user_ids, is_escalation=True
            )
            results["email"] = result
        except Exception as e:
            logger.error(f"Failed to send escalation email notifications: {str(e)}")
            results["email"] = {"success": False, "error": str(e)}

        try:
            result = await self._send_push_notifications(
                approval_request, escalation_user_ids, is_escalation=True
            )
            results["mobile_push"] = result
        except Exception as e:
            logger.error(f"Failed to send escalation push notifications: {str(e)}")
            results["mobile_push"] = {"success": False, "error": str(e)}

        # Also send to workflow-configured channels with escalation context
        channel_configs = approval_workflow.channel_configs or {}
        for channel in ["slack", "mattermost", "webhook"]:
            if channel not in channel_configs:
                continue
            try:
                if channel == "slack":
                    result = await self._send_slack_notification(
                        approval_request, approval_workflow
                    )
                    results["slack"] = result
                elif channel == "mattermost":
                    result = await self._send_mattermost_notification(
                        approval_request, approval_workflow
                    )
                    results["mattermost"] = result
                elif channel == "webhook":
                    result = await self._send_webhook_notification(
                        approval_request, approval_workflow
                    )
                    results["webhook"] = result
            except Exception as e:
                logger.error(
                    f"Failed to send escalation {channel} notification: {str(e)}"
                )
                results[channel] = {"success": False, "error": str(e)}

        return results

    def _partition_users_by_channel(
        self, user_ids: List[uuid.UUID]
    ) -> Tuple[List[uuid.UUID], List[uuid.UUID], List[uuid.UUID]]:
        """Partition users into push-only, email-only, and both channels.

        Args:
            user_ids: List of user IDs to partition.

        Returns:
            Tuple of (push_only, email_only, both) user ID lists.
        """
        push_only: List[uuid.UUID] = []
        email_only: List[uuid.UUID] = []
        both: List[uuid.UUID] = []

        for user_id in user_ids:
            prefs = notification_preferences.get_by_user(self.db, user_id)
            if not prefs:
                continue

            has_email = bool(prefs.enable_email)
            has_push = bool(
                prefs.enable_mobile_push and prefs.get_device_tokens(platform="ios")
            )

            if has_push and has_email:
                both.append(user_id)
            elif has_push:
                push_only.append(user_id)
            elif has_email:
                email_only.append(user_id)
            # else: no channels enabled, skip

        logger.info(
            f"Partitioned {len(user_ids)} users: "
            f"{len(push_only)} push-only, {len(email_only)} email-only, "
            f"{len(both)} both"
        )
        return push_only, email_only, both

    async def _send_delayed_email(
        self,
        request_id: uuid.UUID,
        approval_request: models.ApprovalRequest,
        user_ids: List[uuid.UUID],
        delay_seconds: int = 15,
    ) -> None:
        """Send email notifications after a delay, but only if still pending.

        This implements the mobile-first strategy: give the user time to act
        via push notification before sending email.

        Args:
            request_id: The approval request ID to re-check.
            approval_request: The original approval request (used for email content).
            user_ids: Users to potentially email.
            delay_seconds: How long to wait before sending.
        """
        try:
            await asyncio.sleep(delay_seconds)

            # Re-check if the approval request is still pending
            current_request = (
                self.db.query(models.ApprovalRequest)
                .filter(models.ApprovalRequest.id == request_id)
                .first()
            )

            if not current_request or current_request.status != "pending":
                logger.info(
                    f"Skipping delayed email for approval {request_id}: "
                    f"status is '{current_request.status if current_request else 'not found'}'"
                )
                return

            logger.info(
                f"Approval {request_id} still pending after {delay_seconds}s, "
                f"sending delayed email to {len(user_ids)} users"
            )
            result = await self._send_email_notifications(approval_request, user_ids)
            logger.info(f"Delayed email result: {result}")

        except asyncio.CancelledError:
            logger.info(f"Delayed email task cancelled for approval {request_id}")
        except Exception as e:
            logger.error(
                f"Failed to send delayed email for approval {request_id}: {str(e)}",
                exc_info=True,
            )

    async def _get_approver_user_ids(
        self, approval_workflow: models.ApprovalWorkflow
    ) -> List[uuid.UUID]:
        """Get list of approver user IDs, expanding teams.

        Args:
            approval_workflow: Approval workflow.

        Returns:
            List of user IDs who can approve.
        """
        user_ids = set()

        # Add direct user approvers
        if approval_workflow.approver_user_ids:
            user_ids.update(approval_workflow.approver_user_ids)

        # Expand team approvers to individual users
        if approval_workflow.approver_team_ids:
            for team_id in approval_workflow.approver_team_ids:
                team_members = (
                    self.db.query(models.TeamMembership.user_id)
                    .filter(models.TeamMembership.team_id == team_id)
                    .all()
                )
                user_ids.update([member.user_id for member in team_members])

        return list(user_ids)

    async def _get_escalation_user_ids(
        self, approval_workflow: models.ApprovalWorkflow
    ) -> List[uuid.UUID]:
        """Get list of escalation approver user IDs, expanding teams.

        Args:
            approval_workflow: Approval workflow.

        Returns:
            List of escalation user IDs.
        """
        user_ids = set()

        # Add direct escalation users
        if approval_workflow.escalation_user_ids:
            user_ids.update(approval_workflow.escalation_user_ids)

        # Expand escalation teams
        if approval_workflow.escalation_team_ids:
            for team_id in approval_workflow.escalation_team_ids:
                team_members = (
                    self.db.query(models.TeamMembership.user_id)
                    .filter(models.TeamMembership.team_id == team_id)
                    .all()
                )
                user_ids.update([member.user_id for member in team_members])

        return list(user_ids)

    async def _send_email_notifications(
        self,
        approval_request: models.ApprovalRequest,
        user_ids: List[uuid.UUID],
        is_escalation: bool = False,
    ) -> Dict[str, Any]:
        """Send email notifications to approvers.

        Args:
            approval_request: Approval request.
            user_ids: List of user IDs to notify.
            is_escalation: Whether this is an escalation notification.

        Returns:
            Dict with send results.
        """
        from preloop.utils.email import (
            send_approval_request_email,
            send_escalation_email,
            PRELOOP_URL,
        )

        # Filter to users who have email notifications enabled
        eligible_user_ids = []
        for user_id in user_ids:
            prefs = notification_preferences.get_by_user(self.db, user_id)
            if not prefs or not prefs.enable_email:
                continue
            eligible_user_ids.append(user_id)

        if not eligible_user_ids:
            logger.info(
                f"No users with email enabled for approval request {approval_request.id}"
            )
            return {
                "success": True,
                "sent": 0,
                "failed": 0,
                "skipped": len(user_ids),
                "is_escalation": is_escalation,
            }

        sent_count = 0
        failed_count = 0

        for user_id in eligible_user_ids:
            try:
                # Look up user email
                user = (
                    self.db.query(models.User).filter(models.User.id == user_id).first()
                )
                if not user or not user.email:
                    logger.warning(f"User {user_id} not found or has no email")
                    failed_count += 1
                    continue

                if is_escalation:
                    send_escalation_email(
                        user_email=user.email,
                        tool_name=approval_request.tool_name,
                        request_id=str(approval_request.id),
                        approval_token=approval_request.approval_token,
                        base_url=PRELOOP_URL,
                    )
                else:
                    approval_url = (
                        f"{PRELOOP_URL}/approval/{approval_request.id}"
                        f"?token={approval_request.approval_token}"
                    )
                    await send_approval_request_email(
                        user_email=user.email,
                        tool_name=approval_request.tool_name,
                        tool_args=approval_request.tool_args,
                        approval_url=approval_url,
                        agent_reasoning=approval_request.agent_reasoning,
                    )

                sent_count += 1
                logger.info(
                    f"Sent {'escalation ' if is_escalation else ''}approval email "
                    f"to {user.email}"
                )

            except Exception as e:
                logger.error(
                    f"Failed to send email to user {user_id}: {str(e)}",
                    exc_info=True,
                )
                failed_count += 1

        skipped_count = len(user_ids) - len(eligible_user_ids)
        return {
            "success": failed_count == 0,
            "sent": sent_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "is_escalation": is_escalation,
        }

    async def _send_push_notifications(
        self,
        approval_request: models.ApprovalRequest,
        user_ids: List[uuid.UUID],
        is_escalation: bool = False,
    ) -> Dict[str, Any]:
        """Send mobile push notifications to approvers.

        Args:
            approval_request: Approval request.
            user_ids: List of user IDs to notify.
            is_escalation: Whether this is an escalation notification.

        Returns:
            Dict with send results.
        """
        from preloop.services.push_notifications import (
            get_apns_service,
            NotificationPayloadBuilder,
        )

        apns_service = get_apns_service()
        if not apns_service:
            logger.warning("APNs service not configured")
            return {
                "success": False,
                "error": "APNs not configured",
                "sent": 0,
                "failed": 0,
            }

        sent_count = 0
        failed_count = 0
        invalid_tokens = []  # Track 410 responses

        for user_id in user_ids:
            # Get user's notification preferences
            prefs = notification_preferences.get_by_user(self.db, user_id)
            if not prefs or not prefs.enable_mobile_push:
                continue

            # Get iOS device tokens
            ios_tokens = prefs.get_device_tokens(platform="ios")
            if not ios_tokens:
                continue

            # Build notification payload
            # Note: ApprovalRequest model doesn't have a priority field,
            # so we default to "medium" and set to "high" for escalations
            priority_str = "high" if is_escalation else "medium"
            payload = NotificationPayloadBuilder.new_approval_request(
                request_id=str(approval_request.id),
                tool_name=approval_request.tool_name,
                priority=priority_str,
                expires_at=approval_request.expires_at,
                agent_reasoning=approval_request.agent_reasoning,
            )

            # Add escalation prefix if needed
            if is_escalation:
                payload["aps"]["alert"]["title"] = (
                    "ESCALATION: " + payload["aps"]["alert"]["title"]
                )

            # Determine APNs priority
            apns_priority = 10 if priority_str in ["urgent", "high"] else 5

            # Send to each device
            for token in ios_tokens:
                try:
                    (
                        success,
                        status_code,
                        error_reason,
                    ) = await apns_service.send_notification(
                        device_token=token,
                        payload=payload,
                        priority=apns_priority,
                    )

                    if success:
                        sent_count += 1
                    elif status_code == 410:
                        # Token is invalid/expired
                        invalid_tokens.append((user_id, token))
                        logger.info(f"Marking token as invalid: {token[:10]}...")
                    else:
                        failed_count += 1

                except Exception as e:
                    logger.error(f"Failed to send push to token {token[:10]}...: {e}")
                    failed_count += 1

        # Remove invalid tokens from database
        for user_id, token in invalid_tokens:
            try:
                notification_preferences.remove_device_token(self.db, user_id, token)
                logger.info(f"Removed invalid token for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to remove token: {e}")

        # Commit token removals
        if invalid_tokens:
            self.db.commit()

        return {
            "success": failed_count == 0,
            "sent": sent_count,
            "failed": failed_count,
            "invalid_tokens_removed": len(invalid_tokens),
            "is_escalation": is_escalation,
        }

    async def _send_slack_notification(
        self,
        approval_request: models.ApprovalRequest,
        approval_workflow: models.ApprovalWorkflow,
    ) -> Dict[str, Any]:
        """Send Slack notification.

        Args:
            approval_request: Approval request.
            approval_workflow: Approval workflow with Slack configuration.

        Returns:
            Dict with send result.
        """
        channel_config = approval_workflow.channel_configs.get("slack", {})
        webhook_url = channel_config.get("webhook_url")

        if not webhook_url:
            return {"success": False, "error": "No Slack webhook URL configured"}

        message = self._build_chat_webhook_payload(approval_request)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook_url,
                    json=message,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()

            logger.info(
                f"Sent Slack notification for approval request {approval_request.id}"
            )
            return {"success": True, "channel": "slack"}

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {str(e)}")
            return {"success": False, "error": str(e)}

    async def _send_mattermost_notification(
        self,
        approval_request: models.ApprovalRequest,
        approval_workflow: models.ApprovalWorkflow,
    ) -> Dict[str, Any]:
        """Send Mattermost notification.

        Args:
            approval_request: Approval request.
            approval_workflow: Approval workflow with Mattermost configuration.

        Returns:
            Dict with send result.
        """
        channel_config = approval_workflow.channel_configs.get("mattermost", {})
        webhook_url = channel_config.get("webhook_url")

        if not webhook_url:
            return {"success": False, "error": "No Mattermost webhook URL configured"}

        message = self._build_chat_webhook_payload(approval_request)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook_url,
                    json=message,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()

            logger.info(
                f"Sent Mattermost notification for approval request {approval_request.id}"
            )
            return {"success": True, "channel": "mattermost"}

        except Exception as e:
            logger.error(f"Failed to send Mattermost notification: {str(e)}")
            return {"success": False, "error": str(e)}

    async def _send_webhook_notification(
        self,
        approval_request: models.ApprovalRequest,
        approval_workflow: models.ApprovalWorkflow,
    ) -> Dict[str, Any]:
        """Send generic webhook notification.

        Args:
            approval_request: Approval request.
            approval_workflow: Approval workflow with webhook configuration.

        Returns:
            Dict with send result.
        """
        channel_config = approval_workflow.channel_configs.get("webhook", {})
        webhook_url = channel_config.get("url")

        if not webhook_url:
            return {"success": False, "error": "No webhook URL configured"}

        from preloop.utils.email import PRELOOP_URL

        token = approval_request.approval_token
        approval_url = f"{PRELOOP_URL}/approval/{approval_request.id}?token={token}"

        from preloop.utils.redaction import redact_dict

        message = {
            "type": "approval_request",
            "request_id": str(approval_request.id),
            "tool_name": approval_request.tool_name,
            "tool_args": redact_dict(approval_request.tool_args or {}),
            "agent_reasoning": approval_request.agent_reasoning,
            "status": approval_request.status,
            "requested_at": approval_request.requested_at.isoformat(),
            "expires_at": (
                approval_request.expires_at.isoformat()
                if approval_request.expires_at
                else None
            ),
            "actions": {
                "approve": approval_url,
                "decline": approval_url,
                "view": approval_url,
            },
        }

        # Include extra headers from config if provided
        headers = {"Content-Type": "application/json"}
        extra_headers = channel_config.get("headers", {})
        if isinstance(extra_headers, dict):
            headers.update(extra_headers)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook_url,
                    json=message,
                    headers=headers,
                )
                response.raise_for_status()

            logger.info(
                f"Sent webhook notification for approval request {approval_request.id}"
            )
            return {"success": True, "url": webhook_url}

        except Exception as e:
            logger.error(f"Failed to send webhook notification: {str(e)}")
            return {"success": False, "error": str(e)}

    def _build_chat_webhook_payload(
        self, approval_request: models.ApprovalRequest
    ) -> Dict[str, Any]:
        """Build a Slack/Mattermost-compatible webhook payload.

        Args:
            approval_request: Approval request.

        Returns:
            Dict payload suitable for Slack or Mattermost incoming webhooks.
        """
        from preloop.utils.email import PRELOOP_URL
        from preloop.utils.redaction import redact_dict

        token = approval_request.approval_token
        approval_url = f"{PRELOOP_URL}/approval/{approval_request.id}?token={token}"
        tool_args_formatted = json.dumps(
            redact_dict(approval_request.tool_args or {}), indent=2
        )

        message_text = f"⚠️ **Approval Required: {approval_request.tool_name}**\n\n"
        message_text += f"**Tool:** `{approval_request.tool_name}`\n"
        message_text += f"**Status:** {approval_request.status.upper()}\n\n"

        if approval_request.agent_reasoning:
            message_text += (
                f"**Agent Reasoning:**\n{approval_request.agent_reasoning}\n\n"
            )

        message_text += f"**Arguments:**\n```json\n{tool_args_formatted}\n```\n\n"
        message_text += "**Actions:**\n"
        message_text += f"• [✅ Approve]({approval_url})\n"
        message_text += f"• [❌ Decline]({approval_url})\n"
        message_text += f"• [👁️ View Details]({approval_url})\n"

        fields = [
            {
                "title": "Tool",
                "value": approval_request.tool_name,
                "short": True,
            },
            {
                "title": "Status",
                "value": approval_request.status.upper(),
                "short": True,
            },
        ]

        if approval_request.agent_reasoning:
            fields.insert(
                0,
                {
                    "title": "Agent Reasoning",
                    "value": approval_request.agent_reasoning,
                    "short": False,
                },
            )

        return {
            "text": message_text,
            "attachments": [
                {
                    "color": "#f2c744",
                    "fallback": f"Approval Required: {approval_request.tool_name}",
                    "title": f"⚠️ Approval Required: {approval_request.tool_name}",
                    "title_link": approval_url,
                    "fields": fields,
                    "text": f"**Arguments:**\n```json\n{tool_args_formatted}\n```",
                    "actions": [
                        {
                            "type": "button",
                            "text": "✅ Approve",
                            "url": approval_url,
                            "style": "primary",
                        },
                        {
                            "type": "button",
                            "text": "❌ Decline",
                            "url": approval_url,
                            "style": "danger",
                        },
                        {
                            "type": "button",
                            "text": "👁️ View Details",
                            "url": approval_url,
                        },
                    ],
                }
            ],
        }
