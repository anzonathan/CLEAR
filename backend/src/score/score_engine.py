"""Tennis scoring engine supporting points (0/15/30/40/Deuce/Ad), games, tiebreaks, and sets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal


POINT_LABELS = {0: "0", 1: "15", 2: "30", 3: "40"}


@dataclass
class PointLog:
    point_number: int
    winner_id: int
    reason: str
    score_after: str
    frame_idx: int


@dataclass
class TennisScoreEngine:
    player1_name: str = "PLAYER 1 (NEAR)"
    player2_name: str = "PLAYER 2 (FAR)"
    server_id: int = 1

    p1_points: int = 0
    p2_points: int = 0
    p1_games: int = 0
    p2_games: int = 0
    p1_sets: int = 0
    p2_sets: int = 0
    in_tiebreak: bool = False
    history: List[PointLog] = field(default_factory=list)
    _cooldown_until_frame: int = -100

    def award_point(self, winner_id: int, reason: str = "OUT call", frame_idx: int = 0) -> None:
        """Award point to Player 1 or Player 2 with debounce cooldown."""
        if frame_idx > 0 and frame_idx < self._cooldown_until_frame:
            return
        self._cooldown_until_frame = frame_idx + 45

        if winner_id == 1:
            self.p1_points += 1
        else:
            self.p2_points += 1

        if self.in_tiebreak:
            if (self.p1_points >= 7 or self.p2_points >= 7) and abs(self.p1_points - self.p2_points) >= 2:
                self._win_game(1 if self.p1_points > self.p2_points else 2)
        else:
            if (self.p1_points >= 4 or self.p2_points >= 4) and abs(self.p1_points - self.p2_points) >= 2:
                self._win_game(1 if self.p1_points > self.p2_points else 2)

        self.history.append(
            PointLog(
                point_number=len(self.history) + 1,
                winner_id=winner_id,
                reason=reason,
                score_after=self.format_score_line(),
                frame_idx=frame_idx,
            )
        )

    def register_bounce(self, is_in: bool, court_half: Literal["near", "far"], frame_idx: int) -> None:
        """Automatically update score if a bounce is called OUT."""
        if is_in:
            return
        # Ball landed OUT on `court_half`: the player on the opposite half hit it long/wide.
        winner_id = 2 if court_half == "far" else 1
        self.award_point(winner_id=winner_id, reason=f"Ball OUT on {court_half} court", frame_idx=frame_idx)

    def _win_game(self, winner_id: int) -> None:
        self.p1_points = 0
        self.p2_points = 0
        if winner_id == 1:
            self.p1_games += 1
        else:
            self.p2_games += 1

        self.server_id = 2 if self.server_id == 1 else 1

        if self.in_tiebreak:
            self.in_tiebreak = False
            self._win_set(winner_id)
            return

        if self.p1_games == 6 and self.p2_games == 6:
            self.in_tiebreak = True
        elif (self.p1_games >= 6 or self.p2_games >= 6) and abs(self.p1_games - self.p2_games) >= 2:
            self._win_set(1 if self.p1_games > self.p2_games else 2)

    def _win_set(self, winner_id: int) -> None:
        if winner_id == 1:
            self.p1_sets += 1
        else:
            self.p2_sets += 1
        self.p1_games = 0
        self.p2_games = 0

    def get_point_display(self) -> tuple[str, str]:
        if self.in_tiebreak:
            return str(self.p1_points), str(self.p2_points)
        if self.p1_points >= 3 and self.p2_points >= 3:
            if self.p1_points == self.p2_points:
                return "40", "40"
            elif self.p1_points > self.p2_points:
                return "AD", "40"
            else:
                return "40", "AD"
        return POINT_LABELS.get(self.p1_points, "40"), POINT_LABELS.get(self.p2_points, "40")

    def format_score_line(self) -> str:
        pt1, pt2 = self.get_point_display()
        return f"Sets {self.p1_sets}-{self.p2_sets} | Games {self.p1_games}-{self.p2_games} | Pts {pt1}-{pt2}"

    def to_dict(self) -> Dict[str, object]:
        pt1, pt2 = self.get_point_display()
        return {
            "player1_name": self.player1_name,
            "player2_name": self.player2_name,
            "server_id": self.server_id,
            "sets": [self.p1_sets, self.p2_sets],
            "games": [self.p1_games, self.p2_games],
            "points": [pt1, pt2],
            "score_line": self.format_score_line(),
            "events": [
                {
                    "point_number": e.point_number,
                    "winner_id": e.winner_id,
                    "reason": e.reason,
                    "score_after": e.score_after,
                    "frame_idx": e.frame_idx,
                }
                for e in self.history
            ],
        }
