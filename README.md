# Retail Chatbot - Recommendation System

A conversational retail chatbot that collects user preferences and provides personalized clothing recommendations using embedding-based similarity matching.

## Instructions:
** To use the chatbot follow the steps: **
1. Clone the repository
2. Create a virtual environment (preferably using a stable python version e.g. 3.10-3.11) and install the required packages from requirements-clean.txt
3. Download the images folder from Kaggle: https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/data?select=images (The folder is big ~ 30GB so can't be pushed in the repo)
4. Place the folder under retail-chatbot/recommendation
5. Run the images-folder.py script to remove all of the subfolders from the images folder
6. Run the main and use the chatbot
** If you choose to not download the images folder then a placeholder image will be rendered for the recommended items instead. **

## Phase 1: User Preference Collection

**Interactive conversation flow that gathers:**
- **Mode selection**: Single item vs complete outfit
- **Style preferences**: Business, Casual Sporty, Minimal, etc.
- **Body measurements**: Height, weight for size recommendations
- **Color preferences**: Extracted from user descriptions
- **Occasion**: Formal, casual, or specific events
- **Item specifications**: Specific clothing types requested

**Three distinct flows:**
- **Single-item**: Recommend one clothing piece based on style/occasion
- **Single-item + wardrobe matching**: Find items that match existing wardrobe pieces
- **Outfit**: Recommend complete coordinated outfit with multiple items

## Phase 2: Recommendation Engine

**Embedding-based recommendation system:**
- **Item type filtering**: Match user requests to product categories
- **Style matching**: Filter by style preference using embedding similarity
- **Color enhancement**: Boost products matching user color preferences
- **Description scoring**: Semantic similarity between user description and product details
- **Final ranking**: Combine style, color, and description scores

**Flow differences:**
- **Single-item**: Returns top-k items of requested type
- **Outfit**: Groups recommendations by each requested item type (e.g., separate results for "shirt", "pants", "shoes")
- **Wardrobe matching**: Incorporates existing items into similarity calculations

## User Interface

**Three-stage UI progression:**

**Stage 1 - Conversation:**
- Chat interface with auto-expanding text input
- Bot messages with conversation flow guidance
- Real-time preference collection and validation

**Stage 2 - Summary:**
- Split view: chat history (left) + preference summary (right)
- Size recommendation based on body measurements
- "My recommendations" button to proceed

**Stage 3 - Recommendations:**
- Three-panel layout: chat (20%) + recommendations (60%) + bucket zone (20%)
- Product images organized by category (shirts, pants, etc.)
- Horizontal scrolling within each category
- Product names and style information displayed
