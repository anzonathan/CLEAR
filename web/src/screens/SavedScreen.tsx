import { useNavigate } from "react-router-dom";
import { Button, Text, TopBar } from "../components/ui";

export default function SavedScreen() {
  const navigate = useNavigate();
  return (
    <div className="screen-pad with-tabs">
      <TopBar title="Saved" action="settings" />
      <div className="empty-state">
        <div className="empty-illustration">
          <div className="empty-court" />
          <div className="ball-shadow" />
          <div className="big-ball empty-ball" />
        </div>
        <Text as="h2">Nothing on the bench.</Text>
        <Text as="p" className="muted">
          Save matches, courts and players to find them here anytime.
        </Text>
        <Button icon="search" onClick={() => navigate("/search")}>
          Explore near you
        </Button>
      </div>
    </div>
  );
}
