import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Avatar,
  Button,
  Icon,
  Text,
  TopBar,
  initialsOf,
} from "../components/ui";
import {
  getConnection,
  endConnection,
  startLiveSession,
  type ConnectionDetail,
} from "../lib/api";

export default function ConnectionDetailScreen() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [connection, setConnection] = useState<ConnectionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [ending, setEnding] = useState(false);

  useEffect(() => {
    if (id) {
      getConnection(id)
        .then(setConnection)
        .finally(() => setLoading(false));
    }
  }, [id]);

  async function handleStartLive() {
    if (!id) return;
    try {
      const { sessionId } = await startLiveSession(id);
      navigate(`/live/${sessionId}`);
    } catch (err) {
      console.error("Failed to start live session:", err);
    }
  }

  async function handleEndConnection() {
    if (!id) return;
    setEnding(true);
    try {
      await endConnection(id);
      navigate("/connections");
    } catch (err) {
      console.error("Failed to end connection:", err);
      setEnding(false);
    }
  }

  if (loading) {
    return (
      <div className="screen-pad">
        <TopBar title="Connection" action="close" />
        <div className="loader">
          <i />
          <i />
          <i />
        </div>
      </div>
    );
  }

  if (!connection) {
    return (
      <div className="screen-pad">
        <TopBar title="Connection" action="close" />
        <div className="inline-error">
          <b>Not found</b>
          <span>This connection does not exist.</span>
        </div>
      </div>
    );
  }

  const initials = initialsOf(connection.other_name, connection.other_email);
  const connectedDate = new Date(connection.created_at).toLocaleDateString();

  return (
    <div className="screen-pad">
      <TopBar title="Connection" action="close" />

      <div className="profile-head">
        <Avatar initials={initials} />
        <Text as="h2">{connection.other_name}</Text>
        <Text as="p" className="muted">
          {connection.other_email}
        </Text>
        <div className="profile-stats">
          <div>
            <b>{connection.videos?.length || 0}</b>
            <span>Shared</span>
          </div>
          <div>
            <b>{connectedDate}</b>
            <span>Connected</span>
          </div>
        </div>
      </div>

      <div className="connection-actions">
        <Button icon="video" onClick={handleStartLive}>
          Start live session
        </Button>
        <Button
          variant="secondary"
          icon="upload"
          onClick={() => navigate(`/upload?connection=${id}`)}
        >
          Share recording
        </Button>
      </div>

      {connection.videos && connection.videos.length > 0 && (
        <>
          <div className="section-heading">
            <Text as="h3">Shared videos</Text>
            <span>{connection.videos.length} videos</span>
          </div>
          {connection.videos.map((video) => (
            <div
              key={video.id}
              className="mini-row"
              onClick={() => navigate(`/videos/${video.id}`)}
              style={{ cursor: "pointer" }}
            >
              <div className="video-thumb">
                <Icon name="play" size={16} />
              </div>
              <div>
                <b>{video.file_name}</b>
                <span>
                  {new Date(video.created_at).toLocaleDateString()}
                  {video.duration_seconds &&
                    ` · ${Math.floor(video.duration_seconds / 60)}:${String(
                      video.duration_seconds % 60
                    ).padStart(2, "0")}`}
                </span>
              </div>
              <Icon name="chevron" />
            </div>
          ))}
        </>
      )}

      <div style={{ marginTop: "auto", paddingTop: 24 }}>
        <Button
          variant="ghost"
          onClick={handleEndConnection}
          disabled={ending}
        >
          {ending ? "Ending..." : "End connection"}
        </Button>
      </div>
    </div>
  );
}
