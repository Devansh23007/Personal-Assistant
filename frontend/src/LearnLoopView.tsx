import { FormEvent, useEffect, useState } from "react";

type Deck = {
  id: number;
  user_id: number;
  document_id: number | null;
  title: string;
  description: string | null;
  card_count: number;
  mastered_count: number;
  due_count: number;
  created_at: string;
};

type Flashcard = {
  id: number;
  deck_id: number;
  front: string;
  back: string;
  status: string;
  review_count: number;
  last_reviewed_at: string | null;
  next_review_at: string | null;
  created_at: string;
};

export function LearnLoopView({ token, initialDeckId }: { token: string; initialDeckId?: number | null }) {
  const [decks, setDecks] = useState<Deck[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  // Study session mode
  const [activeDeck, setActiveDeck] = useState<Deck | null>(null);
  const [sessionCards, setSessionCards] = useState<Flashcard[]>([]);
  const [currentCardIndex, setCurrentCardIndex] = useState(0);
  const [isAnswerRevealed, setIsAnswerRevealed] = useState(false);
  const [sessionCompleted, setSessionCompleted] = useState(false);

  // Deck creation
  const [showAddDeck, setShowAddDeck] = useState(false);
  const [newDeckTitle, setNewDeckTitle] = useState("");
  const [newDeckDesc, setNewDeckDesc] = useState("");

  // Card addition
  const [addingCardToDeck, setAddingCardToDeck] = useState<Deck | null>(null);
  const [newCardFront, setNewCardFront] = useState("");
  const [newCardBack, setNewCardBack] = useState("");

  useEffect(() => {
    fetchDecks();
  }, [token]);

  useEffect(() => {
    if (initialDeckId && decks.length > 0) {
      const target = decks.find((d) => d.id === initialDeckId);
      if (target) {
        startStudySession(target, false);
      }
    }
  }, [initialDeckId, decks]);

  async function fetchDecks() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/learnloop/decks", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to load study decks");
      const data = await res.json();
      setDecks(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error loading decks");
    } finally {
      setLoading(false);
    }
  }

  async function startStudySession(deck: Deck, dueOnly: boolean = false) {
    setError("");
    setSuccessMsg("");
    try {
      const res = await fetch(`/api/learnloop/decks/${deck.id}/cards${dueOnly ? "?due_only=true" : ""}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to load cards for study");
      const cards: Flashcard[] = await res.json();
      if (cards.length === 0) {
        setSuccessMsg(`No cards due for "${deck.title}". Great job staying up to date!`);
        return;
      }
      setActiveDeck(deck);
      setSessionCards(cards);
      setCurrentCardIndex(0);
      setIsAnswerRevealed(false);
      setSessionCompleted(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to start study session");
    }
  }

  async function handleReviewCard(rating: "hard" | "good" | "easy") {
    if (!sessionCards[currentCardIndex]) return;
    const cardId = sessionCards[currentCardIndex].id;

    try {
      const res = await fetch(`/api/learnloop/cards/${cardId}/review`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ rating }),
      });
      if (!res.ok) throw new Error("Failed to record review");

      if (currentCardIndex + 1 < sessionCards.length) {
        setCurrentCardIndex((idx) => idx + 1);
        setIsAnswerRevealed(false);
      } else {
        setSessionCompleted(true);
        fetchDecks();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Review error");
    }
  }

  async function handleCreateDeck(e: FormEvent) {
    e.preventDefault();
    setError("");
    setSuccessMsg("");
    try {
      const res = await fetch("/api/learnloop/decks", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          title: newDeckTitle,
          description: newDeckDesc || undefined,
          initial_cards: [],
        }),
      });
      if (!res.ok) throw new Error("Failed to create study deck");
      setSuccessMsg("New deck created!");
      setNewDeckTitle("");
      setNewDeckDesc("");
      setShowAddDeck(false);
      fetchDecks();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Create deck error");
    }
  }

  async function handleAddCard(e: FormEvent) {
    e.preventDefault();
    if (!addingCardToDeck) return;
    setError("");
    setSuccessMsg("");
    try {
      const res = await fetch(`/api/learnloop/decks/${addingCardToDeck.id}/cards`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          front: newCardFront,
          back: newCardBack,
        }),
      });
      if (!res.ok) throw new Error("Failed to add flashcard");
      setSuccessMsg("Card added successfully!");
      setNewCardFront("");
      setNewCardBack("");
      setAddingCardToDeck(null);
      fetchDecks();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Add card error");
    }
  }

  async function handleDeleteDeck(deckId: number) {
    if (!confirm("Are you sure you want to delete this study deck and all its flashcards?")) return;
    try {
      const res = await fetch(`/api/learnloop/decks/${deckId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to delete deck");
      setDecks((prev) => prev.filter((d) => d.id !== deckId));
      if (activeDeck?.id === deckId) setActiveDeck(null);
      setSuccessMsg("Study deck deleted.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete deck error");
    }
  }

  const currentCard = sessionCards[currentCardIndex];

  return (
    <div className="learnloop-view">
      <div className="view-header">
        <div>
          <h2>LearnLoop</h2>
          <p className="subtitle">Spaced repetition memory loops & active recall flashcards</p>
        </div>
        {!activeDeck && (
          <button className="btn-primary" onClick={() => setShowAddDeck(!showAddDeck)}>
            {showAddDeck ? "Cancel" : "+ Create Study Deck"}
          </button>
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}
      {successMsg && <div className="success-banner">{successMsg}</div>}

      {/* New Deck Form */}
      {showAddDeck && !activeDeck && (
        <form className="add-deck-form" onSubmit={handleCreateDeck}>
          <h3>Create New Deck</h3>
          <div className="form-group">
            <label>Deck Title</label>
            <input
              type="text"
              required
              placeholder="e.g., Python Architecture & Async Mastery"
              value={newDeckTitle}
              onChange={(e) => setNewDeckTitle(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label>Description (optional)</label>
            <input
              type="text"
              placeholder="e.g., Key concepts, design patterns, and interview recall questions"
              value={newDeckDesc}
              onChange={(e) => setNewDeckDesc(e.target.value)}
            />
          </div>
          <div className="form-actions">
            <button type="submit" className="btn-primary">Create Deck</button>
          </div>
        </form>
      )}

      {/* Add Card Modal */}
      {addingCardToDeck && (
        <div className="modal-overlay" onClick={() => setAddingCardToDeck(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Add Flashcard to &quot;{addingCardToDeck.title}&quot;</h3>
              <button className="modal-close" onClick={() => setAddingCardToDeck(null)}>✕</button>
            </div>
            <form onSubmit={handleAddCard}>
              <div className="form-group">
                <label>Front (Question / Prompt)</label>
                <textarea
                  rows={3}
                  required
                  placeholder="e.g., What is the difference between concurrency and parallelism?"
                  value={newCardFront}
                  onChange={(e) => setNewCardFront(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Back (Answer / Explanation)</label>
                <textarea
                  rows={4}
                  required
                  placeholder="e.g., Concurrency is about dealing with lots of things at once; parallelism is about doing lots of things at once."
                  value={newCardBack}
                  onChange={(e) => setNewCardBack(e.target.value)}
                />
              </div>
              <div className="form-actions">
                <button type="submit" className="btn-primary">Save Card</button>
                <button type="button" className="btn-secondary" onClick={() => setAddingCardToDeck(null)}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Study Session Active */}
      {activeDeck && (
        <div className="study-session-card">
          <div className="study-session-header">
            <div>
              <h3>{activeDeck.title}</h3>
              <span className="session-progress-text">
                Card {sessionCards.length > 0 ? currentCardIndex + 1 : 0} of {sessionCards.length}
              </span>
            </div>
            <button className="btn-outline btn-sm" onClick={() => setActiveDeck(null)}>
              Exit Study Session
            </button>
          </div>

          {sessionCompleted ? (
            <div className="session-complete-box">
              <span className="celebration-icon">🎉</span>
              <h4>Session Complete!</h4>
              <p>You&apos;ve reviewed all {sessionCards.length} cards in this study loop.</p>
              <button className="btn-primary" onClick={() => setActiveDeck(null)}>
                Back to Decks
              </button>
            </div>
          ) : currentCard ? (
            <div className="flashcard-interactive">
              <div className="flashcard-front">
                <span className="card-label">PROMPT / QUESTION</span>
                <p className="card-text">{currentCard.front}</p>
              </div>

              {!isAnswerRevealed ? (
                <div className="reveal-actions">
                  <button className="btn-primary btn-lg" onClick={() => setIsAnswerRevealed(true)}>
                    Reveal Answer (Space)
                  </button>
                </div>
              ) : (
                <div className="flashcard-back">
                  <span className="card-label">ANSWER / EXPLANATION</span>
                  <p className="card-text answer">{currentCard.back}</p>

                  <div className="rating-prompt">
                    <span>How well did you recall this?</span>
                    <div className="rating-buttons">
                      <button
                        className="btn-rating btn-hard"
                        onClick={() => handleReviewCard("hard")}
                      >
                        Hard <small>(1 day)</small>
                      </button>
                      <button
                        className="btn-rating btn-good"
                        onClick={() => handleReviewCard("good")}
                      >
                        Good <small>(3 days)</small>
                      </button>
                      <button
                        className="btn-rating btn-easy"
                        onClick={() => handleReviewCard("easy")}
                      >
                        Easy <small>(7 days)</small>
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p>No cards to display.</p>
          )}
        </div>
      )}

      {/* Decks Grid */}
      {!activeDeck && (
        <div className="decks-grid">
          {loading ? (
            <p className="loading-notice">Loading study decks…</p>
          ) : decks.length === 0 ? (
            <p className="empty-notice">No study decks yet. Create one or generate from DocuVault!</p>
          ) : (
            decks.map((deck) => (
              <div key={deck.id} className="deck-card">
                <div className="deck-card-header">
                  <span className="deck-icon">🗂️</span>
                  <h4>{deck.title}</h4>
                </div>
                {deck.description && <p className="deck-desc">{deck.description}</p>}

                <div className="deck-stats-row">
                  <span className="stat-pill total">
                    <strong>{deck.card_count}</strong> Total Cards
                  </span>
                  <span className="stat-pill due">
                    <strong>{deck.due_count}</strong> Due Now
                  </span>
                  <span className="stat-pill mastered">
                    <strong>{deck.mastered_count}</strong> Mastered
                  </span>
                </div>

                <div className="deck-actions">
                  <button
                    className="btn-primary btn-sm"
                    disabled={deck.card_count === 0}
                    onClick={() => startStudySession(deck, deck.due_count > 0)}
                  >
                    {deck.due_count > 0 ? `⚡ Review Due (${deck.due_count})` : "Practice All"}
                  </button>
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => setAddingCardToDeck(deck)}
                  >
                    + Add Card
                  </button>
                  <button
                    className="btn-danger btn-sm"
                    onClick={() => handleDeleteDeck(deck.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
