import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button, Field, Icon, Text, TopBar } from "../components/ui";
import { getConnections, type Connection } from "../lib/api";

export default function UploadScreen() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedConnection = searchParams.get("connection");

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [selectedConnection, setSelectedConnection] = useState<string>(
    preselectedConnection || ""
  );
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getConnections().then(setConnections);
  }, []);

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0];
    if (selected) {
      if (!selected.type.startsWith("video/")) {
        setError("Please select a video file");
        return;
      }
      setFile(selected);
      setError(null);
    }
  }

  async function handleUpload() {
    if (!file || !selectedConnection) return;

    setUploading(true);
    setError(null);
    setProgress(0);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("connection_id", selectedConnection);

    const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:3030";

    try {
      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          setProgress(Math.round((e.loaded / e.total) * 100));
        }
      });

      await new Promise<void>((resolve, reject) => {
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve();
          } else {
            reject(new Error("Upload failed"));
          }
        };
        xhr.onerror = () => reject(new Error("Upload failed"));

        xhr.open("POST", `${apiUrl}/api/videos/upload`);
        xhr.withCredentials = true;
        xhr.send(formData);
      });

      navigate(`/connections/${selectedConnection}`);
    } catch (err: any) {
      setError(err.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  function formatSize(bytes: number) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  return (
    <div className="screen-pad">
      <TopBar title="Share video" action="close" />

      <div className="upload-hero">
        <div className="upload-icon">
          <Icon name="upload" size={32} />
        </div>
        <Text as="h2">Share a recording</Text>
        <Text as="p" className="muted">
          Upload a video to share with a connected player for analysis.
        </Text>
      </div>

      {error && (
        <div className="inline-error">
          <b>Error</b>
          <span>{error}</span>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="video/*"
        onChange={handleFileSelect}
        style={{ display: "none" }}
      />

      {!file ? (
        <div
          className="upload-dropzone"
          onClick={() => fileInputRef.current?.click()}
        >
          <Icon name="video" size={28} />
          <b>Select video file</b>
          <span>MP4, MOV, or WebM</span>
        </div>
      ) : (
        <div className="upload-file">
          <div className="upload-file-icon">
            <Icon name="video" size={20} />
          </div>
          <div>
            <b>{file.name}</b>
            <span>{formatSize(file.size)}</span>
          </div>
          <button onClick={() => setFile(null)}>
            <Icon name="close" size={16} />
          </button>
        </div>
      )}

      <div className="field">
        <span>Share with</span>
        <select
          className="input-shell"
          value={selectedConnection}
          onChange={(e) => setSelectedConnection(e.target.value)}
          style={{ width: "100%", height: 44, border: "1px solid var(--border)", borderRadius: 10, padding: "0 12px" }}
        >
          <option value="">Select a connection</option>
          {connections.map((conn) => (
            <option key={conn.id} value={conn.id}>
              {conn.other_name}
            </option>
          ))}
        </select>
      </div>

      {uploading && (
        <div className="upload-progress">
          <div className="upload-progress-bar">
            <div style={{ width: `${progress}%` }} />
          </div>
          <span>{progress}% uploaded</span>
        </div>
      )}

      <Button
        onClick={handleUpload}
        disabled={!file || !selectedConnection || uploading}
      >
        {uploading ? "Uploading..." : "Upload and share"}
      </Button>

      <div className="upload-note">
        <Icon name="settings" size={14} />
        <span>
          Videos will be automatically analyzed for ball tracking and line calls.
        </span>
      </div>
    </div>
  );
}
