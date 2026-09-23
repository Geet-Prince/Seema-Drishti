import { useState, useEffect } from 'react';
import { Users, Upload, X, Check, AlertTriangle, ShieldCheck, Fingerprint, Trash2 } from 'lucide-react';

export default function PersonnelManager({ onClose }) {
  const [personnel, setPersonnel] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const [name, setName] = useState('');
  const [badge, setBadge] = useState('');
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);

  useEffect(() => { fetchPersonnel(); }, []);

  const fetchPersonnel = async () => {
    try {
      const res = await fetch('/api/personnel');
      const data = await res.json();
      if (data.status === 'success') setPersonnel(data.data);
    } catch (err) {
      setError('Failed to fetch personnel list.');
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e) => {
    const f = e.target.files[0];
    setFile(f);
    if (f) {
      const url = URL.createObjectURL(f);
      setPreview(url);
    } else {
      setPreview(null);
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!name || !file) { setError('Name and Image are required.'); return; }
    setUploading(true);
    setError('');
    setSuccessMsg('');
    const formData = new FormData();
    formData.append('name', name);
    formData.append('badge_number', badge);
    formData.append('file', file);
    try {
      const res = await fetch('/api/personnel', { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Upload failed');
      setName(''); setBadge(''); setFile(null); setPreview(null);
      setSuccessMsg(`${name} enrolled successfully — pipeline reloaded.`);
      setTimeout(() => setSuccessMsg(''), 4000);
      fetchPersonnel();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (person) => {
    if (!window.confirm(`Remove "${person.name}" from the registry? The live pipeline will stop recognising this face immediately.`)) return;
    setDeletingId(person.id);
    setError('');
    try {
      const res = await fetch(`/api/personnel/${person.id}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Delete failed');
      setSuccessMsg(`${person.name} removed — pipeline reloaded.`);
      setTimeout(() => setSuccessMsg(''), 4000);
      fetchPersonnel();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeletingId(null);
    }
  };

  const inputCls = 'w-full rounded-sm border border-[rgba(0,240,255,0.2)] bg-black/50 px-3 py-2 text-[13px] text-white outline-none transition-colors placeholder:text-[#5f7a95]/60 focus:border-[#00f0ff] focus:shadow-[0_0_12px_rgba(0,240,255,0.2)]';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-md">
      <div className="hud-panel flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[rgba(0,240,255,0.14)] bg-black/40 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <Fingerprint className="h-5 w-5 text-[#8b5cf6]" style={{ filter: 'drop-shadow(0 0 6px rgba(139,92,246,0.9))' }} />
            <div>
              <h2 className="font-display text-[13px] font-bold tracking-[0.18em] text-white">PERSONNEL VAULT</h2>
              <p className="mono text-[9px] tracking-[0.25em] text-[#5f7a95]">BIOMETRIC REGISTRY · CLEARANCE DB</p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-sm border border-white/10 bg-white/5 p-1.5 text-[#9db4cc] transition-colors hover:border-[rgba(255,45,85,0.5)] hover:text-[#ff8fa3]">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex min-h-0 flex-col md:flex-row">
          {/* ── Left: Enroll form ── */}
          <div className="w-full border-b border-[rgba(0,240,255,0.12)] bg-[rgba(139,92,246,0.04)] p-4 md:w-1/2 md:border-b-0 md:border-r">
            <h3 className="hud-title mb-4 !text-[#8b5cf6]" style={{ textShadow: '0 0 12px rgba(139,92,246,0.6)' }}>+ Enroll Operative</h3>
            <form onSubmit={handleUpload} className="flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="hud-label">Full Name *</span>
                <input type="text" value={name} onChange={e => setName(e.target.value)} className={inputCls} placeholder="e.g. Soldier Ram" required />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="hud-label">Badge Number</span>
                <input type="text" value={badge} onChange={e => setBadge(e.target.value)} className={inputCls} placeholder="SSB-0000" />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="hud-label">Face Scan *</span>
                <input type="file" accept="image/*" onChange={handleFileChange} required
                  className="w-full rounded-sm border border-dashed border-[rgba(0,240,255,0.3)] bg-black/50 px-3 py-2.5 text-[12px] text-white file:mr-2 file:rounded-sm file:border file:border-[rgba(0,240,255,0.3)] file:bg-[rgba(0,240,255,0.1)] file:px-2 file:py-1 file:mono file:text-[10px] file:text-[#00f0ff]" />
              </label>

              {/* Image preview */}
              {preview && (
                <div className="flex items-center gap-3 rounded-sm border border-[rgba(0,240,255,0.2)] bg-black/40 p-2">
                  <img src={preview} alt="preview" className="h-14 w-14 shrink-0 rounded-sm border border-[#00f0ff]/40 object-cover" />
                  <span className="mono text-[10px] text-[#5f7a95]">Face detected preview</span>
                </div>
              )}

              {error && (
                <div className="flex items-center gap-2 rounded-sm border border-[rgba(255,45,85,0.4)] bg-[rgba(255,45,85,0.1)] px-3 py-2 text-[12px] text-[#ff8fa3]">
                  <AlertTriangle className="h-4 w-4 shrink-0" /><span>{error}</span>
                </div>
              )}
              {successMsg && (
                <div className="flex items-center gap-2 rounded-sm border border-[rgba(57,255,136,0.4)] bg-[rgba(57,255,136,0.08)] px-3 py-2 text-[12px] text-[#39ff88]">
                  <Check className="h-4 w-4 shrink-0" /><span>{successMsg}</span>
                </div>
              )}

              <button type="submit" disabled={uploading}
                className="mt-1 flex items-center justify-center gap-2 rounded-sm border border-[rgba(0,240,255,0.5)] bg-[rgba(0,240,255,0.12)] px-4 py-2.5 mono text-[11px] font-bold uppercase tracking-[0.2em] text-[#00f0ff] transition-all hover:bg-[rgba(0,240,255,0.22)] hover:shadow-[0_0_20px_rgba(0,240,255,0.4)] disabled:opacity-50">
                {uploading ? <span className="animate-pulse">◌ Analyzing biometrics…</span> : <><Upload className="h-4 w-4" /> Enroll Identity</>}
              </button>
            </form>
          </div>

          {/* ── Right: Registry list ── */}
          <div className="flex w-full min-h-0 flex-col p-4 md:w-1/2">
            <h3 className="hud-title mb-4">Registry · {personnel.length}</h3>
            <div className="min-h-0 flex-1 overflow-y-auto pr-1">
              {loading ? (
                <div className="animate-pulse mono text-[12px] text-[#5f7a95]">◌ Decrypting registry…</div>
              ) : personnel.length === 0 ? (
                <div className="mt-10 flex flex-col items-center gap-2 text-center">
                  <Users className="h-8 w-8 text-[#5f7a95]/40" />
                  <div className="mono text-[11px] tracking-[0.2em] text-[#5f7a95]">VAULT EMPTY</div>
                  <div className="mono text-[10px] text-[#5f7a95]/60">Enroll an operative to begin face recognition</div>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  {personnel.map(p => (
                    <div key={p.id} className="group flex items-center gap-3 rounded-sm border border-[rgba(0,240,255,0.15)] bg-black/40 p-2 transition-colors hover:border-[rgba(0,240,255,0.35)]">
                      <img
                        src={p.image_path}
                        alt=""
                        className="h-10 w-10 shrink-0 rounded-full border border-[#00f0ff]/60 object-cover"
                        style={{ boxShadow: '0 0 10px rgba(0,240,255,0.3)' }}
                        onError={e => { e.target.style.display = 'none'; }}
                      />
                      <div className="flex min-w-0 flex-col flex-1">
                        <span className="truncate text-[13px] font-semibold text-white">{p.name}</span>
                        {p.badge_number && <span className="mono text-[10px] tracking-widest text-[#00f0ff]/70">[{p.badge_number}]</span>}
                      </div>
                      <span className="flex items-center gap-1 rounded-sm border border-[rgba(57,255,136,0.4)] bg-[rgba(57,255,136,0.08)] px-1.5 py-0.5 mono text-[9px] text-[#39ff88]">
                        <ShieldCheck className="h-3 w-3" /> CLR
                      </span>
                      {/* Delete button */}
                      <button
                        onClick={() => handleDelete(p)}
                        disabled={deletingId === p.id}
                        title="Remove from registry"
                        className="rounded-sm border border-transparent bg-transparent p-1 text-[#5f7a95] opacity-0 transition-all group-hover:opacity-100 hover:border-[rgba(255,45,85,0.5)] hover:bg-[rgba(255,45,85,0.1)] hover:text-[#ff8fa3] disabled:opacity-30"
                      >
                        {deletingId === p.id
                          ? <span className="animate-pulse text-[10px]">…</span>
                          : <Trash2 className="h-3.5 w-3.5" />}
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
