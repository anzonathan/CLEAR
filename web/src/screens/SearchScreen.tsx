import { Icon, Text, TopBar, Field } from "../components/ui";

export default function SearchScreen() {
  return (
    <div className="screen-pad with-tabs">
      <TopBar title="Explore" action="filter" />
      <Field label="" placeholder="Courts, clubs or players" icon="search" />
      <div className="chips">
        <span className="selected">All</span>
        <span>Matches</span>
        <span>Courts</span>
        <span>Players</span>
      </div>
      <div className="map-card">
        <div className="map-lines" />
        <span className="map-pin one">2</span>
        <span className="map-pin two">5</span>
        <span className="map-pin three">1</span>
      </div>
      <div className="section-heading">
        <Text as="h3">12 nearby</Text>
        <span>Map view</span>
      </div>
      <div className="search-result">
        <div className="result-thumb clay" />
        <div>
          <span className="eyebrow">0.8 MI · CLAY</span>
          <b>Parkside Tennis Club</b>
          <span>4 courts · Open now</span>
        </div>
        <Icon name="chevron" />
      </div>
      <div className="search-result">
        <div className="result-thumb green" />
        <div>
          <span className="eyebrow">1.4 MI · HARD</span>
          <b>North Loop Courts</b>
          <span>6 courts · Busy</span>
        </div>
        <Icon name="chevron" />
      </div>
    </div>
  );
}
