import { Link } from "react-router-dom";
import { authClient } from "../lib/auth-client";
import {
  Avatar,
  Button,
  Icon,
  Text,
  TopBar,
  initialsOf,
} from "../components/ui";

export default function ProfileScreen() {
  const { data: session } = authClient.useSession();
  const user = session?.user;
  const initials = initialsOf(user?.name, user?.email);

  return (
    <div className="screen-pad with-tabs">
      <TopBar title="Profile" action="settings" />
      <div className="profile-head">
        <Avatar initials={initials} />
        <Text as="h2">{user?.name ?? "Player"}</Text>
        <Text as="p" className="muted">
          {user?.email ?? ""}
        </Text>
        <div className="profile-stats">
          <div>
            <b>4.2</b>
            <span>Rating</span>
          </div>
          <div>
            <b>38</b>
            <span>Matches</span>
          </div>
          <div>
            <b>12</b>
            <span>Friends</span>
          </div>
        </div>
        <Link to="/settings" style={{ width: "100%" }}>
          <Button variant="secondary">Edit profile</Button>
        </Link>
      </div>
      <div className="achievement">
        <div className="big-ball small-ball" />
        <div>
          <span className="eyebrow">LATEST BADGE</span>
          <b>Clay court regular</b>
          <span>8 matches on clay</span>
        </div>
      </div>
      <div className="section-heading">
        <Text as="h3">Upcoming</Text>
        <span>2 matches</span>
      </div>
      <div className="mini-row">
        <div className="date-tile">
          <b>24</b>
          <span>MAY</span>
        </div>
        <div>
          <b>Sunset court social</b>
          <span>Rally Club · 10:00 AM</span>
        </div>
        <Icon name="chevron" />
      </div>
    </div>
  );
}
