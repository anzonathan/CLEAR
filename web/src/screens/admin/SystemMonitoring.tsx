import { useEffect, useState } from "react";
import { Icon, Text, TopBar } from "../../components/ui";
import { getAdminStats, getAdminUsers, type AdminStats } from "../../lib/api";

export default function SystemMonitoring() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [recentUsers, setRecentUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getAdminStats(), getAdminUsers()])
      .then(([statsData, usersData]) => {
        setStats(statsData);
        // Get 5 most recent users
        setRecentUsers(usersData.slice(0, 5));
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="screen-pad">
        <TopBar title="Monitoring" action="close" />
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
      <TopBar title="Monitoring" action="close" />

      <div className="monitoring-overview">
        <div className="section-heading">
          <Text as="h3">System Health</Text>
          <span className="pill light-pill">HEALTHY</span>
        </div>

        <div className="health-grid">
          <div className="health-item">
            <div className="health-indicator good" />
            <div>
              <b>Auth Server</b>
              <span>Online</span>
            </div>
          </div>
          <div className="health-item">
            <div className="health-indicator good" />
            <div>
              <b>Database</b>
              <span>Connected</span>
            </div>
          </div>
          <div className="health-item">
            <div className="health-indicator good" />
            <div>
              <b>CV Pipeline</b>
              <span>Ready</span>
            </div>
          </div>
          <div className="health-item">
            <div className="health-indicator warning" />
            <div>
              <b>WebRTC</b>
              <span>
                {stats?.activeSessions ?? 0} active
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="section-heading">
        <Text as="h3">Activity</Text>
        <span>Last 24h</span>
      </div>

      <div className="activity-stats">
        <div className="activity-stat">
          <Icon name="users" size={18} />
          <div>
            <b>{stats?.totalUsers ?? 0}</b>
            <span>Total users</span>
          </div>
        </div>
        <div className="activity-stat">
          <Icon name="video" size={18} />
          <div>
            <b>{stats?.totalVideos ?? 0}</b>
            <span>Videos processed</span>
          </div>
        </div>
        <div className="activity-stat">
          <Icon name="link" size={18} />
          <div>
            <b>{stats?.activeConnections ?? 0}</b>
            <span>Active pairs</span>
          </div>
        </div>
      </div>

      <div className="section-heading">
        <Text as="h3">Recent Signups</Text>
      </div>

      {recentUsers.map((user) => (
        <div key={user.id} className="mini-row">
          <div className="date-tile">
            <Icon name="user" size={18} />
          </div>
          <div>
            <b>{user.name}</b>
            <span>
              {user.email} · {new Date(user.created_at).toLocaleDateString()}
            </span>
          </div>
          <span className={`role-badge role-${user.role}`}>
            {user.role}
          </span>
        </div>
      ))}
    </div>
  );
}
