import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button, Icon, Text, TopBar } from "../components/ui";
import { getVideo, type SharedVideo } from "../lib/api";

export default function VideoPlayerScreen() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [video, setVideo] = useState<SharedVideo | null>(null);
  const [loading, setLoading] = useState(true);
  const [showOverlay, setShowOverlay] = useState(true);

  useEffect(() => {
    if (id) {
      getVideo(id)
        .then(setVideo)
        .finally(() => setLoading(false));
    }
  }, [id]);

  if (loading) {
    return (
      <div className="screen-pad">
        <TopBar title="Video" action="close" />
        <div className="loader">
          <i />
          <i />
          <i />
        </div>
      </div>
    );
  }

  if (!video) {
    return (
      <div className="screen-pad">
        <TopBar title="Video" action="close" />
        <div className="inline-error">
          <b>Not found</b>
          <span>This video does not exist.</span>
        </div>
      </div>
    );
  }

  const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8090";

  return (
    <div className="video-player-screen">
      <div className="video-player-header">
        <button className="back-circle" onClick={() => navigate(-1)}>
          <Icon name="close" size={18} />
        </button>
        <Text as="h3">{video.file_name}</Text>
        <button
          className="icon-button"
          onClick={() => setShowOverlay(!showOverlay)}
        >
          <Icon name={showOverlay ? "check" : "search"} size={18} />
        </button>
      </div>

      <div className="video-player-container">
        <video
          src={`${apiUrl}/uploads/${video.file_path}`}
          controls
          autoPlay
          playsInline
          className="video-player"
        />
        {showOverlay && video.detection_results && (
          <div className="detection-overlay">
            {/* Detection overlay would render here based on detection_results */}
          </div>
        )}
      </div>

      <div className="video-player-info">
        <div className="video-meta">
          <div>
            <span className="eyebrow">UPLOADED BY</span>
            <b>{video.uploader_name}</b>
          </div>
          <div>
            <span className="eyebrow">DATE</span>
            <b>{new Date(video.created_at).toLocaleDateString()}</b>
          </div>
          {video.duration_seconds && (
            <div>
              <span className="eyebrow">DURATION</span>
              <b>
                {Math.floor(video.duration_seconds / 60)}:
                {String(video.duration_seconds % 60).padStart(2, "0")}
              </b>
            </div>
          )}
        </div>

        {video.processed && video.detection_results && (
          <div className="detection-summary">
            <div className="section-heading">
              <Text as="h3">Analysis</Text>
              <span className="pill light-pill">AUTO-DETECTED</span>
            </div>
            <div className="detection-stats">
              <div>
                <Icon name="check" size={16} />
                <span>Ball tracking available</span>
              </div>
              <div>
                <Icon name="users" size={16} />
                <span>Player positions detected</span>
              </div>
              <div>
                <Icon name="compass" size={16} />
                <span>Court calibrated</span>
              </div>
            </div>
          </div>
        )}

        {!video.processed && (
          <div className="processing-notice">
            <Icon name="settings" size={20} />
            <div>
              <b>Processing video</b>
              <span>Auto-detection analysis is running...</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
