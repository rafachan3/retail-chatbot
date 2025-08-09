"""
Lightweight conversation backend for collecting user preferences.

Design
------
We keep the GUI thin and let this backend drive the conversation via a
finite state machine (FSM). The GUI calls Session.process(user_input)
and receives a structured payload describing:
  - messages: list[str] to render in the chat
  - stage: current FSM state name (str)
  - expect: "text" or "choice" (so the GUI knows which input widget to show)
  - choices: list[str] (only for expect == "choice")
  - done: bool flag indicating the end of the flow
  - data: snapshot of collected preferences (for debugging or later use)

Only Python's standard library is used (no third-party packages).

How stages map to the decision tree
-----------------------------------
START -> ask outfit vs item
  ├─ outfit -> ask style -> ask items -> ask occasion -> per-item descriptions loop
  │            -> height -> weight -> age -> COMPLETE
  └─ item   -> ask style -> ask item type -> match wardrobe? -> item description
               -> height -> weight -> age -> COMPLETE

Integration contract (GUI)
--------------------------
session = Session()
payload = session.process(None)        # start conversation
payload = session.process("outfit")    # user replies; call for each user message
Render payload.messages; if payload.expect == "choice" show buttons for payload.choices,
otherwise show a text input. If payload.done is True, disable inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional
import logging
from pathlib import Path


class Stage(Enum):
    """Conversation states matching the decision tree."""

    START = auto()
    MODE_SELECTION = auto()  # outfit vs item
    MODE_STYLE = auto()  # style / mood for the selected mode

    # Outfit path
    OUTFIT_ITEMS = auto()
    OUTFIT_OCCASION = auto()  # specific vs daily
    OUTFIT_ITEM_DESC = auto()  # loop over items

    # Single item path
    ITEM_TYPE = auto()
    ITEM_MATCH_WARDROBE = auto()
    ITEM_DESC = auto()

    # Common tail
    BODY_HEIGHT = auto()
    BODY_WEIGHT = auto()
    BODY_AGE = auto()

    COMPLETE = auto()


@dataclass
class SessionData:
    """Holds all collected information across the conversation."""

    # Shared
    mode: Optional[str] = None  # "outfit" | "item"
    style: Optional[str] = None

    # Outfit-specific
    outfit_items_raw: Optional[str] = None
    outfit_items_list: List[str] = field(default_factory=list)
    outfit_items_pending: List[str] = field(default_factory=list)
    current_item: Optional[str] = None
    occasion: Optional[str] = None  # "specific" | "daily"

    # Item-specific
    single_item_type: Optional[str] = None
    match_existing: Optional[bool] = None

    # Details and body info
    descriptions: Dict[str, Any] = field(default_factory=dict)
    body: Dict[str, Any] = field(default_factory=dict)


class Session:
    """Stateful conversation manager.

    Create one Session per user (or keep a mapping of user_id -> Session) and
    call `process()` for each user reply. The Session instance maintains the
    current `stage` and the collected `data`.
    """

    def __init__(self) -> None:
        self.stage: Stage = Stage.START
        self.data = SessionData()
        self.logger = _get_logger()

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def process(self, user_input: Optional[str]) -> Dict[str, Any]:
        """Advance the conversation and return a payload for the GUI.

        Pass `None` (or empty string) to begin the conversation. On subsequent
        calls, pass the user's text or the selected choice (e.g. "outfit").
        """

        if user_input is not None:
            user_input = user_input.strip()

        # Log inbound
        self.logger.info(
            ">> user_input=%r | stage=%s",
            user_input,
            self.stage.name,
        )

        # Entry point: show greeting and ask mode
        if self.stage == Stage.START:
            return self._enter_mode_selection()

        # Route to the dedicated handler for each stage
        if self.stage == Stage.MODE_SELECTION:
            return self._handle_mode_selection(user_input)
        if self.stage == Stage.MODE_STYLE:
            return self._handle_mode_style(user_input)

        # Outfit path
        if self.stage == Stage.OUTFIT_ITEMS:
            return self._handle_outfit_items(user_input)
        if self.stage == Stage.OUTFIT_OCCASION:
            return self._handle_outfit_occasion(user_input)
        if self.stage == Stage.OUTFIT_ITEM_DESC:
            return self._handle_outfit_item_desc(user_input)

        # Single item path
        if self.stage == Stage.ITEM_TYPE:
            return self._handle_item_type(user_input)
        if self.stage == Stage.ITEM_MATCH_WARDROBE:
            return self._handle_item_match(user_input)
        if self.stage == Stage.ITEM_DESC:
            return self._handle_item_desc(user_input)

        # Common tail
        if self.stage == Stage.BODY_HEIGHT:
            return self._handle_body_height(user_input)
        if self.stage == Stage.BODY_WEIGHT:
            return self._handle_body_weight(user_input)
        if self.stage == Stage.BODY_AGE:
            return self._handle_body_age(user_input)

        # Fallback: complete
        return self._payload(["Session complete."], done=True)

    # ---------------------------------------------------------------------
    # Stage handlers
    # ---------------------------------------------------------------------
    def _enter_mode_selection(self) -> Dict[str, Any]:
        self.stage = Stage.MODE_SELECTION
        return self._payload(
            [
                "Hi, I'm your shopping assistant.",
                "Are you looking for a complete outfit or a specific item?",
            ],
            expect="choice",
            choices=["outfit", "item"],
        )

    def _handle_mode_selection(self, user_input: Optional[str]) -> Dict[str, Any]:
        if not user_input or user_input.lower() not in ("outfit", "item"):
            # Re-ask with explicit choices
            return self._payload(
                ["Please choose: 'outfit' or 'item'."],
                expect="choice",
                choices=["outfit", "item"],
            )

        self.data.mode = user_input.lower()
        self.stage = Stage.MODE_STYLE
        if self.data.mode == "outfit":
            return self._payload(
                [
                    "Great! Let's find you an outfit. What is the style or mood you're looking for?",
                ],
                expect="text",
            )
        else:
            return self._payload(
                [
                    "Awesome! What is the style or mood you're looking for?",
                ],
                expect="text",
            )

    def _handle_mode_style(self, user_input: Optional[str]) -> Dict[str, Any]:
        if not user_input:
            return self._payload(["Please describe a style or mood."], expect="text")

        self.data.style = user_input

        if self.data.mode == "outfit":
            self.stage = Stage.OUTFIT_ITEMS
            return self._payload(
                [
                    (
                        f"Got it! You're looking for a {self.data.style} outfit. "
                        "What clothing items do you want to include? "
                        "(e.g. 'jeans, white t-shirt, blazer')"
                    )
                ],
                expect="text",
            )
        else:
            self.stage = Stage.ITEM_TYPE
            return self._payload(
                [
                    (
                        f"Got it! You're looking for a {self.data.style} item. "
                        "What type of item is it? (e.g. 'jacket', 'sneakers')"
                    )
                ],
                expect="text",
            )

    # ---- Outfit path -----------------------------------------------------
    def _handle_outfit_items(self, user_input: Optional[str]) -> Dict[str, Any]:
        if not user_input:
            return self._payload(
                ["List the clothing items separated by commas."], expect="text"
            )

        # Normalize and store item list
        items = [x.strip() for x in user_input.split(",") if x.strip()]
        if not items:
            return self._payload([
                "I couldn't parse any items. Try something like: jeans, white t-shirt, blazer"
            ])
        self.data.outfit_items_raw = user_input
        self.data.outfit_items_list = items
        self.data.outfit_items_pending = items.copy()

        self.stage = Stage.OUTFIT_OCCASION
        return self._payload(
            [
                (
                    f"Perfect! You're looking for an outfit with: {', '.join(items)}. "
                    "Is it for a specific occasion or daily wear?"
                )
            ],
            expect="choice",
            choices=["specific", "daily"],
        )

    def _handle_outfit_occasion(self, user_input: Optional[str]) -> Dict[str, Any]:
        if not user_input or user_input.lower() not in ("specific", "daily"):
            return self._payload(
                ["Choose 'specific' or 'daily'."],
                expect="choice",
                choices=["specific", "daily"],
            )

        self.data.occasion = user_input.lower()

        # Start the per-item description loop with the first pending item
        self.stage = Stage.OUTFIT_ITEM_DESC
        self.data.current_item = self.data.outfit_items_pending.pop(0)
        return self._payload(
            [f"Describe the {self.data.current_item} (color, fit, etc.)."],
            expect="text",
        )

    def _handle_outfit_item_desc(self, user_input: Optional[str]) -> Dict[str, Any]:
        if not user_input:
            return self._payload(
                [f"Please describe the {self.data.current_item}."], expect="text"
            )

        # Store description for the current item
        assert self.data.current_item is not None
        self.data.descriptions[self.data.current_item] = user_input

        if self.data.outfit_items_pending:
            # Move to next item in the loop
            self.data.current_item = self.data.outfit_items_pending.pop(0)
            return self._payload(
                [f"Great. Next item: describe the {self.data.current_item}."],
                expect="text",
            )

        # No items left -> collect body info
        self.stage = Stage.BODY_HEIGHT
        return self._payload(["Thanks. Lastly, your height (in cm)?"], expect="text")

    # ---- Single item path -----------------------------------------------
    def _handle_item_type(self, user_input: Optional[str]) -> Dict[str, Any]:
        if not user_input:
            return self._payload(["What type of item is it?"], expect="text")

        self.data.single_item_type = user_input
        self.stage = Stage.ITEM_MATCH_WARDROBE
        return self._payload(
            ["Do you want it to match your current wardrobe? (yes/no)"],
            expect="choice",
            choices=["yes", "no"],
        )

    def _handle_item_match(self, user_input: Optional[str]) -> Dict[str, Any]:
        if not user_input or user_input.lower() not in ("yes", "no"):
            return self._payload(
                ["Please answer 'yes' or 'no'."],
                expect="choice",
                choices=["yes", "no"],
            )

        self.data.match_existing = user_input.lower() == "yes"
        self.stage = Stage.ITEM_DESC
        return self._payload(
            [
                f"Describe the {self.data.single_item_type} (color, material, fit, etc.).",
            ],
            expect="text",
        )

    def _handle_item_desc(self, user_input: Optional[str]) -> Dict[str, Any]:
        if not user_input:
            return self._payload(
                [f"Please describe the {self.data.single_item_type}."], expect="text"
            )

        assert self.data.single_item_type is not None
        self.data.descriptions[self.data.single_item_type] = user_input
        self.stage = Stage.BODY_HEIGHT
        return self._payload(["Height (in cm)?"], expect="text")

    # ---- Body measurements (common tail) --------------------------------
    def _handle_body_height(self, user_input: Optional[str]) -> Dict[str, Any]:
        if not self._is_number(user_input):
            return self._payload(["Enter a numeric height in cm."], expect="text")
        # At this point user_input is a valid numeric string
        assert isinstance(user_input, str)
        self.data.body["height_cm"] = float(user_input)  # store as float for flexibility
        self.stage = Stage.BODY_WEIGHT
        return self._payload(["Weight (in kg)?"], expect="text")

    def _handle_body_weight(self, user_input: Optional[str]) -> Dict[str, Any]:
        if not self._is_number(user_input):
            return self._payload(["Enter a numeric weight in kg."], expect="text")
        assert isinstance(user_input, str)
        self.data.body["weight_kg"] = float(user_input)
        self.stage = Stage.BODY_AGE
        return self._payload(["Age?"], expect="text")

    def _handle_body_age(self, user_input: Optional[str]) -> Dict[str, Any]:
        if not user_input or not user_input.isdigit():
            return self._payload(["Enter age as an integer."], expect="text")
        self.data.body["age"] = int(user_input)
        self.stage = Stage.COMPLETE
        return self._payload(["Thanks! Preference collection complete."], done=True)

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _payload(
        self,
        messages: List[str],
        expect: str = "text",
        choices: Optional[List[str]] = None,
        done: bool = False,
    ) -> Dict[str, Any]:
        """Build a consistent response payload for the GUI and log it."""

        payload = {
            "messages": messages,
            "stage": self.stage.name,
            "expect": expect,
            "choices": choices or [],
            "done": done,
            "data": self._snapshot(),
        }
        self.logger.info(
            "<< stage=%s | expect=%s | choices=%s | done=%s | data=%s | messages=%s",
            self.stage.name,
            expect,
            payload["choices"],
            done,
            payload["data"],
            messages,
        )
        return payload

    def _snapshot(self) -> Dict[str, Any]:
        """Small, public-friendly snapshot of the collected data."""

        d = self.data
        return {
            "mode": d.mode,
            "style": d.style,
            "occasion": d.occasion,
            "outfit_items": d.outfit_items_list,
            "descriptions": d.descriptions,
            "body": d.body,
        }

    @staticmethod
    def _is_number(value: Optional[str]) -> bool:
        if not value:
            return False
        try:
            float(value)
            return True
        except ValueError:
            return False


# Convenience factory (optional)
def new_session() -> Session:
    return Session()


# ------------------------------
# Logging helpers
# ------------------------------

def _get_logger() -> logging.Logger:
    logger = logging.getLogger("retail_chatbot.user_prefs")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    # Console handler
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    # File handler (best-effort)
    try:
        log_path = Path(__file__).parent / "session.log"
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    return logger


def configure_logging(file_path: Optional[str] = None, level: int = logging.INFO) -> None:
    """Optionally adjust logging from the UI (path/level)."""
    logger = _get_logger()
    logger.setLevel(level)
    if file_path:
        try:
            fh = logging.FileHandler(file_path, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
            logger.addHandler(fh)
        except Exception:
            # Ignore failures; keep existing handlers
            pass
