# Database backups

Supabase's free plan keeps no backups, so `.github/workflows/backup.yml` makes one every night
(09:41 UTC, and on demand from the Actions tab with "Run workflow"). It dumps the app's tables
(schema `public`) with `pg_dump --format=custom`, encrypts the dump with gpg (AES256, using a
passphrase), and keeps only the encrypted file as the run's artifact for 30 days.

The encryption is not optional. The repo is public, anyone signed in to GitHub can download a
public repo's artifacts, and the database holds the contact addresses readers leave with their
reports.

## Setting it up

Add two secrets under the repo's Settings > Secrets and variables > Actions > New repository
secret:

- `BACKUP_DATABASE_URL`: a Postgres connection string for the production database, password
  included. Which one matters (next section).
- `BACKUP_PASSPHRASE`: a long random passphrase, for example the output of
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Keep a copy somewhere other
  than GitHub (a password manager): GitHub never shows a secret again, and without the
  passphrase no backup can be opened.

Until both are set the workflow fails on purpose, so the missing backup shows up as a red run
and a GitHub email rather than a green one. Run it once by hand after adding them and check that
the run's summary says how many tables it backed up.

## Which connection string

Supabase offers three (project > Connect):

- **Direct connection** (`db.<project>.supabase.co:5432`): works with pg_dump, but on the free
  plan it is IPv6 only, and GitHub's runners have no IPv6, so it fails from Actions.
- **Session pooler** (`aws-0-<region>.pooler.supabase.com:5432`, user `postgres.<project>`):
  use this one. It is IPv4 and holds one connection for the whole session, as pg_dump needs.
- **Transaction pooler** (same host, port **6543**): don't. It can hand each statement to a
  different connection, and pg_dump relies on one consistent snapshot over many statements.

Add `?sslmode=require` to the end if it isn't there already.

## Restoring

You need Postgres 17's client tools (`pg_restore`, `psql`) and gpg.

1. Download the backup: the repo's Actions tab > "Database backup" > the night you want >
   Artifacts. It arrives as a zip holding `imbroglio-<date>.dump.gpg`; unzip it.
2. Decrypt it (gpg asks for the passphrase):

   ```
   gpg --output imbroglio.dump --decrypt imbroglio-<date>.dump.gpg
   ```

3. Check what's in it without restoring anything:

   ```
   pg_restore --list imbroglio.dump
   ```

4. Restore into an **empty** database. To try it out locally, the docker-compose Postgres works:

   ```
   createdb -h localhost -U imbroglio imbroglio_restore
   pg_restore --no-owner --no-privileges --dbname=postgresql://imbroglio:imbroglio@localhost:5432/imbroglio_restore imbroglio.dump
   ```

   `--no-owner --no-privileges` leave out Supabase's roles, which a plain Postgres doesn't have.
   An error that schema `public` already exists is harmless.

   To put production back after losing it, restore the same way into the new database
   (the session pooler URL again), then point the services' `DATABASE_URL` at it. The
   `alembic_version` table comes back with the data, so the services see the schema as current
   and don't migrate it again.

5. Delete the decrypted `imbroglio.dump` when you're done: it holds readers' contact addresses.

## Limits

- One backup a night, so up to a day of new requests, findings and reports can be lost.
- Only schema `public`. Nothing of ours lives elsewhere; Supabase's own schemas (auth, storage)
  aren't used by Imbroglio.
- Artifacts last 30 days. An older backup has to be downloaded and kept somewhere else before
  then.
