-- DocuQuery schema for Supabase + pgvector.
-- Run this once in Supabase Dashboard > SQL Editor.
-- The Flask server uses SUPABASE_SERVICE_ROLE_KEY server-side; do not expose it to browsers.

create extension if not exists vector with schema extensions;

create table if not exists public.users (
    id uuid primary key,
    name text not null,
    email text not null unique,
    password_hash text not null,
    created_at timestamptz not null default now()
);

create table if not exists public.papers (
    id uuid primary key,
    session_id uuid not null,
    title text not null,
    filename text not null,
    page_count integer not null default 0 check (page_count >= 0),
    created_at timestamptz not null default now(),
    summary jsonb not null default '{}'::jsonb
);

create table if not exists public.paper_chunks (
    id uuid primary key,
    paper_id uuid not null references public.papers(id) on delete cascade,
    session_id uuid not null,
    page_number integer not null check (page_number > 0),
    section text not null default 'Overview',
    content text not null,
    embedding extensions.vector(384) not null
);

-- For projects created before these columns existed.
alter table public.users add column if not exists reset_token text;
alter table public.users add column if not exists reset_expires timestamptz;
alter table public.papers add column if not exists file_path text;
alter table public.papers add column if not exists file_size bigint not null default 0;

create index if not exists papers_session_created_idx
    on public.papers (session_id, created_at desc);

create index if not exists paper_chunks_paper_session_idx
    on public.paper_chunks (paper_id, session_id);

create index if not exists paper_chunks_embedding_idx
    on public.paper_chunks using hnsw (embedding extensions.vector_cosine_ops);

create or replace function public.match_paper_chunks(
    query_embedding extensions.vector(384),
    match_session_id uuid,
    match_paper_id uuid,
    match_count integer default 6
)
returns table (
    id uuid,
    paper_id uuid,
    session_id uuid,
    page_number integer,
    section text,
    content text,
    similarity double precision
)
language sql
stable
set search_path = public, extensions
as $$
    select
        chunk.id,
        chunk.paper_id,
        chunk.session_id,
        chunk.page_number,
        chunk.section,
        chunk.content,
        (1 - (chunk.embedding <=> query_embedding))::double precision as similarity
    from public.paper_chunks as chunk
    where chunk.session_id = match_session_id
      and chunk.paper_id = match_paper_id
    order by chunk.embedding <=> query_embedding
    limit greatest(1, least(match_count, 20));
$$;

-- Browser clients are not used in this project. Only the server-side service role
-- should access these tables/RPC; RLS blocks anonymous/authenticated direct access.
alter table public.users enable row level security;
alter table public.papers enable row level security;
alter table public.paper_chunks enable row level security;

revoke all on public.users from anon, authenticated;
revoke all on public.papers from anon, authenticated;
revoke all on public.paper_chunks from anon, authenticated;
revoke execute on function public.match_paper_chunks(extensions.vector, uuid, uuid, integer)
    from public, anon, authenticated;
grant all on public.users to service_role;
grant all on public.papers to service_role;
grant all on public.paper_chunks to service_role;
grant execute on function public.match_paper_chunks(extensions.vector, uuid, uuid, integer)
    to service_role;
