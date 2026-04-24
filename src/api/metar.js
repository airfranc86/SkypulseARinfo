module.exports = async function handler(req, res) {
  const { icao, type = 'metar' } = req.query;

  if (!icao || icao.length < 4) {
    return res.status(400).json({ error: 'ICAO requerido (4 caracteres)' });
  }

  const clean = icao.toUpperCase().replace(/[^A-Z0-9]/g, '');
  const key = process.env.CHECKWX_KEY;

  if (!key) {
    return res.status(503).json({ error: 'API key no configurada en el servidor' });
  }

  const endpoint = type === 'taf'
    ? `https://api.checkwx.com/taf/${clean}/decoded`
    : `https://api.checkwx.com/metar/${clean}/decoded`;

  try {
    const upstream = await fetch(endpoint, {
      headers: { 'X-API-Key': key }
    });
    const data = await upstream.json();
    return res.status(upstream.status).json(data);
  } catch (err) {
    return res.status(502).json({ error: `Error al contactar CheckWX: ${err.message}` });
  }
};
