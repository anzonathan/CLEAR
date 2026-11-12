import { useNavigate } from "react-router-dom";
import { authClient } from "../lib/auth-client";
import {
  Avatar,
  Button,
  Icon,
  TopBar,
  initialsOf,
  type IconName,
} from "../components/ui";

export default function SettingsScreen() {
  const navigate = useNavigate();
  const { data: session } = authClient.useSession();
  const user = session?.user;
  const initials = initialsOf(user?.name, user?.email);

  const rows: [IconName, string, string][] = [
    ["user", "Account", "Email, password, profile"],
    ["bell", "Notifications", "Push, email, reminders"],
    ["compass", "Location", "Brooklyn, NY"],
    ["settings", "Preferences", "Level, play style, privacy"],
  ];

  async function signOut() {
    await authClient.signOut();
    navigate("/auth");
  }

  return (
    <div className="screen-pad">
      <TopBar title="Settings" action="close" />
      <div className="settings-profile">
        <Avatar initials={initials} />
        <div>
          <b>{user?.name ?? "Player"}</b>
          <span>{user?.email ?? ""}</span>
        </div>
      </div>
      <div className="settings-group">
        {rows.map(([icon, title, sub]) => (
          <div className="settings-row" key={title}>
            <span className="icon-tile">
              <Icon name={icon} />
            </span>
            <div>
              <b>{title}</b>
              <span>{sub}</span>
            </div>
            <Icon name="chevron" />
          </div>
        ))}
      </div>
      <div className="settings-group">
        <div className="settings-row">
          <span className="icon-tile">
            <Icon name="bell" />
          </span>
          <div>
            <b>Match reminders</b>
            <span>30 minutes before</span>
          </div>
          <span className="toggle on">
            <i />
          </span>
        </div>
        <div className="settings-row">
          <span className="icon-tile">
            <Icon name="settings" />
          </span>
          <div>
            <b>Dark appearance</b>
            <span>Use system setting</span>
          </div>
          <span className="toggle">
            <i />
          </span>
        </div>
      </div>
      <Button variant="ghost" onClick={signOut}>
        Sign out
      </Button>
    </div>
  );
}
