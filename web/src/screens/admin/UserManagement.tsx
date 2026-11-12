import { useEffect, useState } from "react";
import { Avatar, Button, Icon, Text, TopBar, initialsOf } from "../../components/ui";
import {
  getAdminUsers,
  updateUserRole,
  deleteUser,
  type AdminUser,
} from "../../lib/api";

export default function UserManagement() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "user" | "admin" | "developer">("all");
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);

  useEffect(() => {
    loadUsers();
  }, []);

  function loadUsers() {
    setLoading(true);
    getAdminUsers()
      .then(setUsers)
      .finally(() => setLoading(false));
  }

  async function handleRoleChange(userId: string, role: string) {
    await updateUserRole(userId, role);
    loadUsers();
    setEditingUser(null);
  }

  async function handleDelete(userId: string) {
    if (confirm("Are you sure you want to delete this user?")) {
      await deleteUser(userId);
      loadUsers();
    }
  }

  const filteredUsers =
    filter === "all" ? users : users.filter((u) => u.role === filter);

  const roleCounts = {
    all: users.length,
    user: users.filter((u) => u.role === "user").length,
    admin: users.filter((u) => u.role === "admin").length,
    developer: users.filter((u) => u.role === "developer").length,
  };

  if (loading) {
    return (
      <div className="screen-pad">
        <TopBar title="Users" action="close" />
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
      <TopBar title="Users" action="close" />

      <div className="chips">
        {(["all", "user", "admin", "developer"] as const).map((f) => (
          <span
            key={f}
            className={filter === f ? "selected" : ""}
            onClick={() => setFilter(f)}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)} ({roleCounts[f]})
          </span>
        ))}
      </div>

      <div className="section-heading">
        <Text as="h3">
          {filter === "all" ? "All Users" : `${filter}s`}
        </Text>
        <span>{filteredUsers.length} users</span>
      </div>

      {filteredUsers.map((user) => (
        <div key={user.id} className="user-row">
          <Avatar initials={initialsOf(user.name, user.email)} />
          <div className="user-info">
            <b>{user.name}</b>
            <span>{user.email}</span>
            <span className={`role-badge role-${user.role}`}>
              {user.role.toUpperCase()}
            </span>
          </div>
          <div className="user-actions">
            <button onClick={() => setEditingUser(user)}>
              <Icon name="settings" size={16} />
            </button>
            <button onClick={() => handleDelete(user.id)}>
              <Icon name="trash" size={16} />
            </button>
          </div>
        </div>
      ))}

      {editingUser && (
        <div className="modal-overlay" onClick={() => setEditingUser(null)}>
          <div className="mini-modal" onClick={(e) => e.stopPropagation()}>
            <Avatar initials={initialsOf(editingUser.name, editingUser.email)} />
            <b>{editingUser.name}</b>
            <span>{editingUser.email}</span>

            <div className="role-select">
              <span>Change role:</span>
              <div className="chips">
                {(["user", "admin", "developer"] as const).map((role) => (
                  <span
                    key={role}
                    className={editingUser.role === role ? "selected" : ""}
                    onClick={() => handleRoleChange(editingUser.id, role)}
                  >
                    {role}
                  </span>
                ))}
              </div>
            </div>

            <Button variant="secondary" onClick={() => setEditingUser(null)}>
              Close
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
