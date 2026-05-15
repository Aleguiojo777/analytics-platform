// Simple in-memory user store
// In production, replace this with a real database (e.g., SQL Server users table)
const users = [];

module.exports = {
  findByEmail: (email) => users.find(u => u.email === email.toLowerCase()),
  findById: (id) => users.find(u => u.id === id),
  create: (user) => {
    const newUser = { ...user, id: Date.now().toString(), email: user.email.toLowerCase() };
    users.push(newUser);
    return newUser;
  },
  all: () => users
};
