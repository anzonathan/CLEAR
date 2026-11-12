import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Field, Icon, Text, TopBar } from "../components/ui";
import { generatePairCode, joinPairCode } from "../lib/api";

export default function PairScreen() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"generate" | "join">("generate");
  const [code, setCode] = useState("");
  const [generatedCode, setGeneratedCode] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    try {
      const result = await generatePairCode();
      setGeneratedCode(result.code);
      setExpiresAt(result.expiresAt);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleJoin() {
    if (!code.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await joinPairCode(code);
      navigate(`/connections/${result.connectionId}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function copyCode() {
    if (generatedCode) {
      navigator.clipboard.writeText(generatedCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  function formatExpiry(iso: string) {
    const date = new Date(iso);
    const mins = Math.round((date.getTime() - Date.now()) / 60000);
    return mins > 0 ? `Expires in ${mins} min` : "Expired";
  }

  return (
    <div className="screen-pad with-tabs">
      <TopBar title="Connect" action="close" />

      <div className="pair-hero">
        <div className="pair-icon">
          <Icon name="link" size={32} />
        </div>
        <Text as="h2">Pair with a player</Text>
        <Text as="p" className="muted">
          Share your code or enter theirs to connect and share live footage.
        </Text>
      </div>

      <div className="chips" style={{ justifyContent: "center" }}>
        <span
          className={mode === "generate" ? "selected" : ""}
          onClick={() => setMode("generate")}
        >
          Generate code
        </span>
        <span
          className={mode === "join" ? "selected" : ""}
          onClick={() => setMode("join")}
        >
          Enter code
        </span>
      </div>

      {error && (
        <div className="inline-error">
          <b>Error</b>
          <span>{error}</span>
        </div>
      )}

      {mode === "generate" ? (
        <div className="pair-generate">
          {generatedCode ? (
            <div className="code-display">
              <div className="code-value">{generatedCode}</div>
              <button className="code-copy" onClick={copyCode}>
                <Icon name={copied ? "check" : "copy"} size={16} />
                {copied ? "Copied" : "Copy"}
              </button>
              {expiresAt && (
                <span className="code-expiry">{formatExpiry(expiresAt)}</span>
              )}
            </div>
          ) : (
            <Button onClick={handleGenerate} disabled={loading}>
              {loading ? "Generating..." : "Generate pair code"}
            </Button>
          )}
          {generatedCode && (
            <Button variant="secondary" onClick={handleGenerate} disabled={loading}>
              Generate new code
            </Button>
          )}
        </div>
      ) : (
        <div className="pair-join">
          <Field
            label="Pair code"
            placeholder="Enter 6-character code"
            value={code}
            onChange={(v) => setCode(v.toUpperCase())}
          />
          <Button onClick={handleJoin} disabled={loading || code.length < 6}>
            {loading ? "Connecting..." : "Connect"}
          </Button>
        </div>
      )}

      <div className="pair-info">
        <Icon name="users" size={16} />
        <span>Connected players can share live video and recordings</span>
      </div>
    </div>
  );
}
