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

function EventCard() {
  return (
    <Link to="/detail" className="event-card">
      <div className="event-image tournament-image">
        <span className="pill light-pill">FEATURED</span>
        <span className="save">
          <Icon name="bookmark" size={17} />
        </span>
      </div>
      <div className="event-copy">
        <div className="eyebrow">SAT, MAY 24 · 10:00</div>
        <Text as="h3">Sunset clay court social</Text>
        <Text as="p">Rally Club · Court 04</Text>
        <div className="attendees">
          <span>
            <Avatar initials="LP" small />
            <Avatar initials="JS" small />
          </span>
          <b>18 going</b>
        </div>
      </div>
    </Link>
  );
}

export default function HomeScreen() {
  const { data: session } = authClient.useSession();
  const user = session?.user;
  const name = user?.name?.split(" ")[0] ?? "there";
  const initials = initialsOf(user?.name, user?.email);

  return (
    <div className="screen-pad with-tabs">
      <TopBar title={`Good morning, ${name}`} />
      <div className="home-hero">
        <div>
          <div className="eyebrow">YOUR WEEK</div>
          <Text as="h2">Ready to rally?</Text>
        </div>
        <div className="score-ring">
          <b>3</b>
          <span>games</span>
        </div>
      </div>
      <div className="section-heading">
        <Text as="h3">Near you</Text>
        <span>See all</span>
      </div>
      <EventCard />
      <div className="mini-row">
        <div className="mini-thumb court-thumb" />
        <div>
          <b>Open court</b>
          <span>Today · 6:30 PM</span>
        </div>
        <Icon name="chevron" />
      </div>
      <div className="profile-head" style={{ paddingTop: 8 }}>
        <Avatar initials={initials} />
        <Button variant="secondary" icon="settings">
          {user?.name ?? user?.email}
        </Button>
      </div>
    </div>
  );
}
