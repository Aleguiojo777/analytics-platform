// Keywords that indicate sensitive/system tables to hide from users
const SENSITIVE_KEYWORDS = [
  'user', 'password', 'auth', 'credential', 'token',
  'admin', 'role', 'permission', 'secret', 'session',
  'audit', 'log', 'key', 'hash', 'salt'
];

/**
 * Filter out tables whose names contain sensitive keywords
 * @param {string[]} tableNames
 * @returns {string[]} safe table names
 */
function filterSensitiveTables(tableNames) {
  return tableNames.filter(name => {
    const lower = name.toLowerCase();
    return !SENSITIVE_KEYWORDS.some(keyword => lower.includes(keyword));
  });
}

module.exports = { filterSensitiveTables, SENSITIVE_KEYWORDS };
