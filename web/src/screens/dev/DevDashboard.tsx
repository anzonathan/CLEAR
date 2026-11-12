import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon, Text, TopBar } from "../../components/ui";
import { getDevVideos, type SharedVideo } from "../../lib/api";

export default function DevDashboard() {
  const navigate = useNavigate();
  const [videos, setVideos] = useState<SharedVideo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDevVideos()
      .then(setVideos)
      .finally(() => setLoading(false));
  }, []);

  const processedCount = videos.filter((v) => v.processed).length;
  const pendingCount = videos.filter((v) => !v.processed).length;

  if (loading) {
    return (
      <div className="screen-pad">
        <TopBar title="Developer" action="settings" />
        <div className="loader">
          <i />
          <i />
          <i />
        </div>
      </div>
    );
  }

  return (
    <div className="screen-pad">
      <TopBar title="Developer" action="settings" />

      <div className="dev-hero">
        <div className="dev-icon">
          <Icon name="code" size={28} />
        </div>
        <Text as="h2">Dev Dashboard</Text>
        <Text as="p" className="muted">
          Test auto-detection and analyze footage
        </Text>
      </div>

      <div className="dev-stats">
        <div className="stat-card">
          <Icon name="video" size={20} />
          <div>
            <b>{videos.length}</b>
            <span>Total Videos</span>
          </div>
        </div>
        <div className="stat-card">
          <Icon name="check" size={20} />
          <div>
            <b>{processedCount}</b>
            <span>Processed</span>
          </div>
        </div>
        <div className="stat-card featured">
          <Icon name="settings" size={20} />
          <div>
            <b>{pendingCount}</b>
            <span>Pending</span>
          </div>
        </div>
      </div>

      <div className="section-heading">
        <Text as="h3">Tools</Text>
      </div>

      <div
        className="settings-row"
        onClick={() => navigate("/dev/upload")}
        style={{ cursor: "pointer" }}
      >
        <span className="icon-tile">
          <Icon name="upload" />
        </span>
        <div>
          <b>Upload Test Footage</b>
          <span>Upload video for pipeline testing</span>
        </div>
        <Icon name="chevron" />
      </div>

      <div
        className="settings-row"
        onClick={() => navigate("/dev/results")}
        style={{ cursor: "pointer" }}
      >
        <span className="icon-tile">
          <Icon name="search" />
        </span>
        <div>
          <b>Detection Results</b>
          <span>View analysis and detection data</span>
        </div>
        <Icon name="chevron" />
      </div>

      <div className="section-heading">
        <Text as="h3">Recent Uploads</Text>
        <span onClick={() => navigate("/dev/results")} style={{ cursor: "pointer" }}>
          View all
        </span>
      </div>

      {videos.slice(0, 3).map((video) => (
        <div
          key={video.id}
          className="mini-row"
          onClick={() => navigate(`/dev/results/${video.id}`)}
          style={{ cursor: "pointer" }}
        >
          <div className="video-thumb">
            <Icon name="play" size={16} />
          </div>
          <div>
            <b>{video.file_name}</b>
            <span>
              {video.uploader_name} ·{" "}
              {new Date(video.created_at).toLocaleDateString()}
            </span>
          </div>
          {video.processed ? (
            <span className="pill light-pill">DONE</span>
          ) : (
            <div className="loader" style={{ transform: "scale(0.5)" }}>
              <i />
              <i />
              <i />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
