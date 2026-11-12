import { Avatar, Button, Icon, Text } from "../components/ui";

export default function DetailScreen() {
  return (
    <div className="detail-screen">
      <div className="detail-image tournament-image">
        <span className="back-circle">←</span>
        <span className="save">
          <Icon name="bookmark" />
        </span>
      </div>
      <div className="detail-copy">
        <div className="eyebrow">SAT, MAY 24 · 10:00</div>
        <Text as="h2">Sunset clay court social</Text>
        <div className="host">
          <Avatar initials="RC" />
          <div>
            <b>Rally Club</b>
            <span>Hosted by Mila</span>
          </div>
        </div>
        <div className="fact">
          <Icon name="calendar" />
          <div>
            <b>Saturday, May 24</b>
            <span>10:00 AM – 12:30 PM</span>
          </div>
        </div>
        <div className="fact">
          <Icon name="compass" />
          <div>
            <b>Riverside Courts</b>
            <span>1.2 miles away</span>
          </div>
        </div>
        <Text as="p" className="muted">
          Friendly doubles on clay. All intermediate players welcome. Bring
          water and your best serve.
        </Text>
      </div>
      <div className="sticky-action">
        <div>
          <span>From</span>
          <b>$18</b>
        </div>
        <Button>Join match</Button>
      </div>
    </div>
  );
}
