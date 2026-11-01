-- Synthetic test fixture: the original offline store schema, independent of Store.__init__.
CREATE TABLE records(
    run_id TEXT, id TEXT, account TEXT, status TEXT, version INTEGER, evidence TEXT,
    PRIMARY KEY(run_id,id));
CREATE TABLE proposals(
    id TEXT PRIMARY KEY, data TEXT NOT NULL, digest TEXT NOT NULL);
CREATE TABLE decisions(
    proposal_id TEXT PRIMARY KEY REFERENCES proposals(id), digest TEXT NOT NULL,
    approver TEXT, account TEXT, approved INTEGER NOT NULL, consumed INTEGER NOT NULL);
CREATE TABLE events(
    id INTEGER PRIMARY KEY, run_id TEXT, name TEXT, data TEXT NOT NULL);
CREATE TABLE runs(id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE studies(id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE labels(id TEXT PRIMARY KEY, study_id TEXT, data TEXT NOT NULL);
