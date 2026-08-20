import type { AIInterpretation } from "../types";

interface Props {
  interpretations: AIInterpretation[];
}

export default function AIInterpretationPanel({ interpretations }: Props) {
  if (interpretations.length === 0) return null;

  return (
    <div className="ai-panel">
      <h3>🤖 AI Interpretations (Gemini)</h3>
      <div className="ai-disclaimer">
        <strong>DISCLAIMER:</strong> The following interpretations were generated
        by an AI model. They are NOT independently verified engineering facts.
        Use as supplementary information only.
      </div>

      {interpretations.map((ai) => (
        <div key={ai.id} className="ai-item">
          <div className="ai-header">
            <span>Page {ai.page_number}</span>
            <span>Model: {ai.model_used}</span>
            <span>Confidence: {(ai.confidence * 100).toFixed(0)}%</span>
          </div>
          <div className="ai-text">{ai.interpretation_text.slice(0, 2000)}</div>
          {ai.extracted_items.length > 0 && (
            <div className="ai-items-count">
              Extracted {ai.extracted_items.length} items from this page.
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
