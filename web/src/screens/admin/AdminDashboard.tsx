import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon, Text, TopBar } from "../../components/ui";
import { getAdminStats, type AdminStats } from "../../lib/api";

export default function AdminDashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAdminStats()
      .then(setStats)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="screen-pad">
        <TopBar title="Admin" action="settings" />
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
      <TopBar title="Admin" action="settings" />

      <div className="admin-hero">
        <div className="admin-icon">
          <Icon name="shield" size={28} />
        </div>
        <Text as="h2">Admin Dashboard</Text>
        <Text as="p" className="muted">
          System overview and management
        </Text>
      </div>

      <div className="admin-stats">
        <div className="stat-card">
          <Icon name="users" size={20} />
          <div>
            <b>{stats?.totalUsers ?? 0}</b>
            <span>Total Users</span>
          </div>
        </div>
        <div className="stat-card">
          <Icon name="link" size={20} />
          <div>
            <b>{stats?.activeConnections ?? 0}</b>
            <span>Connections</span>
          </div>
        </div>
        <div className="stat-card">
          <Icon name="video" size={20} />
          <div>
            <b>{stats?.totalVideos ?? 0}</b>
            <span>Videos</span>
          </div>
        </div>
        <div className="stat-card featured">
          <Icon name="camera" size={20} />
          <div>
            <b>{stats?.activeSessions ?? 0}</b>
            <span>Live Now</span>
          </div>
        </div>
      </div>

      <div className="section-heading">
        <Text as="h3">Manage</Text>
      </div>

      <div
        className="settings-row"
        onClick={() => navigate("/admin/users")}
        style={{ cursor: "pointer" }}
      >
        <span className="icon-tile">
          <Icon name="users" />
        </span>
        <div>
          <b>User Management</b>
          <span>View, edit, and manage users</span>
        </div>
        <Icon name="chevron" />
      </div>

      <div
        className="settings-row"
        onClick={() => navigate("/admin/monitoring")}
        style={{ cursor: "pointer" }}
      >
        <span className="icon-tile">
          <Icon name="search" />
        </span>
        <div>
          <b>System Monitoring</b>
          <span>Activity logs and usage stats</span>
        </div>
        <Icon name="chevron" />
      </div>

      <div
        className="settings-row"
        onClick={() => navigate("/settings")}
        style={{ cursor: "pointer" }}
      >
        <span className="icon-tile">
          <Icon name="settings" />
        </span>
        <div>
          <b>System Settings</b>
          <span>Configuration and preferences</span>
        </div>
        <Icon name="chevron" />
      </div>
    </div>
  );
}
