import { FormEvent, useEffect, useState } from "react";

type Document = {
  id: number;
  user_id: number;
  title: string;
  filename: string;
  file_size: number;
  content_type: string;
  content_text: string;
  summary: string | null;
  tags: string[];
  created_at: string;
  updated_at: string | null;
};

type SearchCitation = {
  document_id: number;
  title: string;
  snippet: string;
  match_score: number;
};

type SearchResult = {
  query: string;
  total_matches: number;
  citations: SearchCitation[];
};

export function DocuVaultView({ token, onSwitchToDeck }: { token: string; onSwitchToDeck?: (deckId: number) => void }) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResult, setSearchResult] = useState<SearchResult | null>(null);
  const [searching, setSearching] = useState(false);

  // New document form state
  const [showAddForm, setShowAddForm] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newFilename, setNewFilename] = useState("");
  const [newContent, setNewContent] = useState("");
  const [newTags, setNewTags] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Viewing document modal
  const [viewingDoc, setViewingDoc] = useState<Document | null>(null);

  useEffect(() => {
    fetchDocuments();
  }, [token]);

  async function fetchDocuments() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/docuvault/documents", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to load documents");
      const data = await res.json();
      setDocuments(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error loading documents");
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) {
      setSearchResult(null);
      return;
    }
    setSearching(true);
    setError("");
    try {
      const res = await fetch(`/api/docuvault/documents/search?q=${encodeURIComponent(searchQuery)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Search failed");
      const data: SearchResult = await res.json();
      setSearchResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  function clearSearch() {
    setSearchQuery("");
    setSearchResult(null);
  }

  async function handleCreateDocument(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    setSuccessMsg("");
    try {
      const res = await fetch("/api/docuvault/documents", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          title: newTitle,
          filename: newFilename || `${newTitle.toLowerCase().replace(/[^a-z0-9]/g, "_")}.txt`,
          content_text: newContent,
          content_type: "text/plain",
          tags: newTags.split(",").map((t) => t.trim()).filter(Boolean),
        }),
      });
      if (!res.ok) throw new Error("Failed to save document");
      setSuccessMsg("Document stored and indexed successfully!");
      setNewTitle("");
      setNewFilename("");
      setNewContent("");
      setNewTags("");
      setShowAddForm(false);
      fetchDocuments();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create document");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeleteDocument(docId: number) {
    if (!confirm("Are you sure you want to delete this document from your vault?")) return;
    try {
      const res = await fetch(`/api/docuvault/documents/${docId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to delete document");
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
      if (viewingDoc?.id === docId) setViewingDoc(null);
      setSuccessMsg("Document deleted.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete error");
    }
  }

  async function handleGenerateDeck(docId: number) {
    setError("");
    setSuccessMsg("");
    try {
      const res = await fetch(`/api/learnloop/decks/generate-from-doc/${docId}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ num_cards: 4 }),
      });
      if (!res.ok) throw new Error("Could not generate deck from document");
      const deck = await res.json();
      setSuccessMsg(`Generated LearnLoop study deck: "${deck.title}" with ${deck.card_count} flashcards!`);
      if (onSwitchToDeck) {
        onSwitchToDeck(deck.id);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Deck generation error");
    }
  }

  return (
    <div className="docuvault-view">
      <div className="view-header">
        <div>
          <h2>DocuVault</h2>
          <p className="subtitle">Secure document knowledge base with semantic RAG citations</p>
        </div>
        <button
          className="btn-primary"
          onClick={() => setShowAddForm(!showAddForm)}
        >
          {showAddForm ? "Cancel" : "+ Upload / Add Document"}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {successMsg && <div className="success-banner">{successMsg}</div>}

      {/* Add Document Form */}
      {showAddForm && (
        <form className="add-doc-form" onSubmit={handleCreateDocument}>
          <h3>Add New Document to Vault</h3>
          <div className="form-row">
            <div className="form-group">
              <label>Document Title</label>
              <input
                type="text"
                required
                placeholder="e.g., Q3 Project Architecture"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label>Filename (optional)</label>
              <input
                type="text"
                placeholder="e.g., architecture.md"
                value={newFilename}
                onChange={(e) => setNewFilename(e.target.value)}
              />
            </div>
          </div>
          <div className="form-group">
            <label>Tags (comma-separated)</label>
            <input
              type="text"
              placeholder="e.g., architecture, python, specs"
              value={newTags}
              onChange={(e) => setNewTags(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label>Content Text</label>
            <textarea
              rows={6}
              required
              placeholder="Paste or write document text here..."
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
            />
          </div>
          <div className="form-actions">
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? "Saving & Indexing…" : "Save to DocuVault"}
            </button>
          </div>
        </form>
      )}

      {/* RAG Search Bar */}
      <div className="search-section">
        <form onSubmit={handleSearch} className="rag-search-bar">
          <input
            type="text"
            placeholder="Search vault with source citations (e.g., 'concurrency', 'lease', 'database')..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <button type="submit" className="btn-secondary" disabled={searching}>
            {searching ? "Searching…" : "Search"}
          </button>
          {searchResult && (
            <button type="button" className="btn-outline" onClick={clearSearch}>
              Clear
            </button>
          )}
        </form>

        {searchResult && (
          <div className="rag-results-panel">
            <h4>
              Citations for &quot;{searchResult.query}&quot; ({searchResult.total_matches} match
              {searchResult.total_matches === 1 ? "" : "es"})
            </h4>
            {searchResult.citations.length === 0 ? (
              <p className="empty-notice">No citations found matching your query.</p>
            ) : (
              <div className="citations-list">
                {searchResult.citations.map((cite, i) => (
                  <div key={i} className="citation-card">
                    <div className="citation-header">
                      <strong>Source #{cite.document_id}: {cite.title}</strong>
                      <span className="match-tag">Relevance: {(cite.match_score * 100).toFixed(0)}%</span>
                    </div>
                    <blockquote className="citation-snippet">&quot;…{cite.snippet}…&quot;</blockquote>
                    <button
                      className="btn-link"
                      onClick={() => {
                        const target = documents.find((d) => d.id === cite.document_id);
                        if (target) setViewingDoc(target);
                      }}
                    >
                      View Source Document ↗
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Documents List */}
      <div className="documents-section">
        <div className="section-title-row">
          <h3>Indexed Documents ({documents.length})</h3>
        </div>

        {loading ? (
          <p className="loading-notice">Loading documents from vault…</p>
        ) : documents.length === 0 ? (
          <p className="empty-notice">No documents in vault yet. Add one above or explore seeded docs!</p>
        ) : (
          <div className="documents-grid">
            {documents.map((doc) => (
              <div key={doc.id} className="document-card">
                <div className="doc-top">
                  <span className="doc-icon">📄</span>
                  <div className="doc-info">
                    <h4>{doc.title}</h4>
                    <span className="doc-filename">{doc.filename} · {(doc.file_size / 1024).toFixed(1)} KB</span>
                  </div>
                </div>

                {doc.summary && (
                  <p className="doc-summary">{doc.summary}</p>
                )}

                <div className="doc-tags">
                  {doc.tags.map((t, idx) => (
                    <span key={idx} className="doc-tag">#{t}</span>
                  ))}
                </div>

                <div className="doc-actions">
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => setViewingDoc(doc)}
                  >
                    View Text
                  </button>
                  <button
                    className="btn-accent btn-sm"
                    title="Generate flashcards for LearnLoop"
                    onClick={() => handleGenerateDeck(doc.id)}
                  >
                    ⚡ Create Flashcards
                  </button>
                  <button
                    className="btn-danger btn-sm"
                    onClick={() => handleDeleteDocument(doc.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Document View Modal */}
      {viewingDoc && (
        <div className="modal-overlay" onClick={() => setViewingDoc(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{viewingDoc.title}</h3>
              <button className="modal-close" onClick={() => setViewingDoc(null)}>✕</button>
            </div>
            <div className="modal-meta">
              <span><strong>File:</strong> {viewingDoc.filename}</span>
              <span><strong>Size:</strong> {viewingDoc.file_size} bytes</span>
              <span><strong>Type:</strong> {viewingDoc.content_type}</span>
            </div>
            <pre className="modal-text-body">{viewingDoc.content_text}</pre>
            <div className="modal-footer">
              <button
                className="btn-accent"
                onClick={() => {
                  handleGenerateDeck(viewingDoc.id);
                  setViewingDoc(null);
                }}
              >
                ⚡ Generate Study Deck from this Document
              </button>
              <button className="btn-secondary" onClick={() => setViewingDoc(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
