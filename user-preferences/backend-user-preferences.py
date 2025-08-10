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
  └─ item   -> ask style -> ask item type -> match wardrobe? 
               ├─ yes -> ask wardrobe items -> item description
               └─ no  -> item description
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
import re
import os

# Require NLTK stopwords; download corpus if missing (per NLTK docs)
try:
    import nltk  # type: ignore
    from nltk.corpus import stopwords as _nltk_stopwords  # type: ignore
    try:
        _NLTK_STOPWORDS = set(_nltk_stopwords.words("english"))
    except LookupError:
        nltk.download("stopwords", quiet=True)
        _NLTK_STOPWORDS = set(_nltk_stopwords.words("english"))
except Exception as e:
    raise RuntimeError(
        "NLTK and its 'stopwords' corpus are required for description cleaning. "
        "Please install nltk and ensure the stopwords corpus is available."
    ) from e

# Fashion domain keep list to preserve context words
_DOMAIN_KEEP = {
    # Colors
    "black","white","gray","grey","silver","charcoal","graphite","slate","navy","blue","light","dark","midnight","indigo","cyan","teal","aqua","turquoise",
    "green","olive","khaki","lime","forest","emerald","mint","brown","tan","beige","camel","chocolate","mocha","sand","taupe",
    "red","maroon","burgundy","wine","crimson","pink","blush","rose","magenta","fuchsia","purple","violet","lavender","lilac",
    "orange","rust","terracotta","coral","peach","apricot","yellow","mustard","gold","golden","cream","ivory","ecru","offwhite","off-white",
    # Materials
    "cotton","denim","leather","faux","suede","wool","cashmere","merino","linen","silk","satin","viscose","rayon","polyester","nylon","spandex","elastane","lyocell","tencel","modal","acrylic",
    "twill","poplin","corduroy","velvet","fleece","gabardine","down","shearling","sherpa","canvas","mesh","lace","chiffon","organza","sequin","sequins","boucle",
    # Patterns & finishes
    "solid","plain","striped","stripes","pinstripe","pin-stripe","checks","checked","plaid","gingham","houndstooth","herringbone","jacquard","floral","paisley","abstract","geometric","animal","leopard","zebra","camouflage","camo",
    "polkadot","polka-dot","chevron","argyle","windowpane","window-pane","microcheck","micro-check","microstripe","micro-stripe",
    "ribbed","waffle","cable","quilted","matte","glossy","shiny","metallic","distressed","washed","acid","stonewashed","raw","selvedge","seersucker","brushed","waxed","garmentdyed","garment-dyed",
    # Fits & silhouettes
    "slim","skinny","regular","relaxed","loose","oversized","tapered","straight","bootcut","flare","flared","wide","baggy","cropped","fitted","boxy","athletic","tailored",
    "high","mid","low","rise","drop","waist","petite","tall","curvy","maternity","longline","long-line",
    # Garment parts & construction
    "crew","crewneck","vneck","v-neck","scoop","boatneck","turtleneck","mockneck","henley","button","buttoned","buttons","zip","zipper","halfzip","half-zip","fullzip","full-zip",
    "collar","spread","point","buttondown","button-down","band","mandarin","shawl","lapel","notch","peak","double","single","breasted",
    "sleeve","shortsleeve","short-sleeve","longsleeve","long-sleeve","sleeveless","cap","raglan","dolman","cuff","cuffed",
    "hem","rawhem","raw-hem","curvedhem","curved-hem","splithem","split-hem","drawstring","elastic","elasticated","belt","belted","pleat","pleated","dart","yoke","hood","hooded",
    # Item types
    "tshirt","t-shirt","tee","shirt","oxford","polo","blouse","top","tank","camisole","sweater","jumper","hoodie","sweatshirt","cardigan",
    "jacket","blazer","coat","trench","puffer","parka","gilet","vest","overcoat","peacoat","bomber","biker","trucker","windbreaker","anorak","shacket","overshirt",
    "jeans","chinos","trousers","pants","shorts","skirt","dress","jumpsuit","playsuit","suit","suiting","sweatpants","joggers","leggings","tights","cargos","cargo","slacks",
    # Footwear & accessories
    "sneakers","trainers","running","shoes","boots","chelsea","derby","oxford","loafer","loafers","brogue","brogues","monkstrap","monk-strap","sandals",
    "heels","flats","mules","clogs","espadrille","espadrilles","slides","flipflops","flip-flops",
    "bag","backpack","tote","crossbody","cross-body","belt","scarf","beanie","cap","hat","gloves","socks","tie","bowtie","bow-tie",
    "wallet","briefcase","duffle","duffel","satchel","watch","sunglasses",
    # Style/occasion cues
    "casual","smart","formal","business","professional","businesscasual","business-casual","businessformal","business-formal","smartcasual","smart-casual",
    "streetwear","sporty","athleisure","athletic","athflow",
    "minimal","minimalist","minimalistic","maximalist","classic","vintage","retro",
    "modern","contemporary","chic","elegant","sophisticated","refined","elevated","polished","sleek","clean","crisp",
    "edgy","preppy","boho","bohemian","artsy","avantgarde","avant-garde","androgynous","genderneutral","gender-neutral",
    "rugged","utilitarian","utility","workwear","heritage","artisan","artisanal",
    "monochrome","monochromatic","colorblock","color-block","pastel","neon","earthy",
    "quietluxury","quiet-luxury","oldmoney","old-money","luxe","luxury",
    "normcore","gorpcore","cottagecore","balletcore","barbiecore","regencycore","darkacademia","dark-academia","mermaidcore","indiesleaze","indie","y2k","70s","80s","90s","2000s",
    "grunge","punk","goth","emo","rock","metal","techwear","cyberpunk","retro-futuristic","retrofuturistic",
    "western","cowboy","cowgirl","americana","military","safari","nautical","coastal","coastalgrandma","coastal-grandma",
    # Occasions & contexts
    "wedding","weddingguest","wedding-guest","bridesmaid","groomsman","party","evening","office","work","weekend","holiday","vacation","travel","airport","airplane","outdoor","hiking","gym","training",
    "festival","concert","club","clubbing","nightout","night-out","datenight","date-night","date","brunch","dinner","picnic",
    "beach","pool","resort","cruise","apresski","apres-ski","ski","snowboard",
    "rainy","rainwear","winter","summer","spring","fall","autumn",
    "interview","presentation","meeting","clientmeeting","client-meeting","conference","networking","graduation","gala","cocktail","blacktie","black-tie","whitetie","white-tie",
    "commute","errands","loungewear","home","workfromhome","work-from-home","officeparty","office-party","teamdinner","team-dinner",
    # Lengths & coverage
    "mini","midi","maxi","ankle","fulllength","full-length","knee","above","below","threequarter","three-quarter","7/8","crop","cropped","short","long",
    # Washes & treatments
    "lightwash","light-wash","midwash","mid-wash","darkwash","dark-wash","vintagewash","vintage-wash","rinse","rawdenim","fade","faded","whiskered","whiskering","destroyed",
    # Other descriptive terms
    "breathable","stretch","stretchy","soft","cozy","warm","lightweight","heavyweight","midweight",
    "waterproof","water-resistant","waterrepellent","water-repellent","rainproof","windproof","insulated","lined","unlined","packable","quickdry","quick-dry","wrinklefree","wrinkle-free",
}

_STOPWORDS = _NLTK_STOPWORDS - _DOMAIN_KEEP

# Subset of common fashion item-type tokens to help validate comma separation
# (used to detect multiple items accidentally placed in one comma chunk)
ITEM_TYPE_TOKENS = {
    # Tops
    "tshirt", "t-shirt", "tee", "tees", "shirt", "shirts", "oxford", "polo", "blouse", "top", "tops", "tank", "camisole",
    "sweater", "jumpers", "jumper", "hoodie", "sweatshirt", "cardigan", "jacket", "jackets", "blazer", "coat", "coats",
    "trench", "puffer", "parka", "gilet", "vest", "overcoat", "peacoat", "bomber", "biker", "trucker", "windbreaker", "anorak", "shacket", "overshirt",
    # Bottoms
    "jeans", "jean", "chinos", "trousers", "pants", "shorts", "skirt", "skirts", "dress", "dresses", "jumpsuit", "playsuit",
    "suit", "suits", "sweatpants", "joggers", "leggings", "tights", "cargos", "cargo", "slacks", "bottoms", "bottomwear",
    # Footwear
    "sneakers", "trainers", "shoes", "boots", "chelsea", "derby", "oxford", "loafer", "loafers", "sandals",
    "heels", "flats", "mules", "clogs", "brogue", "brogues", "monkstrap", "monk-strap", "espadrille", "espadrilles", "slides", "flipflops", "flip-flops",
    "footwear",
    # Accessories
    "bag", "backpack", "tote", "crossbody", "belt", "scarf", "beanie", "cap", "hat",
    "gloves", "socks", "tie", "bowtie", "wallet", "briefcase", "duffle", "duffel", "satchel", "watch", "sunglasses",
    "headwear", "eyewear",
    # Category synonyms
    "outerwear", "underwear", "lingerie", "sleepwear", "nightwear", "swimwear", "activewear", "athleisure", "loungewear",
    "topwear",
}

# Combined hints used to validate meaningful fashion-related inputs
DOMAIN_HINTS: set[str] = set(_DOMAIN_KEEP) | set(ITEM_TYPE_TOKENS)


class Stage(Enum):
    """Conversation states matching the decision tree."""

    START = auto()
    MODE_SELECTION = auto()  # outfit vs item
    MODE_STYLE = auto()  # style / mood for the selected mode

    # Outfit path
    OUTFIT_ITEMS = auto() # what is the customer looking for
    OUTFIT_OCCASION = auto()  # specific vs daily
    OUTFIT_ITEM_DESC = auto()  # loop over items

    # Single item path
    ITEM_TYPE = auto()  # type of item (e.g. shirt, pants)
    ITEM_MATCH_WARDROBE = auto()  # whether to match existing wardrobe
    ITEM_WARDROBE_ITEMS = auto()  # ask which wardrobe items to match
    ITEM_DESC = auto()  # describe the item

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
    wardrobe_items_to_match: Optional[str] = None  # items to match the new item with

    # Details and body info
    descriptions: Dict[str, Any] = field(default_factory=dict)
    body: Dict[str, Any] = field(default_factory=dict)

    # Clean/normalized variants for later retrieval (kept separate to avoid UI changes)
    style_clean: Optional[str] = None
    outfit_items_list_clean: List[str] = field(default_factory=list)
    single_item_type_clean: Optional[str] = None
    wardrobe_items_to_match_clean: Optional[str] = None
    descriptions_clean: Dict[str, str] = field(default_factory=dict)


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
        # Debug toggle: include cleaned/normalized fields in snapshot/logs
        # Enable by setting RETAIL_CHATBOT_DEBUG_CLEAN=1
        self.debug_clean: bool = bool(int(os.getenv("RETAIL_CHATBOT_DEBUG_CLEAN", "0")))

    def enable_clean_debug(self, enabled: bool = True) -> None:
        """Enable/disable inclusion of cleaned fields in the snapshot for debugging."""
        self.debug_clean = enabled

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def process(self, user_input: Optional[str]) -> Dict[str, Any]:
        """Advance the conversation and return a payload for the GUI.

        Pass `None` (or empty string) to begin the conversation. On subsequent
        calls, pass the user's text or the selected choice (e.g. "outfit").
        """

        if user_input is not None:
            # Trim leading/trailing whitespace; stage handlers may further normalize
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
        if self.stage == Stage.ITEM_WARDROBE_ITEMS:
            return self._handle_item_wardrobe_items(user_input)
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
        """Initialize the conversation and prompt user to choose between outfit or item mode.
        
        Sets the stage to MODE_SELECTION and presents the initial greeting with choice options.
        
        Returns:
            Dict containing the greeting message and choice options for outfit vs item.
        """
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
        """Handle user's choice between outfit and item modes.
        
        Validates the user input and transitions to the style selection stage.
        Re-prompts if input is invalid.
        
        Args:
            user_input: User's choice, should be "outfit" or "item".
            
        Returns:
            Dict containing next stage prompt or error message.
        """
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
        """Handle user's style or mood input and route to appropriate next stage.
        
        Stores the style preference and transitions to either outfit items collection
        or single item type collection based on the previously selected mode.
        
        Args:
            user_input: User's description of desired style or mood.
            
        Returns:
            Dict containing confirmation message and next stage prompt.
        """
        if not user_input:
            return self._payload(["Please describe a style or mood."], expect="text")

        # Reject numeric-only input; require at least one alphabetic character
        if not re.search(r"[A-Za-z]", user_input or ""):
            return self._payload(["Please describe a style or mood with words (not just numbers)."], expect="text")

        # Sanity check for meaningful style text
        if not self._looks_meaningful_style(user_input):
            return self._payload(
                [
                    "That doesn't look like a fashion style. Try terms like 'casual', 'smart', 'minimal', 'streetwear'."
                ],
                expect="text",
            )

        # Store raw + cleaned variants
        self.data.style = user_input
        self.data.style_clean = self._normalize_text(user_input)

        if self.data.mode == "outfit":
            self.stage = Stage.OUTFIT_ITEMS
            return self._payload(
                [
                    f"Got it! You're looking for a {self.data.style} outfit.",
                    "What clothing items do you want to include?",
                    "Please separate items with commas (e.g., 'jeans, t-shirt, blazer').",
                ],
                expect="text",
            )
        else:
            self.stage = Stage.ITEM_TYPE
            return self._payload(
                [
                    f"Got it! You're looking for a {self.data.style} item.",
                    "What type of item is it? (e.g. 'jacket', 'sneakers')",
                ],
                expect="text",
            )

    # ---- Outfit path -----------------------------------------------------
    def _handle_outfit_items(self, user_input: Optional[str]) -> Dict[str, Any]:
        """Handle user's input for outfit items and parse them into a list.
        
        Parses comma-separated clothing items, validates the input, and stores
        the items for further processing. Transitions to occasion selection.
        
        Args:
            user_input: Comma-separated list of clothing items.
            
        Returns:
            Dict containing confirmation of items and occasion selection prompt.
        """
        if not user_input:
            return self._payload(
                ["List the clothing items separated by commas."], expect="text"
            )

        # Single-item fallback: if there's no comma and it looks like one item,
        # switch to the single-item flow (ITEM_MATCH_WARDROBE).
        if "," not in user_input:
            chunk = user_input.strip()
            # If conjunctions present, it's likely multiple items -> ask for commas
            if re.search(r"\b(and|&|plus)\b", chunk, flags=re.IGNORECASE):
                return self._payload(
                    [
                        "Please separate items with commas, e.g., 'jeans, t-shirt, blazer'."
                    ],
                    expect="text",
                )
            tokens = [t for t in re.split(r"[^0-9a-zA-Z\-]+", chunk.lower()) if t]
            matches = sum(1 for t in tokens if t in ITEM_TYPE_TOKENS)
            if matches == 1:
                # Looks like a single item -> pivot to single-item flow
                self.data.mode = "item"
                self.data.single_item_type = chunk
                self.data.single_item_type_clean = self._normalize_text(chunk)
                self.stage = Stage.ITEM_MATCH_WARDROBE
                return self._payload(
                    [
                        "Looks like you're after a single item.",
                        f"Item: {chunk}",
                        "Do you want it to match your current wardrobe? (yes/no)",
                    ],
                    expect="choice",
                    choices=["yes", "no"],
                )
            if matches == 0:
                return self._payload(
                    [
                        "I couldn't recognize a clothing item there. Try a name like 'blazer' or list items with commas: 'jeans, t-shirt, blazer'."
                    ],
                    expect="text",
                )
            # If multiple item tokens are present in one chunk, ask for commas
            return self._payload(
                [
                    "It looks like multiple items are in the same part. Please separate them with commas, e.g., 'jeans, t-shirt, blazer'."
                ],
                expect="text",
            )

        # Extra validation: ensure each comma-chunk represents a single item
        # and not multiple items mashed without commas (e.g., "t-shirt hat", "jeans and hoodie").
        raw_chunks = [chunk.strip() for chunk in user_input.split(",") if chunk.strip()]
        suspicious = False
        for chunk in raw_chunks:
            # If conjunctions appear, it's likely multiple items in one chunk
            if re.search(r"\b(and|&|plus)\b", chunk, flags=re.IGNORECASE):
                suspicious = True
                break
            # Count known item-type tokens in the chunk
            tokens = [t for t in re.split(r"[^0-9a-zA-Z\-]+", chunk.lower()) if t]
            matches = sum(1 for t in tokens if t in ITEM_TYPE_TOKENS)
            if matches >= 2:
                suspicious = True
                break
        if suspicious:
            return self._payload(
                [
                    "It looks like multiple items are in the same part. Please put each item in its own comma-separated entry.",
                    "Example: 'jeans, t-shirt, blazer' (not 't-shirt hat').",
                ],
                expect="text",
            )

        # Validate that each chunk contains a recognizable clothing item
        invalid_chunks: List[str] = []
        for chunk in raw_chunks:
            if not self._has_item_type_token(chunk):
                invalid_chunks.append(chunk)
        if invalid_chunks:
            bad = ", ".join(invalid_chunks)
            return self._payload(
                [
                    f"I couldn't find a clothing item in: {bad}.",
                    "Use item names like 'jeans, t-shirt, blazer'.",
                ],
                expect="text",
            )

        # Parse list and create cleaned variants
        items_display = raw_chunks
        items_clean = [self._normalize_text(x) for x in items_display]
        if not items_display:
            return self._payload([
                "I couldn't parse any items. Try something like: jeans, white t-shirt, blazer"
            ])
        self.data.outfit_items_raw = user_input
        self.data.outfit_items_list = items_display
        self.data.outfit_items_list_clean = items_clean
        self.data.outfit_items_pending = items_display.copy()

        self.stage = Stage.OUTFIT_OCCASION
        return self._payload(
            [
                (
                    f"Perfect! You're looking for an outfit with: {', '.join(self.data.outfit_items_list)}. "
                    "Is it for a specific occasion or daily wear?"
                )
            ],
            expect="choice",
            choices=["specific", "daily"],
        )

    def _handle_outfit_occasion(self, user_input: Optional[str]) -> Dict[str, Any]:
        """Handle user's choice for outfit occasion type.
        
        Validates the occasion selection (specific vs daily) and transitions to
        the per-item description collection phase.
        
        Args:
            user_input: User's choice, should be "specific" or "daily".
            
        Returns:
            Dict containing prompt for the first item description.
        """
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
        """Handle description input for individual outfit items.
        
        Processes the description for the current item and manages the loop
        through all outfit items. Once all items are described, transitions
        to body measurements collection.
        
        Args:
            user_input: User's description of the current item (color, fit, etc.).
            
        Returns:
            Dict containing next item prompt or body height collection prompt.
        """
        if not user_input:
            return self._payload(
                [f"Please describe the {self.data.current_item}."], expect="text"
            )

        # Require at least one fashion-domain term
        if not self._has_domain_words(user_input):
            return self._payload(
                [
                    f"Please include fashion details for the {self.data.current_item} (e.g., color, material, fit like 'navy, slim, cotton')."
                ],
                expect="text",
            )

        # Store description for the current item (raw + cleaned)
        assert self.data.current_item is not None
        self.data.descriptions[self.data.current_item] = user_input
        self.data.descriptions_clean[self.data.current_item] = self._clean_description(user_input)

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
        """Handle user input for the type of single item they're looking for.
        
        Stores the item type and transitions to asking whether they want it
        to match their existing wardrobe.
        
        Args:
            user_input: Description of the item type (e.g., 'jacket', 'sneakers').
            
        Returns:
            Dict containing wardrobe matching question with yes/no choices.
        """
        if not user_input:
            return self._payload(["What type of item is it?"], expect="text")

        # Require a recognizable item type token
        if not self._has_item_type_token(user_input):
            return self._payload(
                [
                    "Please name a clothing item (e.g., 'jacket', 'sneakers', 'jeans')."
                ],
                expect="text",
            )

        self.data.single_item_type = user_input
        self.data.single_item_type_clean = self._normalize_text(user_input)
        self.stage = Stage.ITEM_MATCH_WARDROBE
        return self._payload(
            ["Do you want it to match your current wardrobe? (yes/no)"],
            expect="choice",
            choices=["yes", "no"],
        )

    def _handle_item_match(self, user_input: Optional[str]) -> Dict[str, Any]:
        """Handle user's choice on whether item should match existing wardrobe.
        
        Validates the yes/no response and transitions to item description collection.
        
        Args:
            user_input: User's choice, should be "yes" or "no".
            
        Returns:
            Dict containing item description prompt or validation error.
        """
        if not user_input or user_input.lower() not in ("yes", "no"):
            return self._payload(
                ["Please answer 'yes' or 'no'."],
                expect="choice",
                choices=["yes", "no"],
            )

        self.data.match_existing = user_input.lower() == "yes"
        
        if self.data.match_existing:
            # If they want to match existing wardrobe, ask which items
            self.stage = Stage.ITEM_WARDROBE_ITEMS
            return self._payload(
                [
                    f"Which items in your wardrobe would you like to match the {self.data.single_item_type} with? "
                    "(e.g. 'dark jeans, white shirt, brown belt')"
                ],
                expect="text",
            )
        else:
            # If no matching needed, go straight to item description
            self.stage = Stage.ITEM_DESC
            return self._payload(
                [
                    f"Describe the {self.data.single_item_type} (color, material, fit, etc.).",
                ],
                expect="text",
            )

    def _handle_item_wardrobe_items(self, user_input: Optional[str]) -> Dict[str, Any]:
        """Handle user input for wardrobe items to match the new item with.
        
        Stores the list of wardrobe items that the user wants to coordinate with
        their new item and transitions to item description collection.
        
        Args:
            user_input: User's description of wardrobe items to match with.
            
        Returns:
            Dict containing item description prompt or validation error.
        """
        if not user_input:
            return self._payload(
                [
                    f"Please list the wardrobe items you'd like to match the {self.data.single_item_type} with."
                ],
                expect="text",
            )

        # Mark suspicious if no fashion-related terms were detected
        if not self._has_domain_words(user_input):
            return self._payload(
                [
                    "That looks a bit vague. Please list wardrobe items with fashion terms (e.g., 'dark jeans, white oxford shirt, brown belt')."
                ],
                expect="text",
            )

        self.data.wardrobe_items_to_match = user_input
        self.data.wardrobe_items_to_match_clean = self._normalize_text(user_input)
        self.stage = Stage.ITEM_DESC
        return self._payload(
            [
                f"Great! Now describe the {self.data.single_item_type} you're looking for "
                f"that will match with: {user_input}"
            ],
            expect="text",
        )

    def _handle_item_desc(self, user_input: Optional[str]) -> Dict[str, Any]:
        """Handle description input for the single item.
        
        Stores the item description and transitions to body measurements collection.
        
        Args:
            user_input: User's description of the item (color, material, fit, etc.).
            
        Returns:
            Dict containing body height collection prompt.
        """
        if not user_input:
            return self._payload(
                [f"Please describe the {self.data.single_item_type}."], expect="text"
            )

        # Require at least one fashion-domain term
        if not self._has_domain_words(user_input):
            return self._payload(
                [
                    f"This looks suspicious. Please include fashion details for the {self.data.single_item_type} (e.g., color, material, fit like 'black leather, slim, cropped')."
                ],
                expect="text",
            )

        assert self.data.single_item_type is not None
        self.data.descriptions[self.data.single_item_type] = user_input
        self.data.descriptions_clean[self.data.single_item_type] = self._clean_description(user_input)
        self.stage = Stage.BODY_HEIGHT
        return self._payload(["Height (in cm)?"], expect="text")

    # ---- Body measurements (common tail) --------------------------------
    def _handle_body_height(self, user_input: Optional[str]) -> Dict[str, Any]:
        """Handle user input for body height measurement.
        
        Validates the numeric input for height in centimeters and transitions
        to weight collection.
        
        Args:
            user_input: User's height input, should be a numeric string.
            
        Returns:
            Dict containing weight collection prompt or validation error.
        """
        if not self._is_number(user_input):
            return self._payload(["Enter a numeric height in cm."], expect="text")
        # At this point user_input is a valid numeric string
        assert isinstance(user_input, str)
        height = float(user_input)
        # Sensible human range check (allowing some variance)
        if not (100.0 <= height <= 250.0):
            return self._payload(["Enter a height between 100 and 250 cm."], expect="text")
        self.data.body["height_cm"] = height  # store as float for flexibility
        self.stage = Stage.BODY_WEIGHT
        return self._payload(["Weight (in kg)?"], expect="text")

    def _handle_body_weight(self, user_input: Optional[str]) -> Dict[str, Any]:
        """Handle user input for body weight measurement.
        
        Validates the numeric input for weight in kilograms and transitions
        to age collection.
        
        Args:
            user_input: User's weight input, should be a numeric string.
            
        Returns:
            Dict containing age collection prompt or validation error.
        """
        if not self._is_number(user_input):
            return self._payload(["Enter a numeric weight in kg."], expect="text")
        assert isinstance(user_input, str)
        weight = float(user_input)
        if not (30.0 <= weight <= 300.0):
            return self._payload(["Enter a weight between 30 and 300 kg."], expect="text")
        self.data.body["weight_kg"] = weight
        self.stage = Stage.BODY_AGE
        return self._payload(["Age?"], expect="text")

    def _handle_body_age(self, user_input: Optional[str]) -> Dict[str, Any]:
        """Handle user input for age and complete the preference collection.
        
        Validates the age input as an integer and marks the session as complete.
        
        Args:
            user_input: User's age input, should be a numeric string.
            
        Returns:
            Dict containing completion message with done=True flag.
        """
        if not user_input or not user_input.isdigit():
            return self._payload(["Enter age as an integer."], expect="text")
        age = int(user_input)
        if not (1 <= age <= 120):
            return self._payload(["Enter an age between 1 and 120."], expect="text")
        self.data.body["age"] = age
        self.stage = Stage.COMPLETE
        return self._payload(
            ["Perfect! I have all the information I need. Generating your personalized recommendations..."], 
            done=True, 
            show_summary=True
        )

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _payload(
        self,
        messages: List[str],
        expect: str = "text",
        choices: Optional[List[str]] = None,
        done: bool = False,
        show_summary: bool = False,
    ) -> Dict[str, Any]:
        """Build a consistent response payload for the GUI and log it."""

        payload = {
            "messages": messages,
            "stage": self.stage.name,
            "expect": expect,
            "choices": choices or [],
            "done": done,
            "show_summary": show_summary,
            "data": self._snapshot(),
        }
        self.logger.info(
            "<< stage=%s | expect=%s | choices=%s | done=%s | show_summary=%s | data=%s | messages=%s",
            self.stage.name,
            expect,
            payload["choices"],
            done,
            show_summary,
            payload["data"],
            messages,
        )
        return payload

    def _generate_user_summary(self) -> str:
        """Generate a user-friendly summary of collected preferences."""
        d = self.data
        summary_parts = []
        
        # Mode and style
        if d.mode == "outfit":
            summary_parts.append(f"✨ Looking for: A complete {d.style} outfit")
            if d.outfit_items_list:
                items_text = ", ".join(d.outfit_items_list)
                summary_parts.append(f"📝 Items: {items_text}")
            if d.occasion:
                summary_parts.append(f"🎯 Occasion: {d.occasion.title()} wear")
        else:
            summary_parts.append(f"✨ Looking for: A {d.style} {d.single_item_type}")
            if d.match_existing and d.wardrobe_items_to_match:
                summary_parts.append(f"👔 To match with: {d.wardrobe_items_to_match}")
        
        # Body measurements
        if d.body:
            measurements = []
            if "height_cm" in d.body:
                measurements.append(f"{int(d.body['height_cm'])}cm")
            if "weight_kg" in d.body:
                measurements.append(f"{int(d.body['weight_kg'])}kg")
            if "age" in d.body:
                measurements.append(f"{d.body['age']} years old")
            if measurements:
                summary_parts.append(f"📏 Profile: {' • '.join(measurements)}")
        
        return "\n".join(summary_parts)

    def _snapshot(self) -> Dict[str, Any]:
        """Small, public-friendly snapshot of the collected data."""

        d = self.data
        snapshot = {
            "mode": d.mode,
            "style": d.style,
            "occasion": d.occasion,
            "outfit_items": d.outfit_items_list,
            "single_item_type": d.single_item_type,
            "match_existing": d.match_existing,
            "wardrobe_items_to_match": d.wardrobe_items_to_match,
            "descriptions": d.descriptions,
            "body": d.body,
        }
        
        # Add user summary if session is complete
        if self.stage == Stage.COMPLETE:
            snapshot["user_summary"] = self._generate_user_summary()
        
        # Include cleaned/normalized data for debugging:
        # - Always at COMPLETE
        # - Or at any stage if debug_clean is enabled (env var or method)
        if self.stage == Stage.COMPLETE or self.debug_clean:
            snapshot["clean_debug"] = {
                "style_clean": d.style_clean,
                "outfit_items_list_clean": d.outfit_items_list_clean,
                "single_item_type_clean": d.single_item_type_clean,
                "wardrobe_items_to_match_clean": d.wardrobe_items_to_match_clean,
                "descriptions_clean": d.descriptions_clean,
            }

        return snapshot

    @staticmethod
    def _is_number(value: Optional[str]) -> bool:
        if not value:
            return False
        try:
            float(value)
            return True
        except ValueError:
            return False

    # ------------------------------
    # Normalization & cleaning helpers
    # ------------------------------
    @staticmethod
    def _normalize_text(value: str) -> str:
        v = value.strip().lower()
        return re.sub(r"\s+", " ", v)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        # keep alphanumeric tokens; split on non-alphanumerics
        return [t for t in re.split(r"[^0-9a-zA-Z]+", text.lower()) if t]

    def _clean_description(self, text: str) -> str:
        tokens = self._tokenize(text)
        filtered = [t for t in tokens if t not in _STOPWORDS]
        return " ".join(filtered)

    # --- Validation helpers ---
    def _has_item_type_token(self, text: str, min_hits: int = 1) -> bool:
        """Return True if text contains at least `min_hits` known item type tokens."""
        if not text:
            return False
        s = text.lower()
        tokens_hyphen = [t for t in re.split(r"[^0-9a-zA-Z\-]+", s) if t]
        tokens_basic = self._tokenize(s)
        tokens = set(tokens_hyphen) | set(tokens_basic)
        hits = sum(1 for t in tokens if t in ITEM_TYPE_TOKENS)
        return hits >= min_hits
    def _has_domain_words(self, text: str, min_hits: int = 1) -> bool:
        """Return True if text contains at least `min_hits` known fashion terms.

        Uses both hyphen-preserving and non-hyphen tokenization to catch terms
        like 'off-white', 'full-length', etc.
        """
        if not text:
            return False
        s = text.lower()
        tokens_hyphen = [t for t in re.split(r"[^0-9a-zA-Z\-]+", s) if t]
        tokens_basic = self._tokenize(s)
        tokens = set(tokens_hyphen) | set(tokens_basic)
        hits = sum(1 for t in tokens if t in DOMAIN_HINTS)
        return hits >= min_hits

    def _looks_meaningful_style(self, text: str) -> bool:
        """Strict style check: must contain at least one fashion domain term.

        This ensures consistent behavior across outfit and item modes.
        """
        return self._has_domain_words(text, min_hits=1)


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
