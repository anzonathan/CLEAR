import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button, Icon, Text, TopBar } from "../../components/ui";
import { getDevVideos, getVideo, type SharedVideo } from "../../lib/api";

export default function DetectionResultsScreen() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [video, setVideo] = useState<SharedVideo | null>(null);
  const [videos, setVideos] = useState<SharedVideo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (id) {
      getVideo(id)
        .then(setVideo)
        .finally(() => setLoading(false));
    } else {
      getDevVideos()
        .then(setVideos)
        .finally(() => setLoading(false));
    }
  }, [id]);

  if (loading) {
    return (
      <div className="screen-pad">
        <TopBar title="Results" action="close" />
        <div className="loader">
          <i />
          <i />
          <i />
        </div>
      </div>
    );
  }

  // List view
  if (!id) {
    return (
      <div className="screen-pad">
        <TopBar title="Results" action="close" />

        <div className="chips">
          <span className="selected">All</span>
          <span>Processed</span>
          <span>Pending</span>
        </div>

        <div className="section-heading">
          <Text as="h3">All Videos</Text>
          <span>{videos.length} total</span>
        </div>

        {videos.map((v) => (
          <div
            key={v.id}
            className="result-row"
            onClick={() => navigate(`/dev/results/${v.id}`)}
          >
            <div className="video-thumb">
              <Icon name="play" size={16} />
            </div>
            <div className="result-info">
              <b>{v.file_name}</b>
              <span>
                {v.uploader_name} · {new Date(v.created_at).toLocaleDateString()}
              </span>
            </div>
            <div className="result-status">
              {v.processed ? (
                <span className="status-badge success">
                  <Icon name="check" size={12} />
                  Done
                </span>
              ) : (
                <span className="status-badge pending">
                  <Icon name="settings" size={12} />
                  Processing
                </span>
              )}
            </div>
          </div>
        ))}

        <Button
          variant="secondary"
          icon="upload"
          onClick={() => navigate("/dev/upload")}
        >
          Upload new video
        </Button>
      </div>
    );
  }

  // Detail view
  if (!video) {
    return (
      <div className="screen-pad">
        <TopBar title="Results" action="close" />
        <div className="inline-error">
          <b>Not found</b>
          <span>This video does not exist.</span>
        </div>
      </div>
    );
  }

  const apiUrl = import.meta.env.VITE_CV_API_URL ?? "http://localhost:8090";

  return (
    <div className="screen-pad">
      <TopBar title="Results" action="close" />

      <div className="result-video-preview">
        <video
          src={`${apiUrl}/uploads/${video.file_path}`}
          controls
          playsInline
        />
      </div>

      <div className="result-header">
        <Text as="h2">{video.file_name}</Text>
        <Text as="p" className="muted">
          Uploaded {new Date(video.created_at).toLocaleString()}
        </Text>
      </div>

      <div className="result-status-card">
        {video.processed ? (
          <>
            <div className="success-dot">
              <Icon name="check" size={14} />
            </div>
            <div>
              <b>Analysis complete</b>
              <span>All pipeline stages finished</span>
            </div>
          </>
        ) : (
          <>
            <div className="loading-dot">
              <Icon name="settings" size={14} />
            </div>
            <div>
              <b>Processing...</b>
              <span>Running auto-detection pipeline</span>
            </div>
          </>
        )}
      </div>

      {video.processed && video.detection_results && (
        <>
          <div className="section-heading">
            <Text as="h3">Detection Data</Text>
          </div>

          <div className="detection-cards">
            <div className="detection-card">
              <Icon name="compass" size={20} />
              <b>Court</b>
              <span>Calibrated</span>
            </div>
            <div className="detection-card">
              <Icon name="search" size={20} />
              <b>Ball</b>
              <span>
                {video.detection_results.ball_frames ?? 0} frames
              </span>
            </div>
            <div className="detection-card">
              <Icon name="users" size={20} />
              <b>Players</b>
              <span>
                {video.detection_results.player_count ?? 0} detected
              </span>
            </div>
            <div className="detection-card">
              <Icon name="check" size={20} />
              <b>Calls</b>
              <span>
                {video.detection_results.line_calls ?? 0} line calls
              </span>
            </div>
          </div>

          <div className="section-heading">
            <Text as="h3">Raw Output</Text>
          </div>

          <div className="json-output">
            <pre>{JSON.stringify(video.detection_results, null, 2)}</pre>
          </div>
        </>
      )}

      <Button
        variant="secondary"
        onClick={() => navigate("/dev/results")}
      >
        Back to all results
      </Button>
    </div>
  );
}
