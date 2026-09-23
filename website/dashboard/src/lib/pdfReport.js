import { jsPDF } from 'jspdf';

const SEV_RGB = {
  critical: [239, 68, 68],
  high: [255, 138, 61],
  medium: [245, 166, 35],
  low: [34, 197, 94],
  nominal: [34, 197, 94],
  informational: [74, 222, 128],
};

async function fetchImageAsBase64(url) {
  try {
    const res = await fetch(url);
    const blob = await res.blob();
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  } catch (err) {
    return null;
  }
}

export async function downloadIncidentReport(item) {
  if (!item || item.kind !== 'incident') return;
  const doc = new jsPDF({ unit: 'mm', format: 'a4' });
  const W = doc.internal.pageSize.getWidth();
  const H = doc.internal.pageSize.getHeight();
  const M = 16;
  const color = SEV_RGB[item.severity] || SEV_RGB.informational;

  // ── Header band ────────────────────────────────────────────────────────────
  doc.setFillColor(...color);
  doc.rect(0, 0, W, 14, 'F');
  doc.setTextColor(10, 14, 20);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(13);
  doc.text('SEEMA DRISHTI — INCIDENT REPORT', M, 8.5);
  doc.setTextColor(255, 255, 255);
  doc.setFontSize(9);
  doc.setFont('helvetica', 'normal');
  doc.text(item.dangerLabel || item.severity.toUpperCase(), W - M, 8.5, { align: 'right' });

  let y = 24;

  // ── Title block ────────────────────────────────────────────────────────────
  doc.setTextColor(20, 24, 30);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(16);
  const titleLines = doc.splitTextToSize(item.title || 'Incident', W - M * 2);
  doc.text(titleLines, M, y);
  y += titleLines.length * 7 + 2;

  doc.setDrawColor(...color);
  doc.setLineWidth(0.6);
  doc.line(M, y, W - M, y);
  y += 6;

  // ── Key-value metadata (single-pass per row) ──────────────────────────────
  const plates = item.plateNumbers?.length ? item.plateNumbers.join(', ') : (item.plateNo || '—');
  const wanted = item.watchlistHits?.length ? item.watchlistHits.join(', ') : (item.watchlistHit ? (item.plateNo || 'MATCHED') : '—');
  const kvRows = [
    ['Incident ID', item._id || '—'],
    ['Severity', item.dangerLabel || item.severity || '—'],
    ['Threat Score', item.dangerScore != null ? `${item.dangerScore}/100` : '—'],
    ['Status', (item.status || '—').toUpperCase()],
    ['Location', item.location || '—'],
    ['Camera', item.cameraName || item.cameraId || '—'],
    ['Module(s)', item.modules?.join(', ') || item.module || '—'],
    ['Plate(s)', plates],
    ['Watchlist Hit', wanted],
    ['Started', item.startedAt ? new Date(item.startedAt).toLocaleString() : '—'],
    ['Last Updated', item.timestamp ? new Date(item.timestamp).toLocaleString() : '—'],
    ['Track ID(s)', item.trackId || item._raw?.track_ids?.join(', ') || '—'],
  ];

  const labelX = M;
  const valueX = M + 38;
  const valueMaxW = W - M - valueX;
  const rowH = 4.5;

  doc.setFontSize(9);
  for (const [k, v] of kvRows) {
    // label
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(90, 107, 127);
    doc.text(k.toUpperCase(), labelX, y);

    // value (may wrap)
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(40, 46, 55);
    const vLines = doc.splitTextToSize(String(v), valueMaxW);
    doc.text(vLines, valueX, y);
    y += Math.max(vLines.length, 1) * rowH;
  }
  y += 6;

  // ── Detection summary ──────────────────────────────────────────────────────
  const summaryH = 22;
  doc.setFillColor(17, 23, 18);
  doc.rect(M, y, W - M * 2, summaryH, 'F');

  doc.setTextColor(219, 228, 238);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(12);
  doc.text('Detection Summary', M + 5, y + 6);

  const dets = [
    { label: 'Humans', value: item.humansDetected || 0 },
    { label: 'Vehicles', value: item.vehiclesDetected || 0 },
    { label: 'Weapons', value: item.weaponsDetected || 0 },
    { label: 'Faces', value: item.facesCaptured || 0 },
    { label: 'Snapshots', value: item.snapshotCount || 0 },
  ];
  const cellW = (W - M * 2 - 10) / dets.length;
  dets.forEach((d, i) => {
    const cx = M + 5 + i * cellW;
    doc.setFontSize(16);
    doc.setTextColor(255, 255, 255);
    doc.text(String(d.value), cx + cellW / 2, y + 13, { align: 'center' });
    doc.setFontSize(7.5);
    doc.setTextColor(139, 152, 171);
    doc.text(d.label.toUpperCase(), cx + cellW / 2, y + 18, { align: 'center' });
  });
  y += summaryH + 8;

  // ── Tags / details ────────────────────────────────────────────────────────
  const zoneTags = item.zoneBreaches?.length ? item.zoneBreaches.map((z) => 'Zone: ' + z) : [];
  const actTags = item.activities?.length ? item.activities : [];
  const plateTags = item.plateNumbers?.length ? item.plateNumbers.map((p) => 'Plate: ' + p) : [];
  const vehTags = item.vehicleTypes?.length ? item.vehicleTypes : [];
  const tagGroup = [...zoneTags, ...actTags, ...plateTags, ...vehTags];

  if (tagGroup.length && y < H - 40) {
    doc.setTextColor(20, 24, 30);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(11);
    doc.text('Details', M, y);
    y += 5;
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor(90, 107, 127);
    for (const tag of tagGroup) {
      const tLines = doc.splitTextToSize(tag, W - M * 2);
      doc.text(tLines, M, y);
      y += tLines.length * 4.4;
      if (y > H - 30) break;
    }
  }

  // ── Evidence photos: car snapshot + driver capture(s) ────────────────────
  // snapshots[0] is the vehicle crop; driverSnapshots hold the windshield crop.
  const evidenceImgs = [];
  if (item.snapshotUrl) evidenceImgs.push({ url: item.snapshotUrl, caption: 'Vehicle capture' });
  (item.driverSnapshots || []).forEach((u, i) => {
    if (!evidenceImgs.some((e) => e.url === u)) evidenceImgs.push({ url: u, caption: `Driver capture ${i + 1}` });
  });
  (item.snapshots || []).slice(0, 4).forEach((u, i) => {
    if (!evidenceImgs.some((e) => e.url === u)) evidenceImgs.push({ url: u, caption: `Snapshot ${i + 1}` });
  });
  for (const ev of evidenceImgs.slice(0, 5)) {
    try {
      const imgData = await fetchImageAsBase64(ev.url);
      if (imgData) {
        y += 5;
        const imgW = W - M * 2;
        const imgH = imgW * 9 / 16;
        if (y + imgH + 8 > H - 20) {
          doc.addPage();
          y = M;
        }
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(9);
        doc.setTextColor(90, 107, 127);
        doc.text(ev.caption.toUpperCase(), M, y);
        y += 4;
        doc.addImage(imgData, 'JPEG', M, y, imgW, imgH);
        y += imgH;
      }
    } catch (err) {
      console.warn('Could not embed snapshot', err);
    }
  }

  // ── Footer ─────────────────────────────────────────────────────────────────
  doc.setDrawColor(30, 39, 51);
  doc.setLineWidth(0.3);
  doc.line(M, H - 14, W - M, H - 14);
  doc.setFontSize(7.5);
  doc.setTextColor(139, 152, 171);
  doc.setFont('helvetica', 'normal');
  doc.text(`Generated ${new Date().toLocaleString()} — SEEMA DRISHTI Army Border Intelligence`, M, H - 10);
  doc.setTextColor(...color);
  doc.setFont('helvetica', 'bold');
  doc.text(item._id || '', W - M, H - 10, { align: 'right' });

  doc.save(`incident_report_${(item._id || 'incident').replace(/[^a-zA-Z0-9_-]/g, '_')}.pdf`);
}
