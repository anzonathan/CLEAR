import { Button, Field, TopBar } from "../components/ui";

export default function CreateScreen() {
  return (
    <div className="screen-pad with-tabs">
      <TopBar title="Create match" action="close" />
      <div className="create-art">
        <div className="net" />
        <span>FRIENDLY DOUBLES</span>
      </div>
      <Field label="Match title" placeholder="Friday night rally" />
      <div className="two-fields">
        <Field label="Date" placeholder="May 30" />
        <Field label="Time" placeholder="6:30 PM" />
      </div>
      <Field label="Location" placeholder="Choose a court" icon="compass" />
      <div className="level-select">
        <span>Player level</span>
        <div className="chips">
          <span>Beginner</span>
          <span className="selected">Intermediate</span>
          <span>Advanced</span>
        </div>
      </div>
      <Button>Publish match</Button>
    </div>
  );
}
