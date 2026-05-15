const sql = require('mssql');
const { filterSensitiveTables } = require('../utils/tableFilter');

function buildConfig(connInfo) {
  const encryptEnabled = connInfo.encrypt === true || connInfo.encrypt === 'true';
  return {
    server: connInfo.server,
    port: parseInt(connInfo.port) || 1433,
    database: connInfo.database,
    user: connInfo.username,
    password: connInfo.password,
    options: {
      encrypt: encryptEnabled,
      trustServerCertificate: encryptEnabled || connInfo.trustCert !== false && connInfo.trustCert !== 'false'
    },
    connectionTimeout: 10000,
    requestTimeout: 30000
  };
}

// POST /api/analytics/table  — get analytics data for a specific table.
async function getTableAnalytics(req, res) {
  const { connInfo, tableName } = req.body;

  if (!connInfo || !tableName) {
    return res.status(400).json({ error: 'connInfo and tableName are required.' });
  }

  // Security: re-check table name isn't sensitive
  const safe = filterSensitiveTables([tableName]);
  if (safe.length === 0) {
    return res.status(403).json({ error: 'Access to this table is not allowed.' });
  }

  // Sanitize table name (allow only alphanumeric, underscore, dash, dot)
  if (!/^[\w.\-]+$/.test(tableName)) {
    return res.status(400).json({ error: 'Invalid table name.' });
  }

  let pool;
  try {
    pool = await sql.connect(buildConfig(connInfo));

    // 1. Row count
    const countResult = await pool.request()
      .query(`SELECT COUNT(*) AS total FROM [${tableName}]`);
    const totalRows = countResult.recordset[0].total;

    // 2. Column info
    const colResult = await pool.request()
      .input('tbl', sql.NVarChar, tableName)
      .query(`
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = @tbl
        ORDER BY ORDINAL_POSITION
      `);
    const columns = colResult.recordset;

    // 3. Sample data (first 100 rows)
    const sampleResult = await pool.request()
      .query(`SELECT TOP 100 * FROM [${tableName}]`);
    const rows = sampleResult.recordset;

    // 4. Build chart data
    const numericCols = columns.filter(c =>
      ['int','bigint','smallint','tinyint','float','real','decimal','numeric','money','smallmoney'].includes(c.DATA_TYPE)
    );
    const dateCols = columns.filter(c =>
      ['date','datetime','datetime2','smalldatetime','datetimeoffset'].includes(c.DATA_TYPE)
    );
    const textCols = columns.filter(c =>
      ['varchar','nvarchar','char','nchar','text','ntext'].includes(c.DATA_TYPE)
    );

    // Numeric column stats
    let numericStats = [];
    for (const col of numericCols.slice(0, 6)) {
      const statsRes = await pool.request().query(`
        SELECT
          MIN([${col.COLUMN_NAME}]) AS min_val,
          MAX([${col.COLUMN_NAME}]) AS max_val,
          AVG(CAST([${col.COLUMN_NAME}] AS FLOAT)) AS avg_val,
          SUM(CAST([${col.COLUMN_NAME}] AS FLOAT)) AS sum_val
        FROM [${tableName}]
        WHERE [${col.COLUMN_NAME}] IS NOT NULL
      `);
      const s = statsRes.recordset[0];
      numericStats.push({
        column: col.COLUMN_NAME,
        min: parseFloat(s.min_val) || 0,
        max: parseFloat(s.max_val) || 0,
        avg: parseFloat(s.avg_val?.toFixed(2)) || 0,
        sum: parseFloat(s.sum_val?.toFixed(2)) || 0
      });
    }

    // Category distribution for first text column
    let categoryData = null;
    if (textCols.length > 0) {
      const catCol = textCols[0].COLUMN_NAME;
      const catRes = await pool.request().query(`
        SELECT TOP 10 [${catCol}] AS label, COUNT(*) AS count
        FROM [${tableName}]
        WHERE [${catCol}] IS NOT NULL AND LEN([${catCol}]) > 0
        GROUP BY [${catCol}]
        ORDER BY count DESC
      `);
      categoryData = {
        column: catCol,
        data: catRes.recordset
      };
    }

    // Time series for first date column + first numeric column
    let timeSeriesData = null;
    if (dateCols.length > 0 && numericCols.length > 0) {
      const dateCol = dateCols[0].COLUMN_NAME;
      const numCol = numericCols[0].COLUMN_NAME;
      const tsRes = await pool.request().query(`
        SELECT TOP 30
          CONVERT(VARCHAR(10), [${dateCol}], 120) AS period,
          SUM(CAST([${numCol}] AS FLOAT)) AS total
        FROM [${tableName}]
        WHERE [${dateCol}] IS NOT NULL
        GROUP BY CONVERT(VARCHAR(10), [${dateCol}], 120)
        ORDER BY period
      `);
      timeSeriesData = {
        dateColumn: dateCol,
        valueColumn: numCol,
        data: tsRes.recordset
      };
    }

    res.json({
      tableName,
      totalRows,
      columns,
      numericStats,
      categoryData,
      timeSeriesData,
      sampleRows: rows.slice(0, 10)
    });
  } catch (err) {
    console.error('Analytics error:', err.message);
    res.status(500).json({ error: `Analytics failed: ${err.message}` });
  } finally {
    if (pool) await pool.close();
  }
}

module.exports = { getTableAnalytics };
