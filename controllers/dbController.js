const sql = require('mssql');
const { filterSensitiveTables } = require('../utils/tableFilter');

// POST /api/db/connect  — test connection and return available tables
async function connect(req, res) {
  const { server, port, database, username, password, encrypt, trustCert } = req.body;

  if (!server || !database || !username || !password) {
    return res.status(400).json({ error: 'server, database, username, and password are required.' });
  }

  let portNumber;
  if (port) {
    portNumber = parseInt(port, 10);
    if (Number.isNaN(portNumber)) {
      return res.status(400).json({ error: 'Port must be a valid number.' });
    }
  }

  const encryptEnabled = encrypt === true || encrypt === 'true';
  const config = {
    server,
    ...(portNumber ? { port: portNumber } : {}),
    database,
    user: username,
    password,
    options: {
      encrypt: encryptEnabled,
      trustServerCertificate: encryptEnabled || trustCert !== false && trustCert !== 'false'
    },
    connectionTimeout: 10000,
    requestTimeout: 15000
  };

  let pool;
  try {
    pool = await sql.connect(config);

    // Get all user tables
    const result = await pool.request().query(`
      SELECT TABLE_NAME
      FROM INFORMATION_SCHEMA.TABLES
      WHERE TABLE_TYPE = 'BASE TABLE'
      ORDER BY TABLE_NAME
    `);

    const allTables = result.recordset.map(r => r.TABLE_NAME);
    const safeTables = filterSensitiveTables(allTables);

    // Store connection config in request session-like object (stateless — client sends it each time)
    res.json({
      message: `Connected to "${database}" successfully.`,
      database,
      tables: safeTables,
      tableCount: safeTables.length
    });
  } catch (err) {
    console.error('DB connect error:', err.message);
    res.status(500).json({ error: `Connection failed: ${err.message}` });
  } finally {
    if (pool) await pool.close();
  }
}

module.exports = { connect };
