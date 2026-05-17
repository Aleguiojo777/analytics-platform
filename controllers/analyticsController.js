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

    const looksLikeId = name => /(?:^|_)(?:id|rowid|serial)$|id$/i.test(name);
    const analysisNumericCols = numericCols.filter(c => !looksLikeId(c.COLUMN_NAME));
    const numericAnalysisCols = analysisNumericCols.length > 0 ? analysisNumericCols : numericCols;

    // Numeric column stats
    let numericStats = [];
    for (const col of numericAnalysisCols.slice(0, 6)) {
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
    if (dateCols.length > 0 && numericAnalysisCols.length > 0) {
      const dateCol = dateCols[0].COLUMN_NAME;
      const numCol = numericAnalysisCols[0].COLUMN_NAME;
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

// Helper functions for AI insights
function mean(arr) { return arr.reduce((a, b) => a + b, 0) / arr.length; }
function median(arr) { const sorted = [...arr].sort((a, b) => a - b); return sorted[Math.floor(sorted.length / 2)]; }
function stdDev(arr) { const avg = mean(arr); return Math.sqrt(arr.reduce((sq, n) => sq + Math.pow(n - avg, 2), 0) / arr.length); }
function min(arr) { return Math.min(...arr); }
function max(arr) { return Math.max(...arr); }

function detectAnomalies(values, threshold = 2.5) {
  if (values.length < 4) return [];
  const avg = mean(values);
  const std = stdDev(values);
  if (std === 0) return [];
  return values.map((val, idx) => {
    const z_score = Math.abs((val - avg) / std);
    if (z_score > threshold) {
      const anomaly_type = val > avg ? 'high' : 'low';
      const deviation_pct = avg !== 0 ? Math.abs((val - avg) / avg * 100) : 0;
      return {
        value: parseFloat(val.toFixed(2)),
        index: idx,
        zScore: parseFloat(z_score.toFixed(2)),
        type: anomaly_type,
        deviationPercent: parseFloat(deviation_pct.toFixed(1)),
        expectedRange: `${(avg - std).toFixed(2)} to ${(avg + std).toFixed(2)}`,
        severity: z_score > 4 ? 'critical' : z_score > 3 ? 'high' : 'moderate'
      };
    }
  }).filter(a => a);
}

function analyzeTrend(values) {
  if (values.length < 2) return null;
  const n = values.length;
  const xMean = (n - 1) / 2;
  const yMean = mean(values);
  const numerator = values.reduce((sum, y, i) => sum + (i - xMean) * (y - yMean), 0);
  const denominator = values.reduce((sum, _, i) => sum + Math.pow(i - xMean, 2), 0);
  const slope = numerator / denominator;
  const intercept = yMean - slope * xMean;
  const predictions = values.map((y, i) => slope * i + intercept);
  const ssRes = values.reduce((sum, y, i) => sum + Math.pow(y - predictions[i], 2), 0);
  const ssTot = values.reduce((sum, y) => sum + Math.pow(y - yMean, 2), 0);
  const rSquared = ssTot === 0 ? 0 : 1 - (ssRes / ssTot);
  let trend = 'stable';
  let strength = 'weak';
  if (Math.abs(slope) > 0.01) trend = slope > 0 ? 'upward' : 'downward';
  if (rSquared > 0.7) strength = 'strong';
  else if (rSquared > 0.4) strength = 'moderate';
  return {trend, slope: parseFloat(slope.toFixed(4)), strength, confidence: parseFloat((rSquared * 100).toFixed(1)), prediction: slope * n + intercept};
}

// POST /api/analytics/executive-summary
async function getExecutiveSummary(req, res) {
  const { connInfo, tableName } = req.body;
  if (!connInfo || !tableName) return res.status(400).json({ error: 'connInfo and tableName required.' });
  
  const safe = filterSensitiveTables([tableName]);
  if (safe.length === 0) return res.status(403).json({ error: 'Access denied.' });
  if (!/^[\w.\-]+$/.test(tableName)) return res.status(400).json({ error: 'Invalid table name.' });
  
  let pool;
  try {
    pool = await sql.connect(buildConfig(connInfo));
    const colResult = await pool.request().input('tbl', sql.NVarChar, tableName).query(`SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = @tbl`);
    const numericCols = colResult.recordset.filter(c => ['int','bigint','smallint','tinyint','float','real','decimal','numeric','money','smallmoney'].includes(c.DATA_TYPE));
    if (numericCols.length === 0) { await pool.close(); return res.json({ summary: null, message: 'No numeric columns.' }); }
    
    const analyses = [];
    for (const col of numericCols.slice(0, 10)) {
      try {
        const dataResult = await pool.request().query(`SELECT TOP 1000 [${col.COLUMN_NAME}] FROM [${tableName}] WHERE [${col.COLUMN_NAME}] IS NOT NULL`);
        const values = dataResult.recordset.map(r => {const v = r[col.COLUMN_NAME]; return typeof v === 'number' ? v : parseFloat(v);}).filter(v => !isNaN(v));
        if (values.length > 0) {
          const stats = {count: values.length, min: min(values), max: max(values), avg: parseFloat(mean(values).toFixed(2)), median: parseFloat(median(values).toFixed(2)), stdDev: parseFloat(stdDev(values).toFixed(2))};
          const anomalies = detectAnomalies(values, 2.5);
          const trend = analyzeTrend(values);
          analyses.push({column: col.COLUMN_NAME, stats, anomalies, trend});
        }
      } catch (e) { console.warn(`Failed to analyze ${col.COLUMN_NAME}`); }
    }
    
    await pool.close();
    
    // Generate summary
    const summary = { keyMetrics: [], criticalAnomalies: [], trends: [], recommendations: [], dataQualityScore: 0, anomalyDetails: [] };
    const sorted = [...analyses].sort((a, b) => (b.stats.max - b.stats.min) - (a.stats.max - a.stats.min));
    summary.keyMetrics = sorted.slice(0, 3).map(s => ({column: s.column, value: s.stats.avg, range: `${s.stats.min} to ${s.stats.max}`, variation: (((s.stats.max - s.stats.min) / Math.max(Math.abs(s.stats.avg), 1)) * 100).toFixed(1) + '%'}));
    
    let totalAnomalies = 0, criticalCount = 0;
    analyses.forEach(s => {
      if (s.anomalies && s.anomalies.length > 0) {
        summary.criticalAnomalies.push({column: s.column, count: s.anomalies.length});
        totalAnomalies += s.anomalies.length;
        s.anomalies.forEach(a => {
          if (a.severity === 'critical') criticalCount++;
          summary.anomalyDetails.push({column: s.column, ...a});
        });
      }
    });
    
    analyses.forEach(s => {
      if (s.trend && (s.trend.trend === 'upward' || s.trend.trend === 'downward')) {
        summary.trends.push({column: s.column, direction: s.trend.trend, strength: s.trend.strength, confidence: s.trend.confidence + '%'});
      }
    });
    
    if (criticalCount > 0) summary.recommendations.push(`🔴 CRITICAL: ${criticalCount} critical anomalies detected. Immediate investigation required.`);
    if (!summary.criticalAnomalies.length) summary.recommendations.push('✓ No anomalies detected. Data appears clean.');
    if (summary.trends.some(t => t.direction === 'downward')) summary.recommendations.push('📉 Review declining metrics - investigate root causes.');
    if (summary.trends.some(t => t.direction === 'upward')) summary.recommendations.push('📈 Monitor upward trends - identify growth drivers.');
    
    summary.dataQualityScore = Math.max(0, 100 - (totalAnomalies * 10) - (criticalCount * 10));
    
    return res.json({tableName, columnCount: numericCols.length, analyzedColumns: analyses.length, summary, detailedAnalysis: analyses});
  } catch (err) {
    console.error('Executive summary error:', err.message);
    return res.status(500).json({ error: 'Failed to generate summary.' });
  }
}

module.exports = { getTableAnalytics, getExecutiveSummary };
