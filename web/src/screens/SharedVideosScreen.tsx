import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Icon, Text, TopBar } from "../components/ui";
import { getVideos, type SharedVideo } from "../lib/api";

export default function SharedVideosScreen() {
  const navigate = useNavigate();
  const [videos, setVideos] = useState<SharedVideo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getVideos()
      .then(setVideos)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="screen-pad with-tabs">
        <TopBar title="Videos" />
        <div className="loader">
          <i />
          <i />
          <i />
        </div>
      </div>
    );
  }

  if (videos.length === 0) {
    return (
      <div className="screen-pad with-tabs">
        <TopBar title="Videos" />
        <div className="empty-state">
          <div className="empty-illustration">
            <div className="empty-court" />
            <div className="ball-shadow" />
            <div className="big-ball empty-ball" />
          </div>
          <Text as="h2">No videos yet</Text>
          <Text as="p" className="muted">
            Videos shared with your connections will appear here.
          </Text>
          <Button icon="upload" onClick={() => navigate("/upload")}>
            Share a video
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="screen-pad with-tabs">
      <TopBar title="Videos" />

      <div className="section-heading">
        <Text as="h3">Shared with you</Text>
        <span>{videos.length} videos</span>
      </div>

      <div className="video-grid">
        {videos.map((video) => (
          <div
            key={video.id}
            className="video-card"
            onClick={() => navigate(`/videos/${video.id}`)}
          >
            <div className="video-card-thumb">
              <Icon name="play" size={24} />
              {video.duration_seconds && (
                <span className="video-duration">
                  {Math.floor(video.duration_seconds / 60)}:
                  {String(video.duration_seconds % 60).padStart(2, "0")}
                </span>
              )}
            </div>
            <div className="video-card-info">
              <b>{video.file_name}</b>
              <span>
                {video.uploader_name} ·{" "}
                {new Date(video.created_at).toLocaleDateString()}
              </span>
              {video.processed && (
                <span className="pill light-pill">ANALYZED</span>
              )}
            </div>
          </div>
        ))}
      </div>

      <Button
        variant="secondary"
        icon="upload"
        onClick={() => navigate("/upload")}
      >
        Share a video
      </Button>
    </div>
  );
}
