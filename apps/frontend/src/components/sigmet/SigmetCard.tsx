import { useState, useEffect } from 'react';

export interface SigmetItem {
  hazard: string;
  validTimeFrom: string;
  validTimeTo: string;
  source: string;
  enabled: boolean;
}

export function SigmetCard({ lat, lon }: { lat: number; lon: number }) {
  const [data, setData] = useState<SigmetItem | null>(null);
  useEffect(() => {
    fetch(`/api/sigmet?lat=${lat}&lon=${lon}&radio_km=200`, { headers: { 'User-Agent': 'SkypulseAR/1.0' } })
      .then(r => r.json()).then((j: any) => { if (j?.enabled && j?.data?.length) setData({ ...j.data[0], enabled: j.enabled, source: j.source }); })
      .catch(() => setData(null));
  }, [lat, lon]);
  if (!data) return <div style={{ padding: 8, fontSize: 12, opacity: 0.6 }}>SIGMET: sin avisos (A.3 OK / A.4 pendiente deploy)</div>;
  return (
    <div style={{ padding: 10, border: '1px solid #ccc', borderRadius: 8, background: '#fff9e6', marginTop: 8 }}>
      <strong>⚠️ SIGMET</strong> ({data.hazard}) — {data.source} — válido: {data.validTimeFrom} → {data.validTimeTo}
    </div>
  );
}
