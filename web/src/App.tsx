import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { authClient } from "./lib/auth-client";
import { getMe } from "./lib/api";
import AppShell from "./components/AppShell";
import AuthScreen from "./screens/AuthScreen";
import HomeScreen from "./screens/HomeScreen";
import DetailScreen from "./screens/DetailScreen";
import SearchScreen from "./screens/SearchScreen";
import CreateScreen from "./screens/CreateScreen";
import ProfileScreen from "./screens/ProfileScreen";
import SettingsScreen from "./screens/SettingsScreen";
import NotificationsScreen from "./screens/NotificationsScreen";
import SavedScreen from "./screens/SavedScreen";
import PairScreen from "./screens/PairScreen";
import ConnectionsScreen from "./screens/ConnectionsScreen";
import ConnectionDetailScreen from "./screens/ConnectionDetailScreen";
import SharedVideosScreen from "./screens/SharedVideosScreen";
import VideoPlayerScreen from "./screens/VideoPlayerScreen";
import UploadScreen from "./screens/UploadScreen";
import LiveSessionScreen from "./screens/LiveSessionScreen";
import AdminDashboard from "./screens/admin/AdminDashboard";
import UserManagement from "./screens/admin/UserManagement";
import SystemMonitoring from "./screens/admin/SystemMonitoring";
import DevDashboard from "./screens/dev/DevDashboard";
import TestUploadScreen from "./screens/dev/TestUploadScreen";
import DetectionResultsScreen from "./screens/dev/DetectionResultsScreen";

type UserRole = "user" | "admin" | "developer";

interface UserContext {
  role: UserRole;
  isAdmin: boolean;
  isDev: boolean;
}

const UserRoleContext = createContext<UserContext>({
  role: "user",
  isAdmin: false,
  isDev: false,
});

export function useUserRole() {
  return useContext(UserRoleContext);
}

function Loading() {
  return (
    <div className="app app-loading">
      <div className="loader">
        <i />
        <i />
        <i />
      </div>
    </div>
  );
}

function AuthGate({ children }: { children: ReactNode }) {
  const { data: session, isPending } = authClient.useSession();
  const [role, setRole] = useState<UserRole>("user");
  const [roleLoading, setRoleLoading] = useState(true);

  useEffect(() => {
    if (session?.user) {
      getMe()
        .then((user) => setRole(user.role))
        .catch(() => setRole("user"))
        .finally(() => setRoleLoading(false));
    } else {
      setRoleLoading(false);
    }
  }, [session?.user]);

  if (isPending || roleLoading) return <Loading />;
  if (!session) return <Navigate to="/auth" replace />;

  const userContext: UserContext = {
    role,
    isAdmin: role === "admin",
    isDev: role === "developer" || role === "admin",
  };

  return (
    <UserRoleContext.Provider value={userContext}>
      {children}
    </UserRoleContext.Provider>
  );
}

function RequireRole({ roles, children }: { roles: UserRole[]; children: ReactNode }) {
  const { role } = useUserRole();
  if (!roles.includes(role)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/auth" element={<AuthScreen />} />

        {/* Protected routes */}
        <Route
          element={
            <AuthGate>
              <AppShell />
            </AuthGate>
          }
        >
          {/* Common user routes */}
          <Route index element={<HomeScreen />} />
          <Route path="detail" element={<DetailScreen />} />
          <Route path="search" element={<SearchScreen />} />
          <Route path="create" element={<CreateScreen />} />
          <Route path="profile" element={<ProfileScreen />} />
          <Route path="settings" element={<SettingsScreen />} />
          <Route path="notifications" element={<NotificationsScreen />} />
          <Route path="saved" element={<SavedScreen />} />

          {/* Pairing and connections */}
          <Route path="pair" element={<PairScreen />} />
          <Route path="connections" element={<ConnectionsScreen />} />
          <Route path="connections/:id" element={<ConnectionDetailScreen />} />

          {/* Videos */}
          <Route path="videos" element={<SharedVideosScreen />} />
          <Route path="videos/:id" element={<VideoPlayerScreen />} />
          <Route path="upload" element={<UploadScreen />} />

          {/* Live session (full screen, no shell) */}
          <Route path="live/:sessionId" element={<LiveSessionScreen />} />

          {/* Admin routes */}
          <Route
            path="admin"
            element={
              <RequireRole roles={["admin"]}>
                <AdminDashboard />
              </RequireRole>
            }
          />
          <Route
            path="admin/users"
            element={
              <RequireRole roles={["admin"]}>
                <UserManagement />
              </RequireRole>
            }
          />
          <Route
            path="admin/monitoring"
            element={
              <RequireRole roles={["admin"]}>
                <SystemMonitoring />
              </RequireRole>
            }
          />

          {/* Developer routes */}
          <Route
            path="dev"
            element={
              <RequireRole roles={["developer", "admin"]}>
                <DevDashboard />
              </RequireRole>
            }
          />
          <Route
            path="dev/upload"
            element={
              <RequireRole roles={["developer", "admin"]}>
                <TestUploadScreen />
              </RequireRole>
            }
          />
          <Route
            path="dev/results"
            element={
              <RequireRole roles={["developer", "admin"]}>
                <DetectionResultsScreen />
              </RequireRole>
            }
          />
          <Route
            path="dev/results/:id"
            element={
              <RequireRole roles={["developer", "admin"]}>
                <DetectionResultsScreen />
              </RequireRole>
            }
          />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
