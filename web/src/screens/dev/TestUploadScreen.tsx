import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Icon, Text, TopBar } from "../../components/ui";

export default function TestUploadScreen() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [runPipeline, setRunPipeline] = useState(true);

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
    if (!file) return;

    setUploading(true);
    setError(null);
    setProgress(0);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("run_pipeline", String(runPipeline));

    const apiUrl = import.meta.env.VITE_CV_API_URL ?? "http://localhost:8090";

    try {
      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          setProgress(Math.round((e.loaded / e.total) * 100));
        }
      });

      const response = await new Promise<any>((resolve, reject) => {
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(JSON.parse(xhr.responseText));
          } else {
            reject(new Error("Upload failed"));
          }
        };
        xhr.onerror = () => reject(new Error("Upload failed"));

        xhr.open("POST", `${apiUrl}/api/upload`);
        xhr.send(formData);
      });

      if (runPipeline) {
        navigate(`/dev/results/${response.video_id}`);
      } else {
        navigate("/dev/results");
      }
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
      <TopBar title="Test Upload" action="close" />

      <div className="dev-hero">
        <div className="dev-icon">
          <Icon name="upload" size={28} />
        </div>
        <Text as="h2">Upload Test Footage</Text>
        <Text as="p" className="muted">
          Upload video to test the auto-detection pipeline
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

      <div className="settings-row" onClick={() => setRunPipeline(!runPipeline)}>
        <span className="icon-tile">
          <Icon name="settings" />
        </span>
        <div>
          <b>Run auto-detection</b>
          <span>Process video through CV pipeline</span>
        </div>
        <span className={`toggle ${runPipeline ? "on" : ""}`}>
          <i />
        </span>
      </div>

      {uploading && (
        <div className="upload-progress">
          <div className="upload-progress-bar">
            <div style={{ width: `${progress}%` }} />
          </div>
          <span>{progress}% uploaded</span>
        </div>
      )}

      <Button onClick={handleUpload} disabled={!file || uploading}>
        {uploading ? "Uploading..." : "Upload video"}
      </Button>

      <div className="pipeline-info">
        <div className="section-heading">
          <Text as="h3">Pipeline stages</Text>
        </div>
        <div className="pipeline-stages">
          <div className="pipeline-stage">
            <Icon name="camera" size={16} />
            <span>Court calibration</span>
          </div>
          <div className="pipeline-stage">
            <Icon name="search" size={16} />
            <span>Ball detection</span>
          </div>
          <div className="pipeline-stage">
            <Icon name="users" size={16} />
            <span>Player tracking</span>
          </div>
          <div className="pipeline-stage">
            <Icon name="check" size={16} />
            <span>Line calling</span>
          </div>
        </div>
      </div>
    </div>
  );
}
