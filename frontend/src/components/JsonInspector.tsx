import { useState } from "react";

interface Props {
  data: any;
}

export default function JsonInspector({ data }: Props) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="json-inspector">
      <button className="btn-toggle" onClick={() => setIsOpen(!isOpen)}>
        {isOpen ? "▼ Hide Raw JSON" : "▶ Show Raw JSON"}
      </button>
      {isOpen && (
        <pre className="json-content">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
