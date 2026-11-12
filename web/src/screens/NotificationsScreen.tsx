import { Avatar, Text, TopBar } from "../components/ui";

const notes = [
  ["RC", "Rally Club", "moved Saturday’s match to Court 6.", "2m"],
  ["ML", "Maya L.", "accepted your doubles invite.", "1h"],
  ["CL", "Clear", "Your weekly playing summary is ready.", "3h"],
  ["JS", "Jamie S.", "started following you.", "1d"],
];

export default function NotificationsScreen() {
  return (
    <div className="screen-pad with-tabs">
      <TopBar title="Notifications" action="settings" />
      <div className="notice-filter">
        <b>All activity</b>
        <span>Mark all read</span>
      </div>
      <div className="notice-list">
        {notes.map((n, i) => (
          <div className={`notice ${i < 2 ? "unread" : ""}`} key={n[1]}>
            <Avatar initials={n[0]} small />
            <Text as="p">
              <b>{n[1]}</b> {n[2]}
              <span>{n[3]}</span>
            </Text>
            {i < 2 && <i />}
          </div>
        ))}
      </div>
    </div>
  );
}
