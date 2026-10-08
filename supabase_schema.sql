-- Esquema Supabase para SIMA UdeC (protocolo-app)
-- Ejecútalo una vez en Supabase Dashboard > SQL Editor.

-- 1) Historial de protocolos generados
create table if not exists public.protocolos (
  id bigint generated always as identity primary key,
  usuario text not null,
  curso text not null default '',
  unidad text not null default '1',
  tipo text not null default 'individual',
  nombre_archivo text not null default '',
  storage_path text,
  created_at timestamptz not null default now()
);
create index if not exists protocolos_usuario_idx on public.protocolos (usuario, created_at desc);

-- 2) Notas de quiz / exámenes
create table if not exists public.quiz_notas (
  id bigint generated always as identity primary key,
  usuario text not null,
  curso text not null default '',
  unidad text not null default '1',
  correctas integer not null default 0,
  total integer not null default 20,
  nota numeric not null default 0,
  created_at timestamptz not null default now()
);
create index if not exists quiz_notas_usuario_idx on public.quiz_notas (usuario, created_at desc);

-- 3) Buckets de Storage (créelos también en Dashboard > Storage si no existen):
--    - bucket "modulos" (PDFs por materia/unidad, subidos por el admin)
--    - bucket "protocolos" (los .docx generados)
--    - bucket "subidos" (PDFs que suben los estudiantes en el generador)
-- Ejemplo por SQL (requiere permisos):
-- insert into storage.buckets (id, name, public) values ('modulos', 'modulos', false) on conflict (id) do nothing;
-- insert into storage.buckets (id, name, public) values ('protocolos', 'protocolos', false) on conflict (id) do nothing;
-- insert into storage.buckets (id, name, public) values ('subidos', 'subidos', false) on conflict (id) do nothing;
-- Y su política de acceso anónimo (igual que las anteriores):
-- create policy "anon full access subidos"
-- on storage.objects for all to anon
-- using (bucket_id = 'subidos')
-- with check (bucket_id = 'subidos');

-- 4) Auth: usa Supabase Dashboard > Authentication > Users para crear usuarios,
--    o la página /registro de la app (requiere confirmar email según tu configuración).

-- 4b) Perfiles de estudiante (nombre mostrado + avatar)
create table if not exists public.perfiles (
  usuario text primary key,
  nombre_mostrado text not null default '',
  avatar text not null default '🎓',
  updated_at timestamptz not null default now()
);

-- 5) Materias dinámicas (creadas por el admin desde la web)
create table if not exists public.materias (
  id bigint generated always as identity primary key,
  nombre text not null,
  slug text not null unique,
  semestre text not null default 'SEMESTRE V',
  centro text not null default 'MAGANGUÉ',
  docente text not null default '',
  thumbnail text not null default 'img/course_ciencia_datos.jpg',
  created_by text not null default '',
  created_at timestamptz not null default now()
);

-- 6) Unidades por materia (nombre oficial + ruta del PDF en Storage)
create table if not exists public.unidades (
  id bigint generated always as identity primary key,
  materia_id bigint not null references public.materias(id) on delete cascade,
  numero text not null default '1',
  nombre text not null default '',
  storage_path text,
  created_at timestamptz not null default now(),
  unique (materia_id, numero)
);
