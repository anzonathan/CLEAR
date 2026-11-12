import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Avatar, Button, Icon, Text, TopBar, initialsOf } from "../components/ui";
import { getConnections, type Connection } from "../lib/api";

export default function ConnectionsScreen() {
  const navigate = useNavigate();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getConnections()
      .then(setConnections)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="screen-pad with-tabs">
        <TopBar title="Connections" />
        <div className="loader">
          <i />
          <i />
          <i />
        </div>
      </div>
    );
  }

  if (connections.length === 0) {
    return (
      <div className="screen-pad with-tabs">
        <TopBar title="Connections" />
        <div className="empty-state">
          <div className="empty-illustration">
            <div className="empty-court" />
            <div className="ball-shadow" />
            <div className="big-ball empty-ball" />
          </div>
          <Text as="h2">No connections yet</Text>
          <Text as="p" className="muted">
            Connect with other players to share live footage and recordings.
          </Text>
          <Button icon="link" onClick={() => navigate("/pair")}>
            Pair with a player
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="screen-pad with-tabs">
      <TopBar title="Connections" />

      <div className="section-heading">
        <Text as="h3">Active</Text>
        <span>{connections.length} connected</span>
      </div>

      {connections.map((conn) => (
        <Link
          key={conn.id}
          to={`/connections/${conn.id}`}
          className="connection-row"
        >
          <Avatar initials={initialsOf(conn.other_name, conn.other_email)} />
          <div>
            <b>{conn.other_name}</b>
            <span>{conn.other_email}</span>
          </div>
          <Icon name="chevron" />
        </Link>
      ))}

      <Button
        variant="secondary"
        icon="plus"
        onClick={() => navigate("/pair")}
      >
        Add connection
      </Button>
    </div>
  );
}
