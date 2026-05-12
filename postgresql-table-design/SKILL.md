---
name: postgresql-table-design
description: Design and optimize a PostgreSQL-specific schema. Use for PostgreSQL best practices, data types, indexing, constraints, performance patterns, and advanced features.
---

# PostgreSQL table design

## Core rules

- Use modern PostgreSQL 18 features (virtual columns, uuidv7) if possible.
- Prefer `text` with `check (length(field) <= N)` over `varchar(N)`.
- Define a **primary key** for reference tables (e.g., users, orders). Not needed for time-series, event, or log data. When used, prefer `bigint generated always as identity`; use `uuid` only for global uniqueness or when opacity is required.
- **Normalize to 3NF** initially to remove redundancy and update anomalies. Denormalize only for proven, high-ROI reads where join performance is an issue. Premature denormalization increases maintenance.
- Add **`not null`** constraints where semantically needed, and use **`default`** values for common cases.
- Create **indexes for actual query access paths**: PK/unique (auto), **FK columns (manual)**, frequent filters/sorts, and join keys.
- Prefer **`timestamptz`** for event times, **`numeric`** for money, **`text`** for strings, **`bigint`** for integers, **`double precision`** for floats (or `numeric` for exact decimal math).

## PostgreSQL "Gotchas"

- **Identifiers**: Unquoted names are lowercased. Avoid quoted/mixed-case. Convention: use `snake_case` for tables and columns.
- **SQL keywords**: lowercase.
- **Unique + NULLs**: `unique` allows multiple NULLs. Use `unique (...) nulls not distinct` (PG 15+) to allow a single NULL.
- **FK indexes**: PostgreSQL does not auto-index FK columns; add indexes manually.
- **No silent coercions**: Overflows raise errors (e.g., 999 into `numeric(2,0)` fails). No silent truncation/rounding.
- **Sequences/identity gaps** are normal due to rollbacks and concurrency. Do not "fix" gaps.
- **Heap storage**: No clustered PK by default. `cluster` is a one-off operation and isn't maintained after further inserts. Row order on disk follows insertion unless explicitly clustered.
- **MVCC**: Updates/deletes leave dead rows. `vacuum` cleans them. Avoid wide-row and high-churn designs when possible.

## Data types

- **IDs**: Prefer `bigint generated always as identity`; use `uuid` when federating/distributing or for opaque IDs. Use `uuidv7()`; use `gen_random_uuid()` for PostgreSQL 17 and earlier.
- **Integers**: Use `bigint` unless space matters, then use `integer` or `smallint` as appropriate.
- **Floats**: Use `double precision`. Use `real` only for critical storage constraints. Use `numeric` for decimals needing full precision.
- **Strings**: Use `text`. For limits, use `check (length(col) <= n)`, not `varchar(n)`; avoid `char(n)`. Use `bytea` for binary. Large strings/binary (>2KB) are TOASTed. Default `extended` is optimal. Use collation/expression indexes on `lower(col)` or `citext` for case-insensitivity.
- **Money**: Use `numeric(p, s)`, not float.
- **Time**: Use `timestamptz` for timestamps, `date` for dates, `interval` for durations. Avoid `timestamp` (without timezone). Use `now()` for transaction time, `clock_timestamp()` for wall time.
- **Booleans**: Use `boolean` with `not null` if appropriate.
- **Enums**: Use `create type ... as enum` for stable sets. For evolving values, use `text`/`int` plus `check` or lookup tables.
- **Arrays**: Use standard array types for ordered lists. Index with **GIN** for containment and overlap. Suitable for tags and categories; for relations, use junction tables. Literals: `'{val1,val2}'` or `array[val1,val2]`.
- **Range types**: Use `daterange`, `numrange`, `tstzrange` for intervals; index with **GiST**.
- **Network types**: Use `inet`, `cidr`, `macaddr` for IP/network/MAC.
- **Geometric types**: Use `point`, `line`, `polygon`, `circle`; index with **GiST**. For advanced needs, use **PostGIS**.
- **Text search**: `tsvector` for docs, index with **GIN**. Specify language in `to_tsvector()`/`to_tsquery()`.
- **Domain types**: Use for reusable custom types with validation.
- **Composite types**: Use for structured columns; access as `(col).field`.
- **JSONB**: Preferred for flexible/optional fields; index with **GIN**. Use JSON only if order matters.
- **Vector types**: Use `vector` from `pgvector` for embeddings/similarity search.

### Avoid these data types

- Do not use `timestamp` (no timezone); use `timestamptz`.
- Do not use `char(n)` or `varchar(n)`; use `text`.
- Do not use the `money` type; use `numeric`.
- Do not use `timetz`; use `timestamptz`.
- Do not use precision like `timestamptz(0)`; use `timestamptz`.
- Do not use `serial`; use `generated always as identity`.

## Table types

- **Regular**: Standard, fully durable/logged.
- **`temporary`**: Session-scoped, not logged, auto-dropped.
- **`unlogged`**: Fast, not crash-safe. Use for cache/staging.

## Row-level security

Enable with `alter table tbl enable row level security`, then set policies:
```sql
create policy user_access on orders for select to app_users using (user_id = current_user_id());
```

## Constraints

- **primary key**: Implies unique + not null; adds B-tree index.
- **Foreign key**: Specify `on delete`/`on update` actions. Index referencing columns explicitly. For circular dependencies, use `deferrable initially deferred`.
- **unique**: B-tree index; allows multiple NULLs (unless `nulls not distinct`, PG15+). Prefer `nulls not distinct` unless duplicate NULLs are needed.
- **check**: Row-level constraints; NULLs pass unless combined with `not null`.
- **exclude**: Prevents overlaps using operators; needs suitable index (often GiST).

## Indexing

- **B-tree**: Default; for equality/range queries/order by.
- **Composite**: Index uses leftmost-constrained columns first. Place most-filtered columns first.
- **Covering**: Use `include` for index-only scans.
- **Partial**: For hot subsets, e.g., `status='active'`.
- **Expression**: Use for computed search keys; `where` must match expression.
- **GIN**: Use for JSONB, arrays, text search.
- **GiST**: Use for ranges, geometry, exclusion constraints.
- **BRIN**: For huge, naturally ordered data (e.g., time-series).

## Partitioning

- Use for very large tables (>100M rows) with partition-key filtering.
- Useful for periodic pruning or bulk replace.
- **Range**: For time-series: `partition by range (created_at)` and create partitions per period.
  - **TimescaleDB** automates this.
- **List**: For discrete values: `partition by list (region)`.
- **Hash**: For even distribution when no natural key: `partition by hash (user_id)`.
- Only declarative partitioning; avoid table inheritance.
- **Limitations**: No global uniques—include partition key. No FKs from partitioned tables; use triggers.

## Special considerations

### Update-heavy tables

- Separate frequently updated ("hot") columns into a different table.
- Set `fillfactor=90` to support HOT updates.
- Avoid updating indexed columns.
- Partition based on update patterns.

### Insert-heavy workloads

- Minimize indexes; create only as needed.
- Use `copy` or multi-row `insert` for bulk loads.
- Use **unlogged tables** for staging when possible.
- Defer index creation on large loads: drop, load, then recreate.
- Partition by time/hash to distribute load; TimescaleDB can automate this.
- Use a natural key as PK if possible; insert-heavy tables may not need a PK. If surrogate needed, prefer `bigint generated always as identity`.

### Upsert-friendly design

- `on conflict (col1, col2)` needs a matching unique index (not partial).
- Use `excluded.column` for referenced values and only update changed columns.
- `do nothing` is faster than `do update` if no changes required.

### Safe schema evolution

- Most DDL is transactional (can roll back).
- Use `create index concurrently` for non-blocking index creation; not in transactions.
- Adding `not null` with volatile defaults rewrites entire table. Non-volatile is fast.
- Drop constraints before dropping columns to avoid errors.
- Changing function signatures creates overloads. Drop old as needed.

## Generated columns

- Use `generated always as (...) stored` for computed, indexable columns. Use `virtual` for columns that don't need to be stored.

## Extensions

- **pgcrypto**: Password hashing.
- **pg_trgm**: Fuzzy search; GIN indexes for `like`/`ilike`.
- **citext**: Case-insensitive text type; prefer expression indexes unless strict constraints required.
- **btree_gin/btree_gist**: Mixed-type indexes.
- **hstore**: Key-value pairs; JSONB preferred generally.
- **timescaledb**: Time-series automation.
- **postgis**: Geospatial features.
- **pgvector**: Vector search.
- **pgaudit**: Audit logging.

## JSONB guidance

- Prefer `jsonb` with GIN index:
  - Containment: `jsonb_col @> '{"k":"v"}'`
  - Key existence: `jsonb_col ? 'k'`, any/all: `?|`, `?&`
  - Path containment for nested docs
- Use `jsonb_path_ops` GIN for heavy containment-only; disallows key existence ops.
- For equality/range: extract scalar to generated/expression column and index as B-tree.
- Prefer B-tree range queries over runtime casts.
- Use GIN with `@>` for JSONB arrays when needed.
- Keep core data as regular columns; reserve JSONB for optional/variable fields.
- Add constraints like `check(jsonb_typeof(config) = 'object')` for safety.

## Examples

### Users

```sql
create table users (
  user_id bigint generated always as identity primary key,
  email text not null unique,
  name text not null,
  created_at timestamptz not null default now()
);
create unique index on users (lower(email));
create index on users (created_at);
```

### Orders

```sql
create table orders (
  order_id bigint generated always as identity primary key,
  user_id bigint not null references users(user_id),
  status text not null default 'PENDING' check (status in ('PENDING','PAID','CANCELED')),
  total numeric(10,2) not null check (total > 0),
  created_at timestamptz not null default now()
);
create index on orders (user_id);
create index on orders (created_at);
```

### JSONB

```sql
create table profiles (
  user_id bigint primary key references users(user_id),
  attrs jsonb not null default '{}',
  theme text generated always as (attrs->>'theme') stored
);
create index profiles_attrs_gin on profiles using gin (attrs);
```
