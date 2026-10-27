"""CRUD operations for TrackerScopeRule model."""

from typing import List, Optional, Dict
from collections import defaultdict
from sqlalchemy.orm import Session
from ..models.tracker_scope_rule import TrackerScopeRule, ScopeType, RuleType
from ..models.tracker import Tracker
from .base import CRUDBase


class CRUDTrackerScopeRule(CRUDBase[TrackerScopeRule]):
    """CRUD operations for TrackerScopeRule model."""

    def get_by_tracker(
        self, db: Session, *, tracker_id: str, account_id: Optional[str] = None
    ) -> List[TrackerScopeRule]:
        """Get all scope rules for a given tracker."""
        query = db.query(TrackerScopeRule).filter(
            TrackerScopeRule.tracker_id == tracker_id
        )
        if account_id:
            query = query.join(Tracker).filter(Tracker.account_id == account_id)
        return query.all()

    def validate_scope_rules(
        self, rules: List[Dict[str, str]]
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that scope rules don't have conflicting project-level rules.

        Rules:
        1. Organizations must be explicitly included (ORGANIZATION + INCLUDE)
        2. For projects within an organization, you can use EITHER:
           - PROJECT + INCLUDE rules (whitelist mode)
           - PROJECT + EXCLUDE rules (blacklist mode)
           - No project rules (all projects included)
        3. You CANNOT mix PROJECT + INCLUDE and PROJECT + EXCLUDE for the same organization

        Args:
            rules: List of rule dictionaries with scope_type, rule_type, identifier

        Returns:
            Tuple of (is_valid, error_message)
            - (True, None) if valid
            - (False, error_message) if invalid
        """
        # Group rules by organization
        org_project_rules: Dict[str, Dict[str, List[str]]] = defaultdict(
            lambda: {"includes": [], "excludes": []}
        )

        included_orgs = set()

        for rule in rules:
            scope_type = (
                rule.get("scope_type").value
                if hasattr(rule.get("scope_type"), "value")
                else rule.get("scope_type")
            )
            rule_type = (
                rule.get("rule_type").value
                if hasattr(rule.get("rule_type"), "value")
                else rule.get("rule_type")
            )
            identifier = rule.get("identifier", "")

            # Track included organizations
            if (
                scope_type == ScopeType.ORGANIZATION.value
                and rule_type == RuleType.INCLUDE.value
            ):
                included_orgs.add(identifier)

            # Track project rules by their organization
            if scope_type == ScopeType.PROJECT.value:
                # Extract org from project identifier (format: "org/project" or just "project")
                org_identifier = (
                    identifier.split("/")[0] if "/" in identifier else identifier
                )

                if rule_type == RuleType.INCLUDE.value:
                    org_project_rules[org_identifier]["includes"].append(identifier)
                elif rule_type == RuleType.EXCLUDE.value:
                    org_project_rules[org_identifier]["excludes"].append(identifier)

        # Validate: No organization can have both include and exclude project rules
        for org_identifier, project_rules in org_project_rules.items():
            has_includes = len(project_rules["includes"]) > 0
            has_excludes = len(project_rules["excludes"]) > 0

            if has_includes and has_excludes:
                return (
                    False,
                    f"Organization '{org_identifier}' has both PROJECT INCLUDE and PROJECT EXCLUDE rules. "
                    f"Please use either include rules (whitelist) OR exclude rules (blacklist), not both.",
                )

        return (True, None)


crud_tracker_scope_rule = CRUDTrackerScopeRule(TrackerScopeRule)
