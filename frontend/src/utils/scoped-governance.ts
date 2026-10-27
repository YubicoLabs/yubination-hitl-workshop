import type { AccessRuleSummary } from '../components/governance-rule-set-editor';

export type ScopedToolRules = Record<string, AccessRuleSummary[]>;

export function normalizeScopedToolRules(
  raw: Record<string, Array<Record<string, unknown>>> | null | undefined
): ScopedToolRules {
  const result: ScopedToolRules = {};
  for (const [toolName, rules] of Object.entries(raw || {})) {
    const normalizedToolName = toolName.trim();
    if (!normalizedToolName || !Array.isArray(rules)) {
      continue;
    }
    result[normalizedToolName] = rules
      .map((rule, index) => {
        const priority =
          typeof rule.priority === 'number' && Number.isFinite(rule.priority)
            ? rule.priority
            : index;
        return {
          id:
            typeof rule.id === 'string' && rule.id.trim()
              ? rule.id
              : `scoped:${normalizedToolName}:${index}`,
          action: typeof rule.action === 'string' ? rule.action : 'deny',
          condition_expression:
            typeof rule.condition_expression === 'string'
              ? rule.condition_expression
              : null,
          condition_type:
            typeof rule.condition_type === 'string'
              ? rule.condition_type
              : 'simple',
          priority,
          description:
            typeof rule.description === 'string' ? rule.description : null,
          is_enabled:
            typeof rule.is_enabled === 'boolean' ? rule.is_enabled : true,
          approval_workflow_id:
            typeof rule.approval_workflow_id === 'string'
              ? rule.approval_workflow_id
              : null,
        } satisfies AccessRuleSummary;
      })
      .sort((left, right) => left.priority - right.priority)
      .map((rule, index) => ({
        ...rule,
        priority: index,
      }));
  }
  return result;
}

export function serializeScopedToolRules(
  scopedRules: ScopedToolRules
): Record<string, Array<Record<string, unknown>>> {
  const result: Record<string, Array<Record<string, unknown>>> = {};
  for (const [toolName, rules] of Object.entries(scopedRules)) {
    const normalizedToolName = toolName.trim();
    if (!normalizedToolName || !Array.isArray(rules) || rules.length === 0) {
      continue;
    }
    result[normalizedToolName] = [...rules]
      .sort((left, right) => left.priority - right.priority)
      .map((rule, index) => ({
        action: rule.action,
        condition_expression: rule.condition_expression,
        condition_type: rule.condition_type,
        priority: index,
        description: rule.description,
        is_enabled: rule.is_enabled,
        approval_workflow_id: rule.approval_workflow_id,
      }));
  }
  return result;
}
