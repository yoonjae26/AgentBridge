# Security review: accounts.py

1. **find_user** - SQL injection: the username is interpolated into the SQL string.
   Fix: use a parameterised query, `conn.execute("... WHERE username = ?", (username,))`.
2. **check_password** - passwords are stored and compared in plaintext with `==`,
   which is not constant-time. Fix: store salted hashes and compare with
   `hmac.compare_digest`.
