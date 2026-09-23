import { useState, useEffect } from 'react';
import { Car, Plus, X, Trash2, AlertTriangle, Siren } from 'lucide-react';

export default function WatchlistManager({ onClose }) {
  const [plates, setPlates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const [plate, setPlate] = useState('');
  const [owner, setOwner] = useState('');
  const [notes, setNotes] = useState('');

  useEffect(() => {
    fetchPlates();
  }, []);

  const fetchPlates = async () => {
    try {
      const res = await fetch('/api/watchlist');
      const data = await res.json();
      if (data.status === 'success') setPlates(data.data);
    } catch (err) {
      setError('Failed to fetch watchlist.');
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!plate.trim()) {
      setError('Plate number is required.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const res = await fetch('/api/watchlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plate: plate.trim(), owner, notes }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Add failed');
      setPlate('');
      setOwner('');
      setNotes('');
      fetchPlates();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (p) => {
    try {
      const res = await fetch(`/api/watchlist/${encodeURIComponent(p)}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      fetchPlates();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="flex w-full max-w-2xl flex-col overflow-hidden rounded-lg border border-hairline bg-panel shadow-2xl">
        <div className="flex items-center justify-between border-b border-hairline px-4 py-3">
          <div className="flex items-center gap-2">
            <Siren className="h-5 w-5 text-sev-critical" />
            <h2 className="text-[15px] font-semibold text-fg">Number-Plate Watchlist</h2>
          </div>
          <button onClick={onClose} className="rounded p-1 hover:bg-white/10 text-ghost hover:text-fg">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex flex-col md:flex-row min-h-[400px]">
          {/* Add Form */}
          <div className="w-full md:w-1/2 border-b md:border-b-0 md:border-r border-hairline p-4 bg-panel-2">
            <h3 className="mono text-[11px] font-semibold tracking-wider text-ghost uppercase mb-4">Flag a Vehicle</h3>
            <form onSubmit={handleAdd} className="flex flex-col gap-4">
              <label className="flex flex-col gap-1">
                <span className="mono text-[10px] uppercase text-dim">Plate Number *</span>
                <input
                  type="text"
                  value={plate}
                  onChange={(e) => setPlate(e.target.value.toUpperCase())}
                  className="rounded border border-hairline bg-panel px-3 py-1.5 text-[13px] font-mono font-bold tracking-widest text-fg outline-none focus:border-sev-critical"
                  placeholder="e.g. PB02AB1234"
                  required
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="mono text-[10px] uppercase text-dim">Owner / Suspect</span>
                <input
                  type="text"
                  value={owner}
                  onChange={(e) => setOwner(e.target.value)}
                  className="rounded border border-hairline bg-panel px-3 py-1.5 text-[13px] text-fg outline-none focus:border-sev-critical"
                  placeholder="Optional"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="mono text-[10px] uppercase text-dim">Notes</span>
                <input
                  type="text"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="rounded border border-hairline bg-panel px-3 py-1.5 text-[13px] text-fg outline-none focus:border-sev-critical"
                  placeholder="e.g. stolen, suspect vehicle"
                />
              </label>
              {error && (
                <div className="flex items-center gap-2 rounded bg-sev-critical/20 px-3 py-2 text-[12px] text-sev-critical">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  <span>{error}</span>
                </div>
              )}
              <button
                type="submit"
                disabled={saving}
                className="mt-2 flex items-center justify-center gap-2 rounded bg-sev-critical px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-sev-critical/90 disabled:opacity-50"
              >
                {saving ? <span className="animate-pulse">Adding…</span> : <><Plus className="h-4 w-4" /> Flag Plate</>}
              </button>
              <p className="mono text-[10px] text-dim leading-relaxed">
                Any CCTV that reads this plate fires a critical alert with car + driver photos.
              </p>
            </form>
          </div>

          {/* List */}
          <div className="w-full md:w-1/2 p-4 flex flex-col">
            <h3 className="mono text-[11px] font-semibold tracking-wider text-ghost uppercase mb-4">Flagged Plates</h3>
            <div className="flex-1 overflow-y-auto">
              {loading ? (
                <div className="text-[12px] text-dim animate-pulse">Loading watchlist…</div>
              ) : plates.length === 0 ? (
                <div className="text-[12px] text-dim text-center mt-10">No plates flagged.</div>
              ) : (
                <div className="flex flex-col gap-2">
                  {plates.map((p) => (
                    <div key={p.plate} className="flex items-center gap-3 rounded border border-sev-critical/30 bg-panel-2 p-2">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded border border-sev-critical/50 bg-black">
                        <Car className="h-5 w-5 text-sev-critical" />
                      </div>
                      <div className="flex flex-col min-w-0">
                        <span className="text-[13px] font-mono font-bold tracking-widest text-fg">{p.plate}</span>
                        {(p.owner || p.notes) && (
                          <span className="mono text-[10px] text-ghost truncate">
                            {[p.owner, p.notes].filter(Boolean).join(' · ')}
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => handleDelete(p.plate)}
                        className="ml-auto rounded p-1.5 text-ghost hover:text-sev-critical hover:bg-sev-critical/10"
                        title="Remove from watchlist"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
