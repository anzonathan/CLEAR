import { Outlet } from "react-router-dom";
import { useUserRole } from "../App";
import { TabBar } from "./ui";

export default function AppShell() {
  const { role } = useUserRole();

  return (
    <div className="app">
      <div className="app-main">
        <Outlet />
      </div>
      <TabBar role={role} />
    </div>
  );
}
