# Database Read Verification Policy

Database verification is PostgreSQL read-only evidence collection on an
`isolated_test` target. It is not a generic DB shell. The agent selects an
approved ID; it never supplies SQL, a connection string, or a client command.

Each query is a local relative `.sql` file. The runner permits one read-only
`SELECT` or non-mutating `WITH` statement, rejects DDL/DML/locks and sets the
PostgreSQL client session to default read-only mode. The connection is provided
only through the catalog's approved environment-variable reference.

Results and logs are access-controlled. Reports must use approved non-sensitive
summaries. Production access, mutations, migrations, schema changes, customer
data extraction, and unrestricted database credentials are prohibited.
