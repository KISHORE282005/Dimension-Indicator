import type { DetectedIssue, ValidationResult } from "../types";

interface Props {
  validation: ValidationResult | null;
  issues: DetectedIssue[];
}

const SEVERITY_STYLES: Record<string, string> = {
  error: "severity-error",
  critical: "severity-critical",
  warning: "severity-warning",
  info: "severity-info",
};

export default function IssuesPanel({ validation, issues }: Props) {
  const allIssues = [
    ...(validation?.issues || []),
    ...(validation?.warnings || []),
  ];

  if (allIssues.length === 0) {
    return (
      <div className="issues-panel">
        <h3>⚠️ Issues & Warnings</h3>
        <div className="no-issues">No issues detected.</div>
      </div>
    );
  }

  const errors = allIssues.filter(
    (i) => i.severity === "error" || i.severity === "critical"
  );
  const warnings = allIssues.filter((i) => i.severity === "warning");
  const infos = allIssues.filter((i) => i.severity === "info");

  return (
    <div className="issues-panel">
      <h3>
        ⚠️ Issues & Warnings ({allIssues.length})
      </h3>

      <div className="issues-summary">
        {errors.length > 0 && (
          <span className="issue-badge error">{errors.length} Errors</span>
        )}
        {warnings.length > 0 && (
          <span className="issue-badge warning">{warnings.length} Warnings</span>
        )}
        {infos.length > 0 && (
          <span className="issue-badge info">{infos.length} Info</span>
        )}
      </div>

      {validation?.rules_applied && (
        <div className="rules-applied">
          <small>Rules applied: {validation.rules_applied.join(", ")}</small>
        </div>
      )}

      <div className="issues-list">
        {allIssues.map((issue) => (
          <div
            key={issue.id}
            className={`issue-item ${SEVERITY_STYLES[issue.severity] || ""}`}
          >
            <div className="issue-header">
              <span className={`severity-badge ${issue.severity}`}>
                {issue.severity.toUpperCase()}
              </span>
              <span className="issue-type">{issue.issue_type}</span>
              {issue.page_number && (
                <span className="issue-page">Page {issue.page_number}</span>
              )}
            </div>
            <div className="issue-description">{issue.description}</div>
            {issue.recommendation && (
              <div className="issue-recommendation">
                💡 {issue.recommendation}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
